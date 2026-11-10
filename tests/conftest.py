from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, time, timedelta
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from pyrocko import io, trace

from fdsn_rush import client, selection
from fdsn_rush.models.station import Stations, parse_stations

STATION_HEADER = (
    "#Network|Station|Location|Channel|Latitude|Longitude|Elevation|Depth|"
    "Azimuth|Dip|SensorDescription|Scale|ScaleFreq|ScaleUnits|SampleRate|"
    "StartTime|EndTime"
)


def _line(sta: str, cha: str, rate: float = 100.0, end: str = "") -> str:
    return (
        f"XX|{sta}||{cha}|52.0|13.0|100.0|0.0|0.0|-90.0|Sensor|1e9|1.0|M/S|"
        f"{rate}|2020-01-01T00:00:00|{end}"
    )


# STA01: HH + LH (too low sampling rate) + LDO (aux channel, dropped)
# STA02: EH only, EHE is missing on the server (404)
# STA03: single HHZ channel, ends on 2024-01-01
STATION_TEXT = "\n".join(
    [
        STATION_HEADER,
        _line("STA01", "HHE"),
        _line("STA01", "HHN"),
        _line("STA01", "HHZ"),
        _line("STA01", "LDO", rate=1.0),
        _line("STA01", "LHZ", rate=1.0),
        _line("STA02", "EHE"),
        _line("STA02", "EHN"),
        _line("STA02", "EHZ"),
        _line("STA03", "HHZ", end="2024-01-01T23:59:59"),
    ]
)

MISSING_NSLC = {("XX", "STA02", "", "EHE")}

MSeedFactory = Callable[..., bytes]


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "RETRY_DELAY", 0.0)
    monkeypatch.setattr(selection, "RETRY_DELAY", 0.0)


@pytest.fixture
def stations() -> Stations:
    return parse_stations(STATION_TEXT)


@pytest.fixture
def make_mseed(tmp_path_factory: pytest.TempPathFactory) -> MSeedFactory:
    """Return a factory producing MiniSEED bytes for one trace."""
    tmp_dir = tmp_path_factory.mktemp("mseed")

    def factory(
        nslc: tuple[str, str, str, str],
        day: date,
        seconds: float = 600.0,
        deltat: float = 0.01,
    ) -> bytes:
        tmin = datetime.combine(day, time(), tzinfo=UTC).timestamp()
        tr = trace.Trace(
            *nslc,
            deltat=deltat,
            tmin=tmin,
            ydata=np.arange(int(seconds / deltat), dtype=np.int32),
        )
        path = tmp_dir / f"{'.'.join(nslc)}.{day}.{seconds}.mseed"
        io.save([tr], str(path), format="mseed")
        return path.read_bytes()

    return factory


class FakeFDSN:
    def __init__(self, server: TestServer) -> None:
        self.server = server
        self.dataselect_requests: list[dict[str, str]] = []
        self.station_requests: list[dict[str, Any]] = []
        self.failing_nslc: set[tuple[str, str, str, str]] = set()  # answered with 500
        # Faults for an NSLC, one per query: "start" drops the connection before
        # the response, "body" halfway through it, "slow" waits 0.5 s before the
        # response, and a status code answers with it and `Retry-After: 0`
        self.faults: dict[tuple[str, str, str, str], list[str | int]] = {}
        # Users of the credentials handed out by /auth that the server still knows
        self.auth_users: set[str] = set()
        self.n_auth = 0
        self.unauthorized_nslc: set[tuple[str, str, str, str]] = set()  # always 401
        # Status codes to answer station queries for a network with, one per query
        self.station_errors: dict[str, list[int]] = {}

    @property
    def url(self) -> str:
        return str(self.server.make_url("/"))


def _matches(codes: list[str], patterns: list[str]) -> bool:
    """Match NET STA LOC CHA codes against a POST selection line, "--" is blank."""
    return all(
        fnmatch(code, "" if pattern == "--" else pattern)
        for code, pattern in zip(codes, patterns, strict=True)
    )


@pytest.fixture
async def fake_fdsn(make_mseed: MSeedFactory) -> AsyncIterator[FakeFDSN]:
    """A local FDSN web service serving STATION_TEXT and synthetic waveforms."""

    async def station(request: web.Request) -> web.Response:
        # Station requests are POSTed: "key=value" lines, then one
        # "NET STA LOC CHA START END" line per selection.
        options: dict[str, str] = {}
        selection: list[list[str]] = []
        for line in (await request.text()).splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                options[key] = value
            elif line.strip():
                fields = line.split()
                if len(fields) != 6:
                    raise web.HTTPBadRequest(text=f"Error 400: bad line {line!r}")
                selection.append(fields)
        fake.station_requests.append({"options": options, "selection": selection})
        errors = fake.station_errors.get(selection[0][0] if selection else "")
        if errors:
            status = errors.pop(0)
            if status == 204:
                return web.Response(status=204)
            return web.Response(status=status, text=f"Error {status}")
        # Geographic options are ignored, all stations are at 52.0, 13.0
        lines = [
            line
            for line in STATION_TEXT.splitlines()[1:]
            if any(_matches(line.split("|")[:4], fields[:4]) for fields in selection)
        ]
        if not lines:
            raise web.HTTPNotFound(text="Error 404: no data")
        if options.get("format") == "xml":
            return web.Response(text="<FDSNStationXML/>")
        return web.Response(text="\n".join([STATION_HEADER, *lines]))

    async def dataselect(request: web.Request) -> web.StreamResponse:
        query = request.query
        fake.dataselect_requests.append(dict(query))
        # Be as strict as a real server: all selection parameters are mandatory,
        # a blank location is "--", times are full timestamps and the format is
        # "miniseed".
        for key in ("network", "station", "location", "channel"):
            if key not in query:
                raise web.HTTPBadRequest(text=f"Error 400: missing {key}")
        if query.get("format", "miniseed") != "miniseed":
            raise web.HTTPBadRequest(text="Error 400: unsupported format")
        try:
            start = datetime.strptime(query["starttime"], "%Y-%m-%dT%H:%M:%S")  # noqa: DTZ007
            datetime.strptime(query["endtime"], "%Y-%m-%dT%H:%M:%S")  # noqa: DTZ007
        except (KeyError, ValueError):
            raise web.HTTPBadRequest(text="Error 400: bad time") from None
        location = "" if query["location"] == "--" else query["location"]
        nslc = (query["network"], query["station"], location, query["channel"])
        if nslc in fake.failing_nslc:
            raise web.HTTPInternalServerError(text="Error 500")
        if nslc in MISSING_NSLC:
            raise web.HTTPNotFound(text="Error 404: no data")
        body = make_mseed(nslc, start.date())
        faults = fake.faults.get(nslc)
        if not faults:
            return web.Response(body=body)

        fault = faults.pop(0)
        if isinstance(fault, int):
            return web.Response(
                status=fault, headers={"Retry-After": "0"}, text=f"Error {fault}"
            )
        if fault == "slow":
            await asyncio.sleep(0.5)
            return web.Response(body=body)
        assert request.transport is not None
        if fault == "start":
            request.transport.close()
            return web.Response(body=body)
        response = web.StreamResponse()
        response.content_length = len(body)
        await response.prepare(request)
        await response.write(body[: len(body) // 2])
        await asyncio.sleep(0.01)
        request.transport.close()
        return response

    async def auth(request: web.Request) -> web.Response:
        if "BEGIN PGP" not in await request.text():
            raise web.HTTPBadRequest(text="Error 400: no token")
        fake.n_auth += 1
        user = f"user{fake.n_auth}"
        fake.auth_users.add(user)
        return web.Response(text=f"{user}:secret")

    async def queryauth(request: web.Request) -> web.StreamResponse:
        # Checks the user name only, not the digest
        match = re.search(
            r'username="([^"]+)"', request.headers.get("Authorization", "")
        )
        nslc = (
            request.query.get("network"),
            request.query.get("station"),
            request.query.get("location", "").replace("--", ""),
            request.query.get("channel"),
        )
        if (
            not match
            or match[1] not in fake.auth_users
            or nslc in fake.unauthorized_nslc
        ):
            raise web.HTTPUnauthorized(
                headers={
                    "WWW-Authenticate": 'Digest realm="fake", nonce="abc", qop="auth"'
                },
                text="Error 401",
            )
        return await dataselect(request)

    app = web.Application()
    app.router.add_post("/fdsnws/station/1/query", station)
    app.router.add_get("/fdsnws/dataselect/1/query", dataselect)
    app.router.add_post("/fdsnws/dataselect/1/auth", auth)
    app.router.add_get("/fdsnws/dataselect/1/queryauth", queryauth)

    server = TestServer(app)
    await server.start_server()
    fake = FakeFDSN(server)
    yield fake
    await server.close()


@pytest.fixture
def sds_archive(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def eida_key(tmp_path: Path) -> Path:
    """An EIDA token file, valid for a day."""
    now = datetime.now(UTC)
    details = (
        f'{{"valid_until": "{(now + timedelta(days=1)).isoformat()}", '
        f'"issued": "{now.isoformat()}", "mail": "you@example.org"}}'
    )
    path = tmp_path / "eidatoken"
    path.write_text(
        "-----BEGIN PGP SIGNED MESSAGE-----\n"
        "Hash: SHA256\n\n"
        f"{details}\n"
        "-----BEGIN PGP SIGNATURE-----\n"
        "...\n"
        "-----END PGP SIGNATURE-----\n"
    )
    return path
