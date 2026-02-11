from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import ByteSize
from pyrocko.io import FileLoadError, FileSaveError, load, save
from pyrocko.io.mseed import detect as mseed_detect
from pyrocko.trace import Trace
from rich.progress import Progress

TEMPLATE: str = (
    "%(tmin_year)s/%(network)s/%(station)s/%(channel)s.D"
    "/%(network)s.%(station)s.%(location)s.%(channel)s.D"
    ".%(tmin_year)s.%(julianday)s"
)

CHANNEL_REGEX = re.compile(r"()")
FILE_ERRORS = set()

logger = logging.getLogger(__name__)


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
    try:
        await asyncio.to_thread(
            save,
            traces,
            str(output / TEMPLATE),
            record_length=4096,
            steim=steim,
            append=True,
            check_overlaps=False,
        )

    except FileSaveError as e:
        logger.error("Failed to save: %s", e)
        outfiles = {trace.fill_template(str(output / TEMPLATE)) for trace in traces}
        outfiles -= FILE_ERRORS
        FILE_ERRORS.update(outfiles)

        if outfiles:
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
