from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from fdsn_rush.utils import (
    _NSL,
    NSL,
    NSLC,
    Date,
    date_today,
    human_readable_bytes,
    wait_for_path,
)

NSL_ADAPTER = TypeAdapter(NSL)
DATE_ADAPTER = TypeAdapter(Date)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("XX.STA01.00", _NSL("XX", "STA01", "00")),
        ("XX.STA01", _NSL("XX", "STA01", "")),
        ("XX", _NSL("XX", "", "")),
        ("XX.STA01.00.HHZ", _NSL("XX", "STA01", "00")),
        (["XX", "STA01", ""], _NSL("XX", "STA01", "")),
    ],
)
def test_nsl_parse(value: str | list[str], expected: _NSL) -> None:
    assert NSL_ADAPTER.validate_python(value) == expected


@pytest.mark.parametrize("value", ["", "XXX.STA01", "XX.STATION", "XX.STA.000", 42])
def test_nsl_parse_invalid(value: str | int) -> None:
    with pytest.raises(ValidationError):
        NSL_ADAPTER.validate_python(value)


def test_nsl_serialize() -> None:
    nsl = NSL_ADAPTER.validate_python("XX.STA01.00")
    assert NSL_ADAPTER.dump_python(nsl, mode="json") == "XX.STA01.00"
    assert nsl.pretty == "XX.STA01.00"


@pytest.mark.parametrize(
    ("selector", "nsl", "expected"),
    [
        (_NSL("XX", "", ""), _NSL("XX", "STA01", "00"), True),
        (_NSL("YY", "", ""), _NSL("XX", "STA01", "00"), False),
        (_NSL("XX", "STA01", ""), _NSL("XX", "STA01", "00"), True),
        (_NSL("XX", "STA02", ""), _NSL("XX", "STA01", "00"), False),
        (_NSL("XX", "STA*", ""), _NSL("XX", "STA01", "00"), True),
        (_NSL("XX", "STA01", "10"), _NSL("XX", "STA01", "00"), False),
    ],
)
def test_nsl_match(selector: _NSL, nsl: _NSL, expected: bool) -> None:
    assert selector.match(nsl) is expected


def test_nslc() -> None:
    nslc = NSLC.from_string("XX.STA01..HHZ")
    assert nslc == NSLC("XX", "STA01", "", "HHZ")
    assert nslc.pretty == "XX.STA01..HHZ"
    assert NSLC.from_nsl(_NSL("XX", "STA01", ""), "HHZ") == nslc

    with pytest.raises(ValueError, match="Invalid NSLC"):
        NSLC.from_string("XX.STA01")


def test_date_aliases() -> None:
    today = date_today()
    yesterday = today - timedelta(days=1)

    assert DATE_ADAPTER.validate_python("today") == today
    assert DATE_ADAPTER.validate_python("yesterday") == yesterday
    assert DATE_ADAPTER.validate_python("2024-01-02") == date(2024, 1, 2)

    assert DATE_ADAPTER.dump_python(today, mode="json") == "today"
    assert DATE_ADAPTER.dump_python(yesterday, mode="json") == "yesterday"
    assert DATE_ADAPTER.dump_python(date(2024, 1, 2), mode="json") == "2024-01-02"


def test_human_readable_bytes() -> None:
    assert human_readable_bytes(1024) == "1.0KiB"
    assert human_readable_bytes(1000, decimal=True) == "1.0KB"


async def test_wait_for_path(tmp_path: Path) -> None:
    existing = tmp_path / "exists"
    existing.touch()
    await wait_for_path(existing, timeout=0.1)

    with pytest.raises(FileNotFoundError):
        await wait_for_path(tmp_path / "missing", timeout=0.1)
