from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from conftest import STATION_TEXT

from fdsn_rush.models.station import Channel, Stations, parse_stations
from fdsn_rush.utils import NSL


def test_parse_stations(stations: Stations) -> None:
    assert stations.n_stations == 3
    assert [s.nsl.pretty for s in stations] == ["XX.STA01.", "XX.STA02.", "XX.STA03."]

    sta01 = stations.get_station(NSL("XX", "STA01", ""))
    # LDO is an auxiliary (state of health) channel and dropped
    assert sta01.get_channel_codes() == {"HHE", "HHN", "HHZ", "LHZ"}


def test_parse_stations_keep_aux() -> None:
    stations = parse_stations(STATION_TEXT, ignore_aux=False)
    sta01 = stations.get_station(NSL("XX", "STA01", ""))
    assert "LDO" in sta01.get_channel_codes()


def test_parse_stations_empty() -> None:
    with pytest.raises(ValueError, match="No valid channel data"):
        parse_stations("#just a header\n")


def test_channel_from_line_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid line format"):
        Channel.from_line("XX|STA01||HHZ|52.0")


def test_get_station_missing(stations: Stations) -> None:
    with pytest.raises(ValueError, match="not found"):
        stations.get_station(NSL("YY", "STA01", ""))


def test_sds_path(stations: Stations) -> None:
    channel = stations.get_station(NSL("XX", "STA01", "")).channels[0]
    assert channel.sds_path(date(2024, 1, 5)) == Path(
        "2024/XX/STA01/HHE.D/XX.STA01..HHE.D.2024.005"
    )


def test_get_channels(stations: Stations) -> None:
    sta01 = stations.get_station(NSL("XX", "STA01", ""))
    day = date(2024, 1, 1)

    assert {c.code for c in sta01.get_channels(day)} == {"HHE", "HHN", "HHZ", "LHZ"}
    assert {c.code for c in sta01.get_channels(day, "HH[ZNE]")} == {
        "HHE",
        "HHN",
        "HHZ",
    }
    assert {c.code for c in sta01.get_channels(day, "*", 50.0, 200.0)} == {
        "HHE",
        "HHN",
        "HHZ",
    }
    # Before the channel epoch started
    assert sta01.get_channels(date(2019, 12, 31)) == []


def test_get_channels_epoch_end(stations: Stations) -> None:
    sta03 = stations.get_station(NSL("XX", "STA03", ""))
    assert len(sta03.get_channels(date(2024, 1, 1))) == 1
    assert sta03.get_channels(date(2024, 1, 2)) == []


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        (NSL("XX", "STA01", ""), True),
        (NSL("XX", "", ""), True),
        (NSL("XX", "STA0*", ""), True),
        (NSL("XX", "STA04", ""), False),
        (NSL("YY", "", ""), False),
        ("XX.STA01.", False),
    ],
)
def test_stations_contains(
    stations: Stations, selector: object, expected: bool
) -> None:
    assert (selector in stations) is expected


@pytest.mark.parametrize(
    ("selector", "removed", "kept"),
    [
        (NSL("XX", "STA02", ""), ["STA02"], ["STA01", "STA03"]),
        (NSL("XX", "STA0[13]", ""), ["STA01", "STA03"], ["STA02"]),
        (NSL("XX", "", ""), ["STA01", "STA02", "STA03"], []),
        (NSL("YY", "", ""), [], ["STA01", "STA02", "STA03"]),
    ],
)
def test_stations_remove(
    stations: Stations, selector: NSL, removed: list[str], kept: list[str]
) -> None:
    assert [s.nsl.station for s in stations.remove(selector)] == removed
    assert [s.nsl.station for s in stations] == kept
    assert selector not in stations


def test_stations_extend_skips_known(stations: Stations) -> None:
    sta01 = parse_stations(STATION_TEXT)
    sta01.stations = sta01.stations[:1]

    stations.extend(sta01)
    stations.extend(parse_stations(STATION_TEXT))

    assert [s.nsl.station for s in stations] == ["STA01", "STA02", "STA03"]
