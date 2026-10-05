"""End-to-end tests of ``fdsn-rush download --non-interactive`` against the fake server."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from conftest import FakeFDSN
from pydantic import HttpUrl
from typer.testing import CliRunner

from fdsn_rush import utils
from fdsn_rush.app import app
from fdsn_rush.client import FDSNClient
from fdsn_rush.manager import FDSNDownloadManager
from fdsn_rush.writer import SDSWriter

runner = CliRunner()


@pytest.fixture(autouse=True)
def _restore_global_state() -> Iterator[None]:
    """`download` adds a log file handler and sets `utils.NON_INTERACTIVE`, as a process would."""
    handlers = logging.root.handlers[:]
    yield
    utils.NON_INTERACTIVE = False
    for handler in logging.root.handlers[len(handlers) :]:
        handler.close()
    logging.root.handlers = handlers


def _report(stdout: str) -> dict[str, str]:
    """Parse the `key: value` lines printed by `--non-interactive`."""
    return dict(line.split(": ", 1) for line in stdout.splitlines())


def _config(tmp_path: Path, url: str, selection: str = "XX.STA01") -> Path:
    manager = FDSNDownloadManager(
        writer=SDSWriter(sds_archive=tmp_path / "sds"),
        clients=[FDSNClient(url=HttpUrl(url), rate_limit=1000)],
        metadata_path=tmp_path / "metadata",
        time_range=(date(2024, 1, 1), date(2024, 1, 2)),  # end is exclusive: one day
        station_selection=[selection],
        channel_priority=["HH[ZNE]", "EH[ZNE]"],
        min_channels_per_station=1,
    )
    config = tmp_path / "config.json"
    config.write_text(manager.model_dump_json())
    return config


async def test_non_interactive_downloads_one_day(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    config = _config(tmp_path, fake_fdsn.url)

    # The CLI runs its own event loop, so keep it off the loop serving the fake FDSN
    result = await asyncio.to_thread(
        runner.invoke, app, ["download", str(config), "--non-interactive"]
    )

    assert result.exit_code == 0, result.stderr

    report = _report(result.stdout)
    assert report["status"] == "ok"
    assert "error" not in report
    assert report["sds_folder"] == str(tmp_path / "sds")
    assert report["downloading"] == fake_fdsn.url
    assert report["files"] == "3"
    assert report["failed"] == "0"
    assert result.stderr == ""  # quiet: details are in the log file

    # one day of three channels in the SDS archive
    sds = tmp_path / "sds"
    files = {p.relative_to(sds).as_posix() for p in sds.glob("**/*.D.*")}
    assert files == {
        f"2024/XX/STA01/{cha}.D/XX.STA01..{cha}.D.2024.001"
        for cha in ("HHE", "HHN", "HHZ")
    }
    assert (tmp_path / "metadata" / "XX.xml").exists()
    assert not list(sds.glob("**/*.partial"))

    # stats file
    sds_stats = json.loads((sds / "fdsn-rush-stats.json").read_text())
    assert report["stats_file"] == str(sds / "fdsn-rush-stats.json")
    assert sds_stats["writer"]["total_files_saved"] == 3
    assert sds_stats["writer"]["total_bytes_written"] > 0
    (client,) = sds_stats["clients"]
    assert client["url"] == fake_fdsn.url
    assert client["n_requests"] == 3
    assert client["n_completed"] == 3
    assert client["n_failed"] == 0
    assert client["n_no_data"] == 0
    assert sds_stats["manager"]["elapsed_seconds"] > 0
    assert len(fake_fdsn.dataselect_requests) == 3

    # the log is in the archive
    assert report["log_file"] == str(sds / "fdsn-rush.log")
    log = (sds / "fdsn-rush.log").read_text()
    assert "Starting download" in log
    assert "All downloads completed successfully." in log


async def test_non_interactive_reports_no_data(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    """404 is not a failure, it is counted and the run still succeeds."""
    config = _config(tmp_path, fake_fdsn.url, selection="XX.STA02")

    result = await asyncio.to_thread(
        runner.invoke,
        app,
        ["download", str(config), "-n"],
    )

    assert result.exit_code == 0, result.stderr
    report = _report(result.stdout)
    assert report["status"] == "ok"
    assert report["no_data"] == "1"  # EHE
    assert report["failed"] == "0"


def test_non_interactive_invalid_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["download", str(tmp_path / "missing.json"), "-n"])

    assert result.exit_code == 2
    report = _report(result.stdout)
    assert report["status"] == "invalid_config"
    assert "missing.json" in report["error"]
    assert "files" not in report


def test_non_interactive_server_unreachable(tmp_path: Path) -> None:
    config = _config(tmp_path, "http://127.0.0.1:1")

    result = runner.invoke(app, ["download", str(config), "-n"])

    assert result.exit_code == 1
    report = _report(result.stdout)
    assert report["status"] == "error"
    assert report["error"]
    assert "Download failed" in (tmp_path / "sds" / "fdsn-rush.log").read_text()


async def test_stats_file_is_updated_per_file(
    tmp_path: Path, fake_fdsn: FakeFDSN, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stats file is rewritten at the start, when files finish and at the end."""
    manager = FDSNDownloadManager.load(_config(tmp_path, fake_fdsn.url))
    n_completed: list[int] = []
    write_stats = FDSNDownloadManager._write_stats

    def spy(self: FDSNDownloadManager, path: Path) -> None:
        n_completed.append(self.stats_report().clients[0].n_completed)
        write_stats(self, path)

    monkeypatch.setattr(FDSNDownloadManager, "_write_stats", spy)

    await manager.download()

    assert n_completed[0] == 0
    assert n_completed[-1] == 3
    assert len(n_completed) > 2  # start, at least one finished file, end
    assert 0 < max(n_completed[1:-1]) <= 3  # progress was visible while running


async def test_partial_when_downloads_failed(
    tmp_path: Path, fake_fdsn: FakeFDSN, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing(self: FDSNClient, *args: object) -> None:
        self._stats.n_failed = 2

    monkeypatch.setattr(FDSNClient, "download", failing)
    config = _config(tmp_path, fake_fdsn.url)

    result = await asyncio.to_thread(
        runner.invoke, app, ["download", str(config), "-n"]
    )

    assert result.exit_code == 3
    assert _report(result.stdout)["status"] == "partial"
