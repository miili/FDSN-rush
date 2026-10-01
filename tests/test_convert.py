from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from pyrocko import io, trace

from fdsn_rush.convert import convert_sds


def _save_trace(path: Path, station: str, start: datetime, seconds: int) -> None:
    tr = trace.Trace(
        "XX",
        station,
        "",
        "HHZ",
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
    await convert_sds(input_dir, output, network="YY")

    day1 = output / "2024/YY/STA01/HHZ.D/YY.STA01..HHZ.D.2024.001"
    day2 = output / "2024/YY/STA01/HHZ.D/YY.STA01..HHZ.D.2024.002"
    assert _n_samples(day1) == 43200
    assert _n_samples(day2) == 43200
