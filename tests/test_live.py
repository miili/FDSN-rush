"""Checks against real FDSN servers. Opt in with ``FDSN_RUSH_LIVE=1 pytest``."""

from __future__ import annotations

import os
from datetime import date

import pytest

from fdsn_rush.client import FDSNClient
from fdsn_rush.utils import NSL

pytestmark = pytest.mark.skipif(
    os.environ.get("FDSN_RUSH_LIVE") != "1",
    reason="needs network access, set FDSN_RUSH_LIVE=1",
)

DAY = date(2024, 1, 1), date(2024, 1, 2)


def _locations(client: FDSNClient) -> set[str]:
    return {
        channel.nsl.location
        for station in client.available_stations
        for channel in station.channels
    }


@pytest.mark.parametrize("url", ["https://service.iris.edu", "https://geofon.gfz.de"])
async def test_wildcard_location_matches_all(url: str) -> None:
    """A wildcard plus an explicit location must not narrow to the explicit one."""
    nsl = "IU.ANMO" if "iris" in url else "GE.APE"
    client = FDSNClient(url=url)
    await client.prepare([NSL.parse(f"{nsl}."), NSL.parse(f"{nsl}.00")], *DAY)

    locations = _locations(client)
    assert locations
    if "iris" in url:
        # IU.ANMO has 00, 10, 20, ...; ",00" would return 00 only
        assert {"00", "10"} <= locations
