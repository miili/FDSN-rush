from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import click
import numpy as np
import pytest
from pyrocko import io, trace
from typer.testing import CliRunner

from fdsn_rush.app import app
from fdsn_rush.convert import Rename, convert_sds
from fdsn_rush.utils import NSLC

START = datetime(2024, 1, 1, 1, tzinfo=UTC)


def _save_trace(
    path: Path,
    station: str,
    start: datetime,
    seconds: int,
    network: str = "XX",
    channel: str = "HHZ",
) -> None:
    tr = trace.Trace(
        network,
        station,
        "",
        channel,
        deltat=1.0,
        tmin=start.timestamp(),
        ydata=np.arange(seconds, dtype=np.int32),
    )
    io.save([tr], str(path))


def _n_samples(path: Path) -> int:
    return sum(tr.ydata.size for tr in io.load(str(path)))


async def test_convert_all_files(tmp_path: Path) -> None:
    """Every input file is converted, including the last batch of workers."""
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    start = datetime(2024, 1, 1, 1, tzinfo=UTC)
    for i in range(5):
        _save_trace(input_dir / f"file{i}.mseed", f"STA0{i}", start, 600)

    output = tmp_path / "sds"
    await convert_sds(input_dir, output, n_workers=2)

    files = sorted(p.name for p in output.glob("**/*.D.*"))
    assert files == [f"XX.STA0{i}..HHZ.D.2024.001" for i in range(5)]


async def test_convert_splits_at_midnight(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    # 24 hours from noon to noon, spanning two days
    _save_trace(
        input_dir / "noon.mseed", "STA01", datetime(2024, 1, 1, 12, tzinfo=UTC), 86400
    )

    output = tmp_path / "sds"
    await convert_sds(input_dir, output, [Rename.parse("=YY")])

    day1 = output / "2024/YY/STA01/HHZ.D/YY.STA01..HHZ.D.2024.001"
    day2 = output / "2024/YY/STA01/HHZ.D/YY.STA01..HHZ.D.2024.002"
    assert _n_samples(day1) == 43200
    assert _n_samples(day2) == 43200


def test_rename_parse() -> None:
    rename = Rename.parse("1X..=2D..")
    assert rename.source == NSLC("1X", "", "", "")
    assert rename.target == NSLC("2D", "", "", "")
    assert Rename.parse("...EN1=...ENE").target == NSLC("", "", "", "ENE")
    assert Rename.parse("..00.=..--.").target == NSLC("", "", "--", "")


@pytest.mark.parametrize(
    "rule",
    ["2D", "XX.=2D.STA.00.HHZ.X", "=ABC", "=.STATION", "=...HHZZ", "=.ST*", "=..", ""],
)
def test_rename_parse_invalid(rule: str) -> None:
    with pytest.raises(ValueError, match="rename"):
        Rename.parse(rule)


def _trace(network="1X", station="STA01", location="", channel="EN1") -> trace.Trace:
    return trace.Trace(network, station, location, channel, ydata=np.zeros(1))


def test_rename_apply_chained() -> None:
    renames = [Rename.parse("1X..=2D.."), Rename.parse("2D...EN1=...ENE")]
    tr = _trace()
    for rename in renames:
        rename.apply(tr)
    assert tr.nslc_id == ("2D", "STA01", "", "ENE")


def test_rename_apply_patterns() -> None:
    tr = _trace(location="00", channel="EHZ")
    Rename.parse("..--.=XX").apply(tr)  # only the blank location
    assert tr.network == "1X"
    Rename.parse(".STA0?.00.EH*=..--").apply(tr)
    assert tr.nslc_id == ("1X", "STA01", "", "EHZ")
    Rename.parse("..--.=YY").apply(tr)
    assert tr.network == "YY"


async def test_convert_rename_chained(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    for i, channel in enumerate(["EN1", "EN2", "ENZ"]):
        _save_trace(input_dir / f"{i}.mseed", "STA01", START, 600, "1X", channel)

    output = tmp_path / "sds"
    renames = [Rename.parse("1X..=2D.."), Rename.parse("...EN1=...ENE")]
    await convert_sds(input_dir, output, renames)

    files = sorted(p.name for p in output.glob("**/*.D.*"))
    assert files == [f"2D.STA01..{cha}.D.2024.001" for cha in ["EN2", "ENE", "ENZ"]]
    path = output / "2024/2D/STA01/ENE.D/2D.STA01..ENE.D.2024.001"
    assert io.load(str(path))[0].nslc_id == ("2D", "STA01", "", "ENE")


async def test_convert_rename_merge_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    _save_trace(input_dir / "a.mseed", "STA01", START, 600)
    _save_trace(input_dir / "b.mseed", "STA02", START, 600)

    with caplog.at_level(logging.WARNING):
        await convert_sds(input_dir, tmp_path / "sds", [Rename.parse(".STA02=.STA01")])
    assert "XX.STA01..HHZ holds data from XX.STA01..HHZ, XX.STA02..HHZ" in caplog.text


def test_cli_rename_invalid(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["convert", str(tmp_path), str(tmp_path / "sds"), "--rename", "=ABC"]
    )
    assert result.exit_code == 2
    # Rich styles the output on CI (GITHUB_ACTIONS forces a terminal)
    assert "Invalid value for --rename" in click.unstyle(result.output)
