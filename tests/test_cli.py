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

from fdsn_rush.app import app
from fdsn_rush.client import FDSNClient
from fdsn_rush.manager import FDSNDownloadManager
from fdsn_rush.writer import SDSWriter

runner = CliRunner()


@pytest.fixture(autouse=True)
def _restore_root_logging() -> Iterator[None]:
    """`download` adds a file handler to the root logger, like a real process would."""
    handlers = logging.root.handlers[:]
    yield
    for handler in logging.root.handlers[len(handlers) :]:
        handler.close()
    logging.root.handlers = handlers


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

    # stdout is exactly one JSON document
    report = json.loads(result.stdout)
    assert report["status"] == "ok"
    assert "error" not in report
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

    # stats
    stats = report["stats"]
    assert stats["writer"]["total_files_saved"] == 3
    assert stats["writer"]["total_bytes_written"] > 0
    (client,) = stats["clients"]
    assert client["url"] == fake_fdsn.url
    assert client["n_requests"] == 3
    assert client["n_completed"] == 3
    assert client["n_failed"] == 0
    assert client["n_no_data"] == 0
    assert stats["manager"]["elapsed_seconds"] > 0
    assert len(fake_fdsn.dataselect_requests) == 3

    # the summary is written to the stats file and the log to the archive
    written = json.loads((sds / "fdsn-rush-stats.json").read_text())
    assert written["status"] == "ok"
    assert written["stats"] == report["stats"]
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
    (client,) = json.loads(result.stdout)["stats"]["clients"]
    assert client["n_no_data"] == 1  # EHE
    assert client["n_failed"] == 0


def test_non_interactive_invalid_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["download", str(tmp_path / "missing.json"), "-n"])

    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["status"] == "invalid_config"
    assert "stats" not in report


def test_non_interactive_server_unreachable(tmp_path: Path) -> None:
    config = _config(tmp_path, "http://127.0.0.1:1")

    result = runner.invoke(app, ["download", str(config), "-n"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["status"] == "error"
    assert report["error"]
    assert "Download failed" in (tmp_path / "sds" / "fdsn-rush.log").read_text()


async def test_stats_file_is_updated_per_file(
    tmp_path: Path, fake_fdsn: FakeFDSN, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stats file is rewritten at the start, when files finish and at the end."""
    manager = FDSNDownloadManager.load(_config(tmp_path, fake_fdsn.url))
    reports = []
    write_report = FDSNDownloadManager._write_report

    def spy(self: FDSNDownloadManager, path: Path) -> None:
        reports.append(self.report())
        write_report(self, path)

    monkeypatch.setattr(FDSNDownloadManager, "_write_report", spy)

    await manager.download()

    assert reports[0].status == "running"
    assert reports[-1].status == "ok"
    assert len(reports) > 2  # start, at least one finished file, end
    assert any(
        r.status == "running" and r.stats.clients[0].n_completed > 0 for r in reports
    )


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
    assert json.loads(result.stdout)["status"] == "partial"
