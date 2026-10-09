"""End-to-end tests of ``fdsn-rush download --non-interactive`` against the fake server."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
import rich
from conftest import FakeFDSN
from pydantic import HttpUrl, ValidationError
from typer.testing import CliRunner

from fdsn_rush import utils
from fdsn_rush.app import app
from fdsn_rush.client import FDSNClient
from fdsn_rush.manager import FDSNDownloadManager
from fdsn_rush.selection import StationSelection
from fdsn_rush.writer import SDSWriter

runner = CliRunner()


@pytest.fixture(autouse=True)
def _restore_global_state() -> Iterator[None]:
    """`download` adds a log file handler and sets `utils.NON_INTERACTIVE`, as a process would."""
    handlers = logging.root.handlers[:]
    yield
    utils.NON_INTERACTIVE = False
    rich.reconfigure()  # undo quiet=True
    for handler in logging.root.handlers[len(handlers) :]:
        handler.close()
    logging.root.handlers = handlers


def _report(stdout: str) -> dict[str, str]:
    """Parse the `key: value` lines printed by `--non-interactive`."""
    return dict(line.split(": ", 1) for line in stdout.splitlines())


def _config(tmp_path: Path, url: str, *selection: str) -> Path:
    manager = FDSNDownloadManager(
        writer=SDSWriter(sds_archive=tmp_path / "sds"),
        clients=[FDSNClient(url=HttpUrl(url), rate_limit=1000)],
        metadata_path=tmp_path / "metadata",
        time_range=(date(2024, 1, 1), date(2024, 1, 2)),  # end is exclusive: one day
        station_selections=[StationSelection(stations=list(selection or ["XX.STA01"]))],
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
    assert report["server"] == fake_fdsn.url
    assert report["stations"] == "1"
    assert report["to_download"] == "3"
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
    log = config.with_suffix(".log").read_text()
    assert "Starting download" in log
    assert "All downloads completed successfully." in log


async def test_non_interactive_reports_no_data(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    """404 is not a failure, it is counted and the run still succeeds."""
    config = _config(tmp_path, fake_fdsn.url, "XX.STA02")

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


def test_non_interactive_server_unreachable(tmp_path: Path) -> None:
    config = _config(tmp_path, "http://127.0.0.1:1")

    config.with_suffix(".log").write_text("log of the previous run\n")

    result = runner.invoke(app, ["download", str(config), "-n"])

    assert result.exit_code == 1
    report = _report(result.stdout)
    assert report["status"] == "error"
    assert report["error"]
    log = config.with_suffix(".log").read_text()
    assert "Download failed" in log
    assert "previous run" not in log  # the log is replaced on every run
    assert report["elapsed"] != "Nones"  # failed before the inventory was fetched


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


async def test_metadata_downloads_no_waveforms(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    config = _config(tmp_path, fake_fdsn.url)

    result = await asyncio.to_thread(runner.invoke, app, ["metadata", str(config)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "metadata" / "XX.xml").exists()
    assert fake_fdsn.dataselect_requests == []
    assert not list((tmp_path / "sds").glob("**/*.D.*"))


async def test_server_error_counts_as_failed(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    fake_fdsn.failing_nslc.add(("XX", "STA01", "", "HHZ"))
    config = _config(tmp_path, fake_fdsn.url)

    result = await asyncio.to_thread(
        runner.invoke, app, ["download", str(config), "-n"]
    )

    assert result.exit_code == 2
    report = _report(result.stdout)
    assert report["files"] == "2"
    assert report["failed"] == "1"
    assert report["failed_queries"] == "0"
    assert report["status"] == "partial"


async def test_failed_station_query_is_partial(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    """The other networks are downloaded, but the run is not `ok`."""
    fake_fdsn.station_errors = {"YY": [401]}
    config = _config(tmp_path, fake_fdsn.url, "XX.STA01", "YY")

    result = await asyncio.to_thread(
        runner.invoke, app, ["download", str(config), "-n"]
    )

    assert result.exit_code == 2
    report = _report(result.stdout)
    assert report["files"] == "3"
    assert report["failed"] == "0"
    assert report["failed_queries"] == "1"
    assert report["status"] == "partial"


async def test_all_station_queries_failed_is_error(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    fake_fdsn.station_errors = {"XX": [500, 500, 500]}
    config = _config(tmp_path, fake_fdsn.url)

    result = await asyncio.to_thread(
        runner.invoke, app, ["download", str(config), "-n"]
    )

    assert result.exit_code == 1
    report = _report(result.stdout)
    assert report["error"].startswith("StationQueryError: 1 station queries")
    assert report["failed_queries"] == "1"
    assert report["status"] == "error"


async def test_worker_error_is_unwrapped(
    tmp_path: Path, fake_fdsn: FakeFDSN, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An error inside the nested TaskGroups is reported as itself."""

    async def broken(self: SDSWriter, download: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(SDSWriter, "done", broken)
    config = _config(tmp_path, fake_fdsn.url)

    result = await asyncio.to_thread(
        runner.invoke, app, ["download", str(config), "-n"]
    )

    assert result.exit_code == 1
    report = _report(result.stdout)
    assert report["error"] == "RuntimeError: disk full"
    assert report["status"] == "error"


def test_check_valid_config(tmp_path: Path) -> None:
    config = _config(tmp_path, "http://x.invalid")

    result = runner.invoke(app, ["check", str(config)])

    assert result.exit_code == 0
    assert "is valid" in result.stdout
    assert not (tmp_path / "sds").exists()  # nothing is written


def test_check_invalid_config(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"time_range": 5}')

    result = runner.invoke(app, ["check", str(config)])

    assert result.exit_code == 1
    assert isinstance(result.exception, ValidationError)


@pytest.mark.parametrize(
    "config",
    [
        {"station_blacklist": ["GE.APE"]},  # removed option
        {"station_selecton": {"selection": "StationSelection"}},  # misspelled
        {"station_selection": {"selection": "StationSelection"}},  # renamed
        {"station_selections": [{"selection": "StationSelection", "networks": ["GE"]}]},
        {"writer": {"sds_archiv": "data"}},
        {"clients": [{"urll": "https://geofon.gfz.de"}]},
    ],
)
def test_check_unknown_option(tmp_path: Path, config: dict[str, object]) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))

    result = runner.invoke(app, ["check", str(path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, ValidationError)
    assert "Extra inputs are not permitted" in str(result.exception)


async def test_download_interactive_exit_code(
    tmp_path: Path, fake_fdsn: FakeFDSN
) -> None:
    """Without -n the live view runs and the files are still written."""
    config = _config(tmp_path, fake_fdsn.url)

    result = await asyncio.to_thread(runner.invoke, app, ["download", str(config)])

    assert result.exit_code == 0
    assert len(list((tmp_path / "sds").glob("**/*.D.*"))) == 3
