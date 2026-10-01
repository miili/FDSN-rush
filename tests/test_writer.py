from __future__ import annotations

from datetime import date
from pathlib import Path

from conftest import MSeedFactory
from pyrocko import io

from fdsn_rush.client import DownloadDayfile
from fdsn_rush.models.station import Stations
from fdsn_rush.utils import _NSL
from fdsn_rush.writer import SDSWriter

DAY = date(2024, 1, 1)
NSLC = ("XX", "STA01", "", "HHZ")


def _dayfile(stations: Stations) -> DownloadDayfile:
    sta01 = stations.get_station(_NSL("XX", "STA01", ""))
    (channel,) = sta01.get_channels(DAY, "HHZ")
    return DownloadDayfile(channel=channel, date=DAY)


async def test_writer_saves_dayfile(
    stations: Stations, make_mseed: MSeedFactory, sds_archive: Path
) -> None:
    writer = SDSWriter(sds_archive=sds_archive)
    await writer.prepare()
    dayfile = _dayfile(stations)

    assert not writer.has_chunk(dayfile)

    data = make_mseed(NSLC, DAY)
    # Data arrives in multiple chunks
    await writer.add_data(dayfile, data[:4096])
    await writer.add_data(dayfile, data[4096:])
    assert (sds_archive / dayfile.sds_path(partial=True)).exists()

    await writer.done(dayfile)

    final = sds_archive / dayfile.sds_path()
    assert writer.has_chunk(dayfile)
    assert not (sds_archive / dayfile.sds_path(partial=True)).exists()
    assert final.name == "XX.STA01..HHZ.D.2024.001"

    (trace,) = io.load(str(final))
    assert trace.nslc_id == NSLC
    assert trace.ydata.size == 60_000


async def test_writer_drops_short_traces(
    stations: Stations, make_mseed: MSeedFactory, sds_archive: Path
) -> None:
    writer = SDSWriter(sds_archive=sds_archive)
    await writer.prepare()
    dayfile = _dayfile(stations)

    # Shorter than the default min_length_seconds of 1 minute
    await writer.add_data(dayfile, make_mseed(NSLC, DAY, seconds=30.0))
    await writer.done(dayfile)

    assert not writer.has_chunk(dayfile)
    assert not (sds_archive / dayfile.sds_path(partial=True)).exists()


async def test_writer_prepare_cleans_up(
    stations: Stations, make_mseed: MSeedFactory, sds_archive: Path
) -> None:
    dayfile = _dayfile(stations)
    partial = sds_archive / dayfile.sds_path(partial=True)
    empty = sds_archive / dayfile.sds_path()
    partial.parent.mkdir(parents=True)
    partial.write_bytes(make_mseed(NSLC, DAY))
    empty.touch()

    writer = SDSWriter(sds_archive=sds_archive)
    await writer.prepare()

    assert not partial.exists()
    assert not empty.exists()
    assert writer.remote_log.file == sds_archive / "remote_errors.log"
