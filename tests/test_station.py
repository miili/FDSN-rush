from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from conftest import STATION_TEXT

from fdsn_rush.models.station import Channel, Stations, parse_stations
from fdsn_rush.utils import _NSL


def test_parse_stations(stations: Stations) -> None:
    assert stations.n_stations == 3
    assert [s.nsl.pretty for s in stations] == ["XX.STA01.", "XX.STA02.", "XX.STA03."]

    sta01 = stations.get_station(_NSL("XX", "STA01", ""))
    # LDO is an auxiliary (state of health) channel and dropped
    assert sta01.get_channel_codes() == {"HHE", "HHN", "HHZ", "LHZ"}


def test_parse_stations_keep_aux() -> None:
    stations = parse_stations(STATION_TEXT, ignore_aux=False)
    sta01 = stations.get_station(_NSL("XX", "STA01", ""))
    assert "LDO" in sta01.get_channel_codes()


def test_parse_stations_empty() -> None:
    with pytest.raises(ValueError, match="No valid channel data"):
        parse_stations("#just a header\n")


def test_channel_from_line_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid line format"):
        Channel.from_line("XX|STA01||HHZ|52.0")


def test_get_station_missing(stations: Stations) -> None:
    with pytest.raises(ValueError, match="not found"):
        stations.get_station(_NSL("YY", "STA01", ""))


def test_sds_path(stations: Stations) -> None:
    channel = stations.get_station(_NSL("XX", "STA01", "")).channels[0]
    assert channel.sds_path(date(2024, 1, 5)) == Path(
        "2024/XX/STA01/HHE.D/XX.STA01..HHE.D.2024.005"
    )


def test_get_channels(stations: Stations) -> None:
    sta01 = stations.get_station(_NSL("XX", "STA01", ""))
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
    sta03 = stations.get_station(_NSL("XX", "STA03", ""))
    assert len(sta03.get_channels(date(2024, 1, 1))) == 1
    assert sta03.get_channels(date(2024, 1, 2)) == []
