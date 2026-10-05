from __future__ import annotations

from datetime import date

import pytest
from conftest import FakeFDSN
from pydantic import TypeAdapter, ValidationError

from fdsn_rush.client import FDSNClient, StationQueryError
from fdsn_rush.models.station import Stations
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


def _station_codes(stations: Stations) -> list[str]:
    return [station.nsl.station for station in stations]


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


def test_exclude_stations_parses_and_serializes() -> None:
    selection = SELECTION_ADAPTER.validate_python(
        {"selection": "RadiusSelection", "exclude_stations": ["IV.CPOZ", "IV.CPOZ."]}
    )
    assert selection.exclude_stations == {NSL("IV", "CPOZ", "")}
    assert selection.model_dump()["exclude_stations"] == {"IV.CPOZ."}


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
        (GeographicSelection, {"networks": ["XXX"]}),
        (RadiusSelection, {"latitude": -90.5}),
        (RadiusSelection, {"maxradius": 0.0}),
        (RadiusSelection, {"minradius": 0.2, "maxradius": 0.1}),
        (RadiusSelection, {"networks": ["XXX"]}),
        (StationSelection, {"stations": []}),
        (StationSelection, {"stations": ["XXX.STA01"]}),
        # servers answer `[...]` with 400
        (StationSelection, {"stations": ["XX.STA0[12]"]}),
        (GeographicSelection, {"networks": ["X[XY]"]}),
        # network codes are explicit, so requests never overlap
        (StationSelection, {"stations": ["X?.STA01"]}),
        (StationSelection, {"stations": ["*.STA01"]}),
        (StationSelection, {"stations": [".STA01"]}),
        (GeographicSelection, {"networks": ["X?"]}),
        (RadiusSelection, {"networks": ["*"]}),
        (RadiusSelection, {"networks": [""]}),
    ],
)
def test_invalid_selection(model: type, data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(data)


async def test_station_selection_requests_each_network(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX.STA01", "YY.STA01", "XX.STA02."])

    stations = await selection.get_available_stations(client, *DAY)

    assert len(fake_fdsn.station_requests) == 2
    xx, yy = fake_fdsn.station_requests
    assert xx["options"] == {"level": "channel", "format": "text", "nodata": "404"}
    assert [line[:4] for line in xx["selection"]] == [
        ["XX", "STA01", "*", "*"],
        ["XX", "STA02", "*", "*"],
    ]
    assert [line[:4] for line in yy["selection"]] == [["YY", "STA01", "*", "*"]]
    # YY is unknown to the server (404) and does not fail the XX request
    assert _station_codes(stations) == ["STA01", "STA02"]


async def test_station_selection_nothing_found(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["YY"])

    stations = await selection.get_available_stations(client, *DAY)

    assert stations.n_stations == 0


async def test_geographic_selection(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = GeographicSelection(
        minlatitude=40.7, maxlatitude=40.95, minlongitude=13.95, maxlongitude=14.35
    )

    stations = await selection.get_available_stations(client, *DAY)

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
    assert stations.n_stations == 3


async def test_radius_selection(fake_fdsn: FakeFDSN) -> None:
    client = FDSNClient(url=fake_fdsn.url)

    await RadiusSelection().get_available_stations(client, *DAY)
    await RadiusSelection(minradius=0.05, maxradius=0.2).get_available_stations(
        client, *DAY
    )

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


@pytest.mark.parametrize("model", [GeographicSelection, RadiusSelection])
async def test_area_selection_networks(fake_fdsn: FakeFDSN, model: type) -> None:
    client = FDSNClient(url=fake_fdsn.url)

    stations = await model(networks=["YY", "XX", "YY"]).get_available_stations(
        client, *DAY
    )

    (request,) = fake_fdsn.station_requests
    assert request["selection"] == [
        ["XX", *ALL_LINE[1:]],
        ["YY", *ALL_LINE[1:]],
    ]
    assert stations.n_stations == 3


@pytest.mark.parametrize(
    ("exclude", "expected"),
    [
        ([], ["STA01", "STA02", "STA03"]),
        (["XX.STA02"], ["STA01", "STA03"]),
        (["XX.STA0[12]", "XX.STA03"], []),
        (["XX.STA04", "YY"], ["STA01", "STA02", "STA03"]),
    ],
)
@pytest.mark.parametrize("model", [StationSelection, GeographicSelection])
async def test_exclude_stations(
    fake_fdsn: FakeFDSN, model: type, exclude: list[str], expected: list[str]
) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = model(exclude_stations=exclude)
    if model is StationSelection:
        selection.stations = [NSL("XX", "", "")]

    stations = await selection.get_available_stations(client, *DAY)

    assert _station_codes(stations) == expected


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (StationSelection, {"stations": ["XX"]}),
        (GeographicSelection, {}),
        (RadiusSelection, {}),
    ],
)
@pytest.mark.parametrize(
    ("include_restricted", "expected"), [(True, None), (False, "FALSE")]
)
async def test_include_restricted(
    fake_fdsn: FakeFDSN,
    model: type,
    kwargs: dict[str, object],
    include_restricted: bool,
    expected: str | None,
) -> None:
    client = FDSNClient(url=fake_fdsn.url)
    selection = model(include_restricted=include_restricted, **kwargs)

    await selection.get_available_stations(client, *DAY)

    (request,) = fake_fdsn.station_requests
    # TRUE is the API default and not sent
    assert request["options"].get("includerestricted") == expected


def test_options_never_scientific() -> None:
    selection = RadiusSelection(latitude=0.00001, longitude=-0.0, maxradius=1e-05)

    ((_, options, _),) = selection._requests()

    assert options["latitude"] == "0.00001"
    assert options["longitude"] == "0"
    assert options["maxradius"] == "0.00001"


async def test_station_selection_deduplicates(fake_fdsn: FakeFDSN) -> None:
    """Overlapping lines in one request must not duplicate stations."""
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX.STA0*", "XX.STA01", "XX"])

    stations = await selection.get_available_stations(client, *DAY)

    assert _station_codes(stations) == ["STA01", "STA02", "STA03"]


@pytest.mark.parametrize("status", [404, 204])
async def test_no_stations_is_no_error(fake_fdsn: FakeFDSN, status: int) -> None:
    fake_fdsn.station_errors = {"XX": [status]}
    client = FDSNClient(url=fake_fdsn.url)

    stations = await StationSelection(stations=["XX"]).get_available_stations(
        client, *DAY
    )

    assert stations.n_stations == 0
    assert len(fake_fdsn.station_requests) == 1


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_transient_error_is_retried(fake_fdsn: FakeFDSN, status: int) -> None:
    fake_fdsn.station_errors = {"XX": [status, status]}
    client = FDSNClient(url=fake_fdsn.url)

    stations = await StationSelection(stations=["XX"]).get_available_stations(
        client, *DAY
    )

    assert stations.n_stations == 3
    assert len(fake_fdsn.station_requests) == 3


@pytest.mark.parametrize(
    ("errors", "n_requests"),
    [
        ([503, 503, 503], 3),  # retried until the attempts run out
        ([400], 1),  # client errors are not retried
        ([401], 1),
    ],
)
async def test_failed_query_raises_with_other_stations(
    fake_fdsn: FakeFDSN, errors: list[int], n_requests: int
) -> None:
    fake_fdsn.station_errors = {"XX": errors}
    client = FDSNClient(url=fake_fdsn.url)
    selection = StationSelection(stations=["XX", "YY", "ZZ.STA01"])

    with pytest.raises(StationQueryError, match="network XX") as error:
        await selection.get_available_stations(client, *DAY)

    assert error.value.failed == ["network XX"]
    xx_requests = [
        r for r in fake_fdsn.station_requests if r["selection"][0][0] == "XX"
    ]
    assert len(xx_requests) == n_requests
    # YY and ZZ were still queried
    assert len(fake_fdsn.station_requests) == n_requests + 2


async def test_unreachable_server_raises() -> None:
    client = FDSNClient(url="http://127.0.0.1:1", timeout=1.0)

    with pytest.raises(StationQueryError) as error:
        await StationSelection(stations=["XX"]).get_available_stations(client, *DAY)

    assert error.value.failed == ["network XX"]
    assert error.value.stations.n_stations == 0
