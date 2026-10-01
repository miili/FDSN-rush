from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import HttpUrl

from fdsn_rush.remote_log import RemoteLog
from fdsn_rush.utils import NSLC

NSLC_ = NSLC("XX", "STA01", "", "HHZ")
DAY = date(2024, 1, 1)
REMOTE = HttpUrl("https://geofon.gfz.de")


def test_remote_log_without_file() -> None:
    log = RemoteLog()
    log.add_error(NSLC_, DAY, REMOTE, 404)
    assert log.get_error(NSLC_, DAY, REMOTE) == 404


def test_remote_log_persists(tmp_path: Path) -> None:
    log_file = tmp_path / "sub" / "remote_errors.log"
    log = RemoteLog()
    log.set_logfile(log_file)

    log.add_error(NSLC_, DAY, REMOTE, 404)
    # Only codes in LOG_ERROR_CODES are recorded, transient errors are retried
    log.add_error(NSLC_, date(2024, 1, 2), REMOTE, 503)

    assert log.n_errors == 1
    assert log.get_error(NSLC_, DAY, REMOTE) == 404
    assert log.get_error(NSLC_, date(2024, 1, 2), REMOTE) is None

    reloaded = RemoteLog(log_file)
    assert reloaded.n_errors == 1
    assert reloaded.get_error(NSLC_, DAY, REMOTE) == 404
    assert reloaded.get_error(NSLC_, DAY, HttpUrl("https://other.org")) is None
