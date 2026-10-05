from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from fdsn_rush import utils
from fdsn_rush.utils import (
    NSL,
    NSLC,
    Date,
    FilePath,
    NSLType,
    date_today,
    human_readable_bytes,
    wait_for_path,
)

FILE_PATH_ADAPTER = TypeAdapter(FilePath)
NSL_ADAPTER = TypeAdapter(NSLType)
DATE_ADAPTER = TypeAdapter(Date)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("XX.STA01.00", NSL("XX", "STA01", "00")),
        ("XX.STA01", NSL("XX", "STA01", "")),
        ("XX", NSL("XX", "", "")),
        ("XX.STA01.00.HHZ", NSL("XX", "STA01", "00")),
        (["XX", "STA01", ""], NSL("XX", "STA01", "")),
    ],
)
def test_nsl_parse(value: str | list[str], expected: NSL) -> None:
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
        (NSL("XX", "", ""), NSL("XX", "STA01", "00"), True),
        (NSL("YY", "", ""), NSL("XX", "STA01", "00"), False),
        (NSL("XX", "STA01", ""), NSL("XX", "STA01", "00"), True),
        (NSL("XX", "STA02", ""), NSL("XX", "STA01", "00"), False),
        (NSL("XX", "STA*", ""), NSL("XX", "STA01", "00"), True),
        (NSL("XX", "STA01", "10"), NSL("XX", "STA01", "00"), False),
    ],
)
def test_nsl_match(selector: NSL, nsl: NSL, expected: bool) -> None:
    assert selector.match(nsl) is expected


def test_nslc() -> None:
    nslc = NSLC.from_string("XX.STA01..HHZ")
    assert nslc == NSLC("XX", "STA01", "", "HHZ")
    assert nslc.pretty == "XX.STA01..HHZ"
    assert NSLC.from_nsl(NSL("XX", "STA01", ""), "HHZ") == nslc

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


def test_file_path_expands_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".eidatoken").touch()

    assert FILE_PATH_ADAPTER.validate_python("~/.eidatoken") == tmp_path / ".eidatoken"
    with pytest.raises(ValidationError, match="does not exist"):
        FILE_PATH_ADAPTER.validate_python("~/missing")


def test_report(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    utils.report("key", "value")
    assert capsys.readouterr().out == ""  # silent unless --non-interactive

    monkeypatch.setattr(utils, "NON_INTERACTIVE", True)
    utils.report("error", "line one\n  line two")
    assert capsys.readouterr().out == "error: line one line two\n"
