from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from conftest import FakeFDSN
from pydantic import HttpUrl, ValidationError

from fdsn_rush.client import FDSNClient
from fdsn_rush.manager import FDSNDownloadManager
from fdsn_rush.models.station import Stations
from fdsn_rush.writer import SDSWriter

TIME_RANGE = (date(2024, 1, 1), date(2024, 1, 3))


def _manager(tmp_path: Path, url: str, **kwargs) -> FDSNDownloadManager:
    return FDSNDownloadManager(
        writer=SDSWriter(sds_archive=tmp_path / "data"),
        clients=[FDSNClient(url=HttpUrl(url), rate_limit=1000)],
        metadata_path=tmp_path / "metadata",
        time_range=TIME_RANGE,
        station_selection=["XX"],
        channel_priority=["HH[ZNE]", "EH[ZNE]"],
        min_channels_per_station=3,
        **kwargs,
    )


def _work_ids(manager: FDSNDownloadManager, client: FDSNClient) -> set[str]:
    return {f"{d.channel.nslc.pretty}/{d.date}" for d in manager.get_work(client)}


def test_config_roundtrip(tmp_path: Path) -> None:
    """The output of `fdsn-rush init` must load in strict mode."""
    config = tmp_path / "config.json"
    config.write_text(FDSNDownloadManager().model_dump_json())

    manager = FDSNDownloadManager.load(config)
    assert manager.model_dump_json() == config.read_text()


def test_config_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        FDSNDownloadManager.load(tmp_path / "missing.json")


def test_config_invalid_time_range() -> None:
    with pytest.raises(ValidationError, match="Start date must be before end date"):
        FDSNDownloadManager(time_range=(date(2024, 1, 2), date(2024, 1, 1)))


def test_get_work(tmp_path: Path, stations: Stations) -> None:
    manager = _manager(tmp_path, "https://example.org")
    client = manager.clients[0]
    client.available_stations = stations

    assert _work_ids(manager, client) == {
        f"XX.{sta}..{cha}/{day}"
        for sta, band in (("STA01", "HH"), ("STA02", "EH"))
        for cha in (f"{band}Z", f"{band}N", f"{band}E")
        for day in ("2024-01-01", "2024-01-02")
    }

    # STA03 qualifies once a single channel suffices, but only while its epoch runs
    manager.min_channels_per_station = 1
    assert {w for w in _work_ids(manager, client) if "STA03" in w} == {
        "XX.STA03..HHZ/2024-01-01"
    }


def test_get_work_blacklist_and_archive(tmp_path: Path, stations: Stations) -> None:
    manager = _manager(tmp_path, "https://example.org", station_blacklist={"XX.STA02"})
    client = manager.clients[0]
    client.available_stations = stations

    existing = (
        manager.writer.sds_archive / "2024/XX/STA01/HHZ.D/XX.STA01..HHZ.D.2024.001"
    )
    existing.parent.mkdir(parents=True)
    existing.touch()

    work = _work_ids(manager, client)
    assert not any("STA02" in w for w in work)
    assert "XX.STA01..HHZ/2024-01-01" not in work
    assert len(work) == 5


async def test_download(tmp_path: Path, fake_fdsn: FakeFDSN) -> None:
    manager = _manager(tmp_path, fake_fdsn.url)
    await manager.download()

    archive = manager.writer.sds_archive
    files = {p.name for p in archive.glob("**/*.D.*")}
    assert files == {
        f"XX.{sta}..{cha}.D.2024.{day}"
        for sta, chas in (("STA01", "HHZ HHN HHE"), ("STA02", "EHZ EHN"))
        for cha in chas.split()
        for day in ("001", "002")
    }
    assert not list(archive.glob("**/*.partial"))
    # every run keeps a stats file in the archive
    assert '"total_files_saved":10' in (archive / "fdsn-rush-stats.json").read_text()
    assert (manager.metadata_path / "XX.xml").read_text() == "<FDSNStationXML/>"

    # EHE returned 404 and is logged so it is not requested again
    remote_log = (archive / "remote_errors.log").read_text().splitlines()
    assert len(remote_log) == 2
    assert all(line.startswith("XX.STA02..EHE,") for line in remote_log)
    n_requests = len(fake_fdsn.dataselect_requests)
    assert n_requests == 12

    # Wire format: blank location as "--", full timestamps, miniseed
    request = fake_fdsn.dataselect_requests[0]
    assert request["location"] == "--"
    assert request["format"] == "miniseed"
    assert request["starttime"].endswith("T00:00:00")
    assert request["endtime"].endswith("T00:00:00")

    # Re-running skips archived dayfiles and logged 404s
    manager = _manager(tmp_path, fake_fdsn.url)
    await manager.download()
    assert len(fake_fdsn.dataselect_requests) == n_requests


async def test_download_metadata_only(tmp_path: Path, fake_fdsn: FakeFDSN) -> None:
    manager = _manager(tmp_path, fake_fdsn.url)
    await manager.download(metadata_only=True)

    assert (manager.metadata_path / "XX.xml").exists()
    assert fake_fdsn.dataselect_requests == []
