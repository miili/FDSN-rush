"""Non-interactive ``download`` mode for scripts and agents.

Logs go to stderr and to a file in the SDS archive. A compact JSON report is
rewritten to a stats file every few seconds (poll it for progress) and printed
to stdout once at the end.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import rich
from pydantic import BaseModel

from fdsn_rush import __version__
from fdsn_rush.manager import FDSNDownloadManager, StatsReport
from fdsn_rush.utils import datetime_now

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

LOG_FILE_NAME = "fdsn-rush.log"
STATS_FILE_NAME = "fdsn-rush-stats.json"
Status = Literal["running", "ok", "partial", "error", "invalid_config"]
EXIT_CODES: dict[Status, int] = {"ok": 0, "error": 1, "invalid_config": 2, "partial": 3}


class Report(BaseModel):
    status: Status = "running"
    updated: datetime | None = None
    error: str | None = None
    log_file: Path | None = None
    stats_file: Path | None = None
    time_range: tuple[str, str] | None = None
    stats: StatsReport | None = None


@contextmanager
def _logging(log_file: Path, level: int) -> Iterator[None]:
    """Plain UTC log lines to stderr and `log_file`."""
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    formatter.converter = time.gmtime
    handlers = [logging.StreamHandler(sys.stderr), logging.FileHandler(log_file)]
    for handler in handlers:
        handler.setFormatter(formatter)
    root.handlers, root.level = handlers, level
    try:
        yield
    finally:
        root.handlers, root.level = saved
        handlers[1].close()


def run(
    config: Path,
    *,
    metadata_only: bool = False,
    stats_file: Path | None = None,
    stats_interval: float = 5.0,
    log_level: int = logging.INFO,
) -> int:
    """Run a download without interactive output and return the exit code."""
    rich.reconfigure(stderr=True, force_terminal=False)  # keep stdout for the report
    report = Report()
    manager: FDSNDownloadManager | None = None

    def emit(status: Status, error: str | None = None, *, final: bool = False) -> int:
        """Rewrite the stats file and, at the end, print the report."""
        report.status, report.error, report.updated = status, error, datetime_now()
        if manager and report.stats_file:
            report.stats = manager.stats_report()
            tmp = report.stats_file.with_suffix(".tmp")  # atomic for polling readers
            tmp.write_text(report.model_dump_json(exclude_none=True))
            tmp.replace(report.stats_file)
        if final:
            sys.stdout.write(report.model_dump_json(exclude_none=True) + "\n")
        return EXIT_CODES.get(status, 0)

    async def download() -> None:
        async def poll() -> None:
            while True:
                emit("running")
                await asyncio.sleep(stats_interval)

        poller = asyncio.create_task(poll())
        try:
            await manager.download(metadata_only=metadata_only)
        finally:
            poller.cancel()

    try:
        manager = FDSNDownloadManager.load(config)
    except (OSError, ValueError) as e:  # includes pydantic's ValidationError
        return emit("invalid_config", str(e), final=True)

    archive = manager.writer.sds_archive
    archive.mkdir(parents=True, exist_ok=True)
    report.log_file = archive / LOG_FILE_NAME
    report.stats_file = stats_file or archive / STATS_FILE_NAME
    report.stats_file.parent.mkdir(parents=True, exist_ok=True)
    report.time_range = tuple(d.isoformat() for d in manager.time_range)

    with _logging(report.log_file, log_level):
        logger.info("fdsn-rush %s, config %s", __version__, config)
        try:
            asyncio.run(download())
        except Exception as e:
            logger.exception("Download failed")
            # TaskGroup wraps worker errors in an ExceptionGroup
            leaf = e.exceptions[0] if isinstance(e, BaseExceptionGroup) else e
            return emit("error", f"{type(leaf).__name__}: {leaf}", final=True)

    n_failed = sum(c.n_failed for c in manager.stats_report().clients)
    return emit("partial" if n_failed else "ok", final=True)
