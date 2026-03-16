from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import ByteSize
from pyrocko.io import FileLoadError, FileSaveError, load, save
from pyrocko.io.mseed import detect as mseed_detect
from pyrocko.trace import NoData, Trace
from rich.progress import Progress

SDS_TEMPLATE: str = (
    "{year}/{network}/{station}/{channel}.D/"
    "{network}.{station}.{location}.{channel}.D.{year}.{julianday:03d}"
)

CHANNEL_REGEX = re.compile(r"()")
FILE_ERRORS = set()

logger = logging.getLogger(__name__)

_FILE_LOCKS = defaultdict(asyncio.Lock)


@contextlib.asynccontextmanager
async def file_lock(file_path: str):
    """Context manager to handle file locks."""
    async with _FILE_LOCKS[file_path]:
        yield

    if not _FILE_LOCKS[file_path].locked():
        _FILE_LOCKS.pop(file_path, None)


async def convert(
    input: Path, output: Path, network: str = "", steim: Literal[1, 2] = 2
):
    try:
        traces: list[Trace] = await asyncio.to_thread(
            load,
            str(input),
        )
    except FileLoadError as e:
        logger.error(
            "Failed to load %s: %s",
            input,
            e,
        )
        return

    for tr in traces:
        if network:
            tr.set_network(network)

    split_traces = []
    for tr in traces:
        tr_start = datetime.fromtimestamp(tr.tmin, tz=timezone.utc)
        tr_end = datetime.fromtimestamp(tr.tmax, tz=timezone.utc)

        if tr_start.date() == tr_end.date():
            split_traces.append(tr)
            continue

        start_day = tr_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = tr_end.replace(hour=0, minute=0, second=0, microsecond=0)
        current_day = start_day
        while current_day < end_day:
            with contextlib.suppress(NoData):
                split_traces.append(
                    tr.chop(
                        tmin=current_day.timestamp(),
                        tmax=current_day.timestamp() + 3600 * 24,
                        inplace=False,
                    ),
                )
            current_day += timedelta(days=1)

    for trace in split_traces:
        tr_tmid = trace.tmin + (trace.tmax - trace.tmin) / 2
        date = datetime.fromtimestamp(tr_tmid, tz=timezone.utc).date()
        name = SDS_TEMPLATE.format(
            year=date.year,
            network=trace.network,
            station=trace.station,
            location=trace.location,
            channel=trace.channel,
            julianday=date.timetuple().tm_yday,
        )
        try:
            async with file_lock(name):
                await asyncio.to_thread(
                    save,
                    trace,
                    str(output / name),
                    record_length=4096,
                    steim=steim,
                    append=True,
                    check_overlaps=False,
                )
        except FileSaveError as e:
            logger.error("Failed to save: %s", e)
            outfiles = {str(output / name)}
            outfiles -= FILE_ERRORS
            FILE_ERRORS.update(outfiles)

            with (output / "errors.txt").open("a") as f:
                f.write("\n".join(outfiles) + "\n")


async def convert_sds(
    input: Path,
    output: Path,
    network: str = "",
    steim: Literal[1, 2] = 2,
    n_workers: int = 64,
):
    nbytes = 0

    input_files = set()
    with Progress() as progress:
        task = progress.add_task("Scanning files", total=None)

        for i, path in enumerate(input.rglob("*.*")):
            if not path.is_file():
                continue

            with open(path, "rb") as f:
                try:
                    header = f.read(512)
                except OSError:
                    continue

            if not mseed_detect(header):
                continue

            input_files.add(path)
            nbytes += path.stat().st_size
            if i % 100 == 0:
                progress.update(
                    task,
                    completed=i,
                    description=f"Scanned {ByteSize(nbytes).human_readable()}",
                )

    logger.info(
        "%s files found (%s total size)",
        len(input_files),
        ByteSize(nbytes).human_readable(),
    )

    queue = asyncio.Queue(n_workers)
    with Progress() as progress:
        task = progress.add_task("Processing", total=len(input_files))
        for path in input_files:
            t = asyncio.create_task(convert(path, output, network, steim))
            t.add_done_callback(lambda _: queue.get_nowait())
            await queue.put(t)
            progress.update(task, advance=1)
