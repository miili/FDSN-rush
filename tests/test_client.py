from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import aiohttp
import pytest
from conftest import FakeFDSN
from pyrocko import io

from fdsn_rush import client as client_module
from fdsn_rush.client import (
    REAUTH_MIN_AGE,
    RETRY_AFTER_MAX,
    RETRY_ATTEMPTS,
    DownloadDayfile,
    FDSNClient,
    retry_after,
)
from fdsn_rush.models.station import Stations
from fdsn_rush.selection import StationSelection
from fdsn_rush.utils import NSL, fdsn_time
from fdsn_rush.writer import SDSWriter

HHZ = ("XX", "STA01", "", "HHZ")


def testfdsn_time() -> None:
    assert fdsn_time(date(2024, 1, 1)) == "2024-01-01T00:00:00"


async def test_prepare_requests_each_network_once(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX.STA01", "YY.STA01", "XX.STA02"])

    await client.prepare()
    await client.add_selection(selection, date(2024, 1, 1), date(2024, 1, 3))

    requests = fake_fdsn.station_requests
    assert len(requests) == 2
    assert requests[0]["options"] == {
        "level": "channel",
        "format": "text",
        "nodata": "404",
    }
    assert requests[0]["selection"] == [
        ["XX", "STA01", "*", "*", "2024-01-01T00:00:00", "2024-01-03T00:00:00"],
        ["XX", "STA02", "*", "*", "2024-01-01T00:00:00", "2024-01-03T00:00:00"],
    ]
    assert [r["selection"][0][0] for r in requests] == ["XX", "YY"]
    assert [s.nsl.pretty for s in client.available_stations] == [
        "XX.STA01.",
        "XX.STA02.",
    ]


async def test_prepare_twice_replaces_stations(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX.STA01"])

    await client.prepare()
    await client.add_selection(selection, date(2024, 1, 1), date(2024, 1, 3))
    await client.prepare()
    assert client.available_stations.n_stations == 0

    await client.add_selection(selection, date(2024, 1, 1), date(2024, 1, 3))
    assert client.available_stations.n_stations == 1


async def test_add_selection_merges_stations(fake_fdsn: FakeFDSN) -> None:
    """Selections add up, a station matched by several is kept once."""
    client = FDSNClient(url=fake_fdsn.url)
    await client.prepare()

    for nsl in ("XX.STA01", "XX.STA*"):
        selection = StationSelection(stations=[nsl])
        await client.add_selection(selection, date(2024, 1, 1), date(2024, 1, 3))

    assert [s.nsl.pretty for s in client.available_stations] == [
        "XX.STA01.",
        "XX.STA02.",
        "XX.STA03.",
    ]


async def test_prepare_keeps_selections_apart(fake_fdsn: FakeFDSN) -> None:
    """One line per selection: no cross product, a wildcard stays a wildcard."""
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX.STA01.", "XX.STA02.10"])

    await client.prepare()
    await client.add_selection(selection, date(2024, 1, 1), date(2024, 1, 3))

    (request,) = fake_fdsn.station_requests
    assert [line[:4] for line in request["selection"]] == [
        ["XX", "STA01", "*", "*"],
        ["XX", "STA02", "10", "*"],
    ]


async def test_download_metadata_is_one_post(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = [NSL.parse("XX.STA*"), NSL.parse("XX.STA03.00")]

    data = await client.download_metadata(selection, date(2024, 1, 1), date(2024, 1, 3))

    assert data == "<FDSNStationXML/>"
    (request,) = fake_fdsn.station_requests
    assert request["options"]["level"] == "response"
    assert [line[:3] for line in request["selection"]] == [
        ["XX", "STA*", "*"],
        ["XX", "STA03", "00"],
    ]


def _dayfiles(stations: Stations, *codes: str, days: int = 1) -> list[DownloadDayfile]:
    """Dayfiles of the XX.STA01 channels with `codes`, from 2024-01-01 on."""
    channels = {
        channel.code: channel
        for station in stations
        if station.nsl.station == "STA01"
        for channel in station.channels
    }
    return [
        DownloadDayfile(channels[code], date(2024, 1, 1) + timedelta(days=day))
        for code in codes
        for day in range(days)
    ]


async def _download(
    client: FDSNClient, sds_archive: Path, dayfiles: list[DownloadDayfile]
) -> SDSWriter:
    writer = SDSWriter(sds_archive=sds_archive)
    await writer.prepare()
    for dayfile in dayfiles:
        await client.add_work(dayfile)
    await client.download(writer, asyncio.Event())
    return writer


def _n_requests(fake_fdsn: FakeFDSN, channel: str) -> int:
    return sum(r["channel"] == channel for r in fake_fdsn.dataselect_requests)


async def test_download_retries_dropped_connections(
    fake_fdsn: FakeFDSN, stations: Stations, sds_archive: Path
) -> None:
    """A dropped connection is retried, the data of the failed attempt discarded."""
    fake_fdsn.faults[HHZ] = ["body"] * (RETRY_ATTEMPTS - 1)
    client = FDSNClient(url=fake_fdsn.url, rate_limit=1000)
    (dayfile,) = _dayfiles(stations, "HHZ")

    await _download(client, sds_archive, [dayfile])

    assert _n_requests(fake_fdsn, "HHZ") == RETRY_ATTEMPTS
    assert client._stats.n_failed == 0
    (tr,) = io.load(str(sds_archive / dayfile.sds_path()))
    assert tr.ydata.size == 60_000  # 600 s at 100 Hz, nothing duplicated


@pytest.mark.parametrize(
    ("mode", "error"),
    [("start", "ServerDisconnectedError"), ("body", "ClientPayloadError")],
)
async def test_download_gives_up_on_dropped_connections(
    fake_fdsn: FakeFDSN,
    stations: Stations,
    sds_archive: Path,
    caplog: pytest.LogCaptureFixture,
    mode: str,
    error: str,
) -> None:
    """A dayfile that keeps failing is counted as failed, the others are saved."""
    fake_fdsn.faults[HHZ] = [mode] * 100
    client = FDSNClient(url=fake_fdsn.url, rate_limit=1000, n_workers=2)
    dayfiles = _dayfiles(stations, "HHZ", "HHN", days=2)

    await _download(client, sds_archive, dayfiles)

    # aiohttp itself repeats a request once if a reused connection was closed
    assert _n_requests(fake_fdsn, "HHZ") >= 2 * RETRY_ATTEMPTS
    assert client._stats.n_failed == 2
    assert f"Failed to download XX.STA01..HHZ for 2024-01-01: {error}" in caplog.text
    for dayfile in dayfiles:
        saved = (sds_archive / dayfile.sds_path()).exists()
        assert saved == (dayfile.channel.code == "HHN")
        assert not (sds_archive / dayfile.sds_path(partial=True)).exists()


async def test_download_retries_server_errors(
    fake_fdsn: FakeFDSN, stations: Stations, sds_archive: Path
) -> None:
    fake_fdsn.faults[HHZ] = [503, 429]
    client = FDSNClient(url=fake_fdsn.url, rate_limit=1000)
    (dayfile,) = _dayfiles(stations, "HHZ")

    await _download(client, sds_archive, [dayfile])

    assert _n_requests(fake_fdsn, "HHZ") == RETRY_ATTEMPTS
    assert client._stats.n_failed == 0
    assert (sds_archive / dayfile.sds_path()).exists()


async def test_download_gives_up_on_server_errors(
    fake_fdsn: FakeFDSN, stations: Stations, sds_archive: Path
) -> None:
    """A lasting 500 is retried, then failed, and not written to the remote log."""
    fake_fdsn.failing_nslc.add(HHZ)
    client = FDSNClient(url=fake_fdsn.url, rate_limit=1000)
    (dayfile,) = _dayfiles(stations, "HHZ")

    writer = await _download(client, sds_archive, [dayfile])

    assert _n_requests(fake_fdsn, "HHZ") == RETRY_ATTEMPTS
    assert client._stats.n_failed == 1
    assert not writer.remote_log.get_error(
        dayfile.channel.nslc, dayfile.date, client.url
    )


async def test_download_timeout_is_logged_as_timeout(
    fake_fdsn: FakeFDSN,
    stations: Stations,
    sds_archive: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "RETRY_ATTEMPTS", 1)
    fake_fdsn.faults[HHZ] = ["slow"]
    client = FDSNClient(url=fake_fdsn.url, rate_limit=1000)
    client.timeout = 0.1  # below the configurable minimum, to keep the test fast
    (dayfile,) = _dayfiles(stations, "HHZ")

    await _download(client, sds_archive, [dayfile])

    assert client._stats.n_failed == 1
    assert "XX.STA01..HHZ for 2024-01-01: Remote timeout (0.1 s)" in caplog.text


@pytest.mark.parametrize(
    ("headers", "seconds"),
    [
        (None, 0.0),
        ({}, 0.0),
        ({"Retry-After": "5"}, 5.0),
        ({"Retry-After": "-5"}, 0.0),
        ({"Retry-After": "86400"}, RETRY_AFTER_MAX),
        ({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, 0.0),
    ],
)
def test_retry_after(headers: dict[str, str] | None, seconds: float) -> None:
    assert retry_after(headers) == seconds


async def test_reauthenticate_once_for_all_workers(
    fake_fdsn: FakeFDSN, stations: Stations, eida_key: Path
) -> None:
    """Forgotten credentials are replaced by one token exchange for all requests."""
    client = FDSNClient(url=fake_fdsn.url, eida_key=eida_key)
    await client._authenticate()
    first, *dayfiles = _dayfiles(stations, "HHZ", "HHN", "HHE", days=3)

    async def fetch(session: aiohttp.ClientSession, dayfile: DownloadDayfile) -> bytes:
        chunks = client.download_waveform_data(session, dayfile.channel, dayfile.date)
        return b"".join([chunk async for chunk in chunks])

    async with aiohttp.ClientSession(base_url=fake_fdsn.url) as session:
        assert await fetch(session, first)
        # A day later the credentials expire
        client._auth_time -= 86400
        fake_fdsn.auth_users.clear()
        data = await asyncio.gather(*(fetch(session, d) for d in dayfiles))

    assert all(data)
    assert fake_fdsn.n_auth == 2


@pytest.mark.parametrize(("min_age", "n_auth"), [(REAUTH_MIN_AGE, 1), (0.0, 2)])
async def test_unauthorized_network_is_exchanged_once(
    fake_fdsn: FakeFDSN,
    stations: Stations,
    sds_archive: Path,
    eida_key: Path,
    monkeypatch: pytest.MonkeyPatch,
    min_age: float,
    n_auth: int,
) -> None:
    """A 401 for data the token does not grant costs at most one exchange.

    Fresh credentials are never exchanged. Older ones are exchanged once, and
    when the new credentials are rejected too, the network is marked.
    """
    monkeypatch.setattr(client_module, "REAUTH_MIN_AGE", min_age)
    fake_fdsn.unauthorized_nslc.add(HHZ)
    client = FDSNClient(
        url=fake_fdsn.url, rate_limit=1000, n_workers=1, eida_key=eida_key
    )
    dayfiles = _dayfiles(stations, "HHZ", "HHN", days=3)

    await _download(client, sds_archive, dayfiles)

    assert fake_fdsn.n_auth == n_auth
    assert client._unauthorized_networks == {"XX"}
    assert client._stats.n_failed == 3
    assert all((sds_archive / d.sds_path()).exists() for d in dayfiles[3:])


async def test_failed_exchange_does_not_abort(
    fake_fdsn: FakeFDSN,
    stations: Stations,
    sds_archive: Path,
    eida_key: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed exchange fails the restricted dayfiles, and is not repeated."""
    monkeypatch.setattr(client_module, "REAUTH_MIN_AGE", 0.0)
    fake_fdsn.auth_status = [200, 500, 200]
    fake_fdsn.unauthorized_nslc.add(HHZ)
    client = FDSNClient(
        url=fake_fdsn.url, rate_limit=1000, n_workers=1, eida_key=eida_key
    )
    dayfiles = _dayfiles(stations, "HHZ", "HHN", days=3)

    await _download(client, sds_archive, dayfiles)

    assert client._auth_failed
    assert fake_fdsn.auth_status == [200]  # only one failed attempt
    assert client._stats.n_failed == 3
    assert all((sds_archive / d.sds_path()).exists() for d in dayfiles[3:])


async def test_reauthenticate_rules(
    fake_fdsn: FakeFDSN, eida_key: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FDSNClient(url=fake_fdsn.url, eida_key=eida_key)
    await client._authenticate()
    auth = client._auth
    assert auth is not None

    # Fresh credentials: the token does not grant the network
    assert not await client._reauthenticate(auth, "XX")
    assert client._unauthorized_networks == {"XX"}
    assert fake_fdsn.n_auth == 1

    # Older credentials: forgotten, unless the network is not granted
    client._auth_time -= REAUTH_MIN_AGE
    assert not await client._reauthenticate(auth, "XX")
    assert await client._reauthenticate(auth, "YY")
    assert client._auth is not auth
    assert fake_fdsn.n_auth == 2
    # Another worker already replaced them
    assert await client._reauthenticate(auth, "YY")
    assert fake_fdsn.n_auth == 2

    # A failed exchange is not repeated
    monkeypatch.setattr(client_module, "REAUTH_MIN_AGE", 0.0)
    eida_key.unlink()
    auth = client._auth
    assert not await client._reauthenticate(auth, "YY")
    assert not await client._reauthenticate(auth, "ZZ")
    assert client._auth is auth
    assert client._auth_failed


async def test_authenticate_rejects_expired_token(
    fake_fdsn: FakeFDSN, eida_key: Path
) -> None:
    eida_key.write_text(
        eida_key.read_text().replace('"valid_until": "2', '"valid_until": "1')
    )
    client = FDSNClient(url=fake_fdsn.url, eida_key=eida_key)

    with pytest.raises(ValueError, match="EIDA token expired"):
        await client._authenticate()


@pytest.mark.parametrize("dashes", ["-----", ""])
async def test_authenticate_header(
    fake_fdsn: FakeFDSN, eida_key: Path, dashes: str
) -> None:
    """The PGP header is accepted with and without the dashes."""
    eida_key.write_text(eida_key.read_text().replace("-----", dashes))
    client = FDSNClient(url=fake_fdsn.url, eida_key=eida_key)

    await client._authenticate()

    assert client._auth is not None
