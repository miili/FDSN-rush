from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic import ByteSize
from pyrocko.io import FileLoadError, FileSaveError, load, save
from pyrocko.io.mseed import detect as mseed_detect
from pyrocko.trace import NoData, Trace
from rich.progress import Progress

from fdsn_rush.utils import NSL, NSLC

SDS_TEMPLATE: str = (
    "{year}/{network}/{station}/{channel}.D/"
    "{network}.{station}.{location}.{channel}.D.{year}.{julianday:03d}"
)

FILE_ERRORS = set()

CODE_REGEX = re.compile(r"[A-Za-z0-9]*")
CODE_LENGTHS = {"network": 2, "station": 5, "location": 2, "channel": 3}

logger = logging.getLogger(__name__)

_FILE_LOCKS = defaultdict(asyncio.Lock)


@contextlib.asynccontextmanager
async def file_lock(file_path: str):
    """Context manager to handle file locks."""
    async with _FILE_LOCKS[file_path]:
        yield

    if not _FILE_LOCKS[file_path].locked():
        _FILE_LOCKS.pop(file_path, None)


def _split_codes(codes: str, rule: str) -> NSLC:
    """Split `NET.STA.LOC.CHA` into its parts. Missing trailing parts are empty."""
    parts = codes.split(".")
    if len(parts) > 4:
        raise ValueError(
            f"invalid codes `{codes}` in rename `{rule}`, expected `NET.STA.LOC.CHA`"
        )
    return NSLC(*parts, *[""] * (4 - len(parts)))


class Rename(NamedTuple):
    """A rename rule `FROM=TO`, both written as `NET.STA.LOC.CHA`.

    Each part of `source` is an fnmatch pattern: an empty part matches any
    code and `--` matches the blank location. Each part of `target` is the new
    code: an empty part keeps the code and `--` sets the blank location.
    """

    source: NSLC
    target: NSLC

    @classmethod
    def parse(cls, rule: str) -> Rename:
        source, sep, target = rule.partition("=")
        if not sep:
            raise ValueError(f"invalid rename `{rule}`, expected `FROM=TO`")
        rename = cls(_split_codes(source, rule), _split_codes(target, rule))
        for name, code in rename.target._asdict().items():
            if name == "location" and code == "--":
                continue
            if not CODE_REGEX.fullmatch(code) or len(code) > CODE_LENGTHS[name]:
                raise ValueError(
                    f"invalid {name} `{code}` in rename `{rule}`, expected up to "
                    f"{CODE_LENGTHS[name]} letters or digits"
                )
        if not any(rename.target):
            raise ValueError(f"rename `{rule}` changes nothing")
        return rename

    def apply(self, trace: Trace) -> None:
        """Rename the trace in place if it matches the source."""
        nsl = NSL(trace.network, trace.station, trace.location)
        if not NSL(*self.source[:3]).match(nsl):
            return
        if self.source.channel and not fnmatch(trace.channel, self.source.channel):
            return
        location = self.target.location
        trace.set_codes(
            network=self.target.network or None,
            station=self.target.station or None,
            location="" if location == "--" else location or None,
            channel=self.target.channel or None,
        )


async def convert(
    input: Path,
    output: Path,
    renames: Sequence[Rename] = (),
    steim: Literal[1, 2] = 2,
    codes: defaultdict[NSLC, set[NSLC]] | None = None,
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
        source = NSLC(tr.network, tr.station, tr.location, tr.channel)
        for rename in renames:
            rename.apply(tr)
        if codes is not None:
            codes[NSLC(tr.network, tr.station, tr.location, tr.channel)].add(source)

    split_traces = []
    for tr in traces:
        tr_start = datetime.fromtimestamp(tr.tmin, tz=UTC)
        tr_end = datetime.fromtimestamp(tr.tmax, tz=UTC)

        if tr_start.date() == tr_end.date():
            split_traces.append(tr)
            continue

        start_day = tr_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = tr_end.replace(hour=0, minute=0, second=0, microsecond=0)
        current_day = start_day
        while current_day <= end_day:
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
        date = datetime.fromtimestamp(tr_tmid, tz=UTC).date()
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


def _is_mseed(path: Path) -> bool:
    """Check if the file starts with a MiniSEED header."""
    try:
        with path.open("rb") as f:
            header = f.read(512)
    except OSError:
        return False
    return bool(mseed_detect(header))


async def convert_sds(
    input: Path,
    output: Path,
    renames: Sequence[Rename] = (),
    steim: Literal[1, 2] = 2,
    n_workers: int = 64,
):
    nbytes = 0
    codes: defaultdict[NSLC, set[NSLC]] = defaultdict(set)

    input_files = set()
    with Progress() as progress:
        task = progress.add_task("Scanning files", total=None)

        for i, path in enumerate(input.rglob("*.*")):
            if not path.is_file():
                continue

            if not _is_mseed(path):
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
    pending: set[asyncio.Task] = set()
    with Progress() as progress:
        task = progress.add_task("Processing", total=len(input_files))
        for path in input_files:
            t = asyncio.create_task(convert(path, output, renames, steim, codes))
            pending.add(t)
            t.add_done_callback(pending.discard)
            t.add_done_callback(lambda _: queue.get_nowait())
            t.add_done_callback(lambda _: progress.update(task, advance=1))
            await queue.put(t)
        # Wait for the last batch, asyncio.run would cancel it otherwise
        await asyncio.gather(*pending)

    for target, sources in sorted(codes.items()):
        for source in sorted(sources - {target}):
            logger.info("Renamed %s to %s", source.pretty, target.pretty)
        if len(sources) > 1:
            logger.warning(
                "%s holds data from %s",
                target.pretty,
                ", ".join(source.pretty for source in sorted(sources)),
            )
