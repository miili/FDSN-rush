from __future__ import annotations

from datetime import date

from conftest import FakeFDSN

from fdsn_rush.client import FDSNClient
from fdsn_rush.selection import StationSelection
from fdsn_rush.utils import NSL, fdsn_time


def testfdsn_time() -> None:
    assert fdsn_time(date(2024, 1, 1)) == "2024-01-01T00:00:00"


async def test_prepare_requests_each_network_once(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX.STA01", "YY.STA01", "XX.STA02"])

    await client.prepare(selection, date(2024, 1, 1), date(2024, 1, 3))

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
    selection = StationSelection(stations=["XX"])

    await client.prepare(selection, date(2024, 1, 1), date(2024, 1, 3))
    await client.prepare(selection, date(2024, 1, 1), date(2024, 1, 3))

    assert client.available_stations.n_stations == 3


async def test_prepare_keeps_selections_apart(fake_fdsn: FakeFDSN) -> None:
    """One line per selection: no cross product, a wildcard stays a wildcard."""
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX.STA01.", "XX.STA02.10"])

    await client.prepare(selection, date(2024, 1, 1), date(2024, 1, 3))

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
