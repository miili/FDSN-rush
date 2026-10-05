"""Checks against real FDSN servers. Opt in with ``FDSN_RUSH_LIVE=1 pytest``."""

from __future__ import annotations

import math
import os
from datetime import date

import pytest

from fdsn_rush.client import FDSNClient
from fdsn_rush.models.station import Channel, Stations
from fdsn_rush.selection import (
    GeographicSelection,
    RadiusSelection,
    StationSelection,
)
from fdsn_rush.utils import NSL

pytestmark = pytest.mark.skipif(
    os.environ.get("FDSN_RUSH_LIVE") != "1",
    reason="needs network access, set FDSN_RUSH_LIVE=1",
)

DAY = date(2024, 1, 1), date(2024, 1, 2)
# INGV serves the Campi Flegrei network (IV)
INGV = "https://webservices.ingv.it"


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
    selection = StationSelection(stations=[f"{nsl}.", f"{nsl}.00"])
    await client.prepare(selection, *DAY)

    locations = _locations(client)
    assert locations
    if "iris" in url:
        # IU.ANMO has 00, 10, 20, ...; ",00" would return 00 only
        assert {"00", "10"} <= locations


async def test_metadata_post() -> None:
    client = FDSNClient(url="https://geofon.gfz.de")
    data = await client.download_metadata([NSL.parse("GE.APE")], *DAY)

    assert "FDSNStationXML" in data


def _distance_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    cos_d = math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(
        lat2
    ) * math.cos(lon2 - lon1)
    return math.degrees(math.acos(min(1.0, cos_d)))


def _channels(stations: Stations) -> list[Channel]:
    return [channel for station in stations for channel in station.channels]


def _nsls(stations: Stations) -> list[NSL]:
    return [station.nsl for station in stations]


async def test_station_selection() -> None:
    selection = StationSelection(stations=["IV.CPOZ", "ZZ"])
    stations = await selection.get_available_stations(FDSNClient(url=INGV), *DAY)

    # ZZ does not exist and must not fail the IV request
    assert _nsls(stations) == [NSL("IV", "CPOZ", "")]


async def test_geographic_selection() -> None:
    selection = GeographicSelection()
    stations = await selection.get_available_stations(FDSNClient(url=INGV), *DAY)

    assert NSL("IV", "CPOZ", "") in stations
    for channel in _channels(stations):
        assert selection.minlatitude <= channel.lat <= selection.maxlatitude
        assert selection.minlongitude <= channel.lon <= selection.maxlongitude


async def test_radius_selection() -> None:
    disk = RadiusSelection()
    ring = RadiusSelection(minradius=0.05, maxradius=0.15)
    client = FDSNClient(url=INGV)

    disk_stations = await disk.get_available_stations(client, *DAY)
    ring_stations = await ring.get_available_stations(client, *DAY)

    assert NSL("IV", "CPOZ", "") in disk_stations
    assert ring_stations.n_stations
    assert set(_nsls(ring_stations)) < set(_nsls(disk_stations))
    for channel in _channels(ring_stations):
        distance = _distance_deg(
            ring.latitude, ring.longitude, channel.lat, channel.lon
        )
        assert ring.minradius <= distance <= ring.maxradius + 1e-3


async def test_exclude_stations() -> None:
    selection = RadiusSelection(exclude_stations=["IV.CPOZ", "IV.CS*"])
    stations = await selection.get_available_stations(FDSNClient(url=INGV), *DAY)

    assert stations.n_stations
    assert NSL("IV", "CPOZ", "") not in stations
    assert NSL("IV", "CS*", "") not in stations


async def test_area_selection_networks() -> None:
    client = FDSNClient(url=INGV)
    all_networks = await RadiusSelection().get_available_stations(client, *DAY)
    iv_only = await RadiusSelection(networks=["IV"]).get_available_stations(
        client, *DAY
    )

    assert {nsl.network for nsl in _nsls(all_networks)} > {"IV"}
    assert iv_only.n_stations
    assert {nsl.network for nsl in _nsls(iv_only)} == {"IV"}


async def test_include_restricted() -> None:
    selection = GeographicSelection(include_restricted=False)
    stations = await selection.get_available_stations(FDSNClient(url=INGV), *DAY)
    assert stations.n_stations
