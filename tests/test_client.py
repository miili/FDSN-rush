from __future__ import annotations

from datetime import date

from conftest import FakeFDSN

from fdsn_rush.client import FDSNClient, _fdsn_time
from fdsn_rush.utils import NSL


def test_fdsn_time() -> None:
    assert _fdsn_time(date(2024, 1, 1)) == "2024-01-01T00:00:00"


async def test_prepare_requests_each_network_once(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = [NSL.parse("XX.STA01"), NSL.parse("YY.STA01"), NSL.parse("XX.STA02")]

    await client.prepare(selection, date(2024, 1, 1), date(2024, 1, 3))

    networks = [req["network"] for req in fake_fdsn.station_requests]
    assert sorted(networks) == ["XX", "YY"]
    request = fake_fdsn.station_requests[0]
    assert request["starttime"] == "2024-01-01T00:00:00"
    assert request["endtime"] == "2024-01-03T00:00:00"


async def test_prepare_wildcard_selection_omits_parameter(
    fake_fdsn: FakeFDSN,
) -> None:
    """An empty location is a wildcard, ",00" would only match blank and 00."""
    client = FDSNClient(url=fake_fdsn.url)
    selection = [NSL.parse("XX.STA01."), NSL.parse("XX.STA01.00")]

    await client.prepare(selection, date(2024, 1, 1), date(2024, 1, 3))

    (request,) = fake_fdsn.station_requests
    assert "location" not in request
    assert request["station"] == "STA01"


async def test_prepare_joins_explicit_codes(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = [NSL.parse("XX.STA02.10"), NSL.parse("XX.STA01.00")]

    await client.prepare(selection, date(2024, 1, 1), date(2024, 1, 3))

    (request,) = fake_fdsn.station_requests
    assert request["station"] == "STA01,STA02"
    assert request["location"] == "00,10"
