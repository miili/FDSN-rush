"""End-to-end tests of ``fdsn-rush download --non-interactive`` against the fake server."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest
from conftest import FakeFDSN
from pydantic import HttpUrl
from typer.testing import CliRunner

from fdsn_rush import headless
from fdsn_rush.app import app
from fdsn_rush.client import FDSNClient
from fdsn_rush.manager import FDSNDownloadManager
from fdsn_rush.writer import SDSWriter

runner = CliRunner()


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

    # stdout is exactly one JSON document, logs are on stderr
    report = json.loads(result.stdout)
    assert report["status"] == "ok"
    assert "error" not in report
    assert report["time_range"] == ["2024-01-01", "2024-01-02"]
    assert "Starting download" in result.stderr

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
    assert json.loads((sds / "fdsn-rush-stats.json").read_text()) == report
    log = (sds / "fdsn-rush.log").read_text()
    assert "Starting download" in log
    assert "All downloads completed successfully." in log


async def test_non_interactive_reports_no_data(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    """404 is not a failure, it is counted and the run still succeeds."""
    config = _config(tmp_path, fake_fdsn.url, selection="XX.STA02")
    stats_file = tmp_path / "out" / "stats.json"

    result = await asyncio.to_thread(
        runner.invoke,
        app,
        ["download", str(config), "-n", "--stats-file", str(stats_file)],
    )

    assert result.exit_code == 0, result.stderr
    (client,) = json.loads(result.stdout)["stats"]["clients"]
    assert client["n_no_data"] == 1  # EHE
    assert client["n_failed"] == 0
    assert json.loads(stats_file.read_text())["status"] == "ok"


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


def test_stats_file_needs_non_interactive(tmp_path: Path) -> None:
    config = _config(tmp_path, "http://127.0.0.1:1")

    result = runner.invoke(app, ["download", str(config), "--stats-file", "x.json"])

    assert result.exit_code == 2


async def test_stats_file_is_polled(
    tmp_path: Path, fake_fdsn: FakeFDSN, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While the download runs, the stats file is rewritten with status "running"."""

    async def slow_download(self: FDSNDownloadManager, **kwargs: object) -> None:
        await asyncio.sleep(0.5)

    monkeypatch.setattr(FDSNDownloadManager, "download", slow_download)
    stats_file = tmp_path / "stats.json"
    run_task = asyncio.create_task(
        asyncio.to_thread(
            headless.run,
            _config(tmp_path, fake_fdsn.url),
            stats_file=stats_file,
            stats_interval=0.05,
        )
    )
    for _ in range(100):
        if (
            stats_file.exists()
            and json.loads(stats_file.read_text())["status"] == "running"
        ):
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("stats file was not updated while running")

    assert await run_task == 0
    assert json.loads(stats_file.read_text())["status"] == "ok"


def test_partial_when_downloads_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_download(self: FDSNDownloadManager, **kwargs: object) -> None:
        self.clients[0]._stats.n_failed = 2

    monkeypatch.setattr(FDSNDownloadManager, "download", failing_download)

    result = runner.invoke(
        app, ["download", str(_config(tmp_path, "http://x.invalid")), "-n"]
    )

    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "partial"
