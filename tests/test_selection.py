from __future__ import annotations

from datetime import date

import pytest
from conftest import FakeFDSN
from pydantic import TypeAdapter, ValidationError

from fdsn_rush.client import FDSNClient
from fdsn_rush.selection import (
    CAMPI_FLEGREI,
    GeographicSelection,
    RadiusSelection,
    SelectionType,
    StationSelection,
)
from fdsn_rush.utils import NSL

DAY = date(2024, 1, 1), date(2024, 1, 2)
ALL_LINE = ["*", "*", "*", "*", "2024-01-01T00:00:00", "2024-01-02T00:00:00"]
SELECTION_ADAPTER = TypeAdapter(SelectionType)


def test_available_stations_needs_prepare() -> None:
    with pytest.raises(RuntimeError, match="prepare"):
        _ = StationSelection().available_stations


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"selection": "StationSelection"}, StationSelection),
        ({"selection": "GeographicSelection"}, GeographicSelection),
        ({"selection": "RadiusSelection"}, RadiusSelection),
    ],
)
def test_discriminated_union(data: dict[str, str], expected: type) -> None:
    assert type(SELECTION_ADAPTER.validate_python(data)) is expected


def test_station_selection_parses_and_serializes() -> None:
    selection = SELECTION_ADAPTER.validate_python(
        {"selection": "StationSelection", "stations": ["XX.STA01", "YY"]}
    )
    assert selection.stations == [NSL("XX", "STA01", ""), NSL("YY", "", "")]
    assert selection.model_dump()["stations"] == ["XX.STA01.", "YY.."]


def test_defaults_contain_campi_flegrei() -> None:
    box = GeographicSelection()
    lat, lon = CAMPI_FLEGREI
    assert box.minlatitude < lat < box.maxlatitude
    assert box.minlongitude < lon < box.maxlongitude
    assert box.maxlatitude - box.minlatitude < 1.0
    assert box.maxlongitude - box.minlongitude < 1.0

    radius = RadiusSelection()
    assert (radius.latitude, radius.longitude) == CAMPI_FLEGREI
    assert radius.maxradius < 1.0


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (GeographicSelection, {"minlatitude": 41.0, "maxlatitude": 40.0}),
        (GeographicSelection, {"minlongitude": 14.3, "maxlongitude": 14.3}),
        (GeographicSelection, {"maxlatitude": 91.0}),
        (GeographicSelection, {"minlongitude": -181.0}),
        (RadiusSelection, {"latitude": -90.5}),
        (RadiusSelection, {"maxradius": 0.0}),
        (RadiusSelection, {"minradius": 0.2, "maxradius": 0.1}),
        (StationSelection, {"stations": []}),
        (StationSelection, {"stations": ["XXX.STA01"]}),
    ],
)
def test_invalid_selection(model: type, data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(data)


async def test_station_selection_requests_each_network(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX.STA01", "YY.STA01", "XX.STA02."])

    nsls = await selection.prepare(client, *DAY)

    assert len(fake_fdsn.station_requests) == 2
    xx, yy = fake_fdsn.station_requests
    assert xx["options"] == {"level": "channel", "format": "text", "nodata": "404"}
    assert [line[:4] for line in xx["selection"]] == [
        ["XX", "STA01", "*", "*"],
        ["XX", "STA02", "*", "*"],
    ]
    assert [line[:4] for line in yy["selection"]] == [["YY", "STA01", "*", "*"]]
    # the fake server returns the same inventory for every request
    assert nsls == [station.nsl for station in selection.available_stations]
    assert selection.available_stations.n_stations == 6


async def test_station_selection_missing_network(fake_fdsn: FakeFDSN) -> None:
    fake_fdsn.nodata_networks = {"YY"}
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX", "YY"])

    nsls = await selection.prepare(client, *DAY)

    assert len(fake_fdsn.station_requests) == 2
    assert nsls == [NSL("XX", f"STA0{i}", "") for i in (1, 2, 3)]


async def test_station_selection_all_missing(fake_fdsn: FakeFDSN) -> None:
    fake_fdsn.nodata_networks = {"YY"}
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["YY"])

    assert await selection.prepare(client, *DAY) == []
    assert selection.available_stations.n_stations == 0


async def test_geographic_selection(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = GeographicSelection(
        minlatitude=40.7, maxlatitude=40.95, minlongitude=13.95, maxlongitude=14.35
    )

    nsls = await selection.prepare(client, *DAY)

    (request,) = fake_fdsn.station_requests
    assert request["options"] == {
        "level": "channel",
        "format": "text",
        "nodata": "404",
        "minlatitude": "40.7",
        "maxlatitude": "40.95",
        "minlongitude": "13.95",
        "maxlongitude": "14.35",
    }
    assert request["selection"] == [ALL_LINE]
    assert len(nsls) == 3


async def test_radius_selection(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)

    await RadiusSelection().prepare(client, *DAY)
    await RadiusSelection(minradius=0.05, maxradius=0.2).prepare(client, *DAY)

    default, ring = fake_fdsn.station_requests
    assert default["options"] == {
        "level": "channel",
        "format": "text",
        "nodata": "404",
        "latitude": str(CAMPI_FLEGREI[0]),
        "longitude": str(CAMPI_FLEGREI[1]),
        "maxradius": "0.15",
    }
    assert default["selection"] == [ALL_LINE]
    assert ring["options"]["minradius"] == "0.05"
    assert ring["options"]["maxradius"] == "0.2"


async def test_prepare_twice_does_not_duplicate(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = GeographicSelection()

    await selection.prepare(client, *DAY)
    await selection.prepare(client, *DAY)

    assert selection.available_stations.n_stations == 3
