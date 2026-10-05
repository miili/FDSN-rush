"""Non-interactive ``download`` mode for scripts and agents.

Logs go to stderr and to a file in the SDS archive, stdout carries one JSON
summary, and the same summary is written to a stats file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import rich
from pydantic import ValidationError

from fdsn_rush import __version__
from fdsn_rush.manager import FDSNDownloadManager

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

LOG_FILE_NAME = "fdsn-rush.log"
STATS_FILE_NAME = "fdsn-rush-stats.json"
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class ExitCode(IntEnum):
    OK = 0
    ERROR = 1  # unexpected failure, e.g. server unreachable
    CONFIG = 2  # configuration file missing or invalid
    PARTIAL = 3  # finished, but some dayfiles failed (404 is not a failure)


@contextmanager
def _logging(log_file: Path | None, level: int) -> Iterator[None]:
    """Plain log lines to stderr, plus a log file when a path is given."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    formatter = logging.Formatter(LOG_FORMAT)
    formatter.converter = time.gmtime

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    root.handlers = handlers
    root.setLevel(level)
    for handler in handlers:
        handler.setFormatter(formatter)
    try:
        yield
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        for handler in handlers:
            handler.close()


def _write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def _status(report: dict[str, Any]) -> ExitCode:
    if report["error"] is not None:
        return (
            ExitCode.CONFIG if report["error"]["type"] == "config" else ExitCode.ERROR
        )
    n_failed = sum(client["n_failed"] for client in report["stats"]["clients"])
    return ExitCode.PARTIAL if n_failed else ExitCode.OK


def run(
    config: Path,
    *,
    metadata_only: bool = False,
    stats_file: Path | None = None,
    log_level: int = logging.INFO,
) -> ExitCode:
    """Run a download without any interactive output and print a JSON summary.

    Returns the process exit code, see `ExitCode`.
    """
    # Rich progress bars (archive scan) must not end up on stdout.
    rich.reconfigure(stderr=True, force_terminal=False)

    report: dict[str, Any] = {
        "status": "error",
        "version": __version__,
        "config": str(config),
        "metadata_only": metadata_only,
        "started": datetime.now(UTC).isoformat(),
        "error": None,
        "sds_archive": None,
        "log_file": None,
        "stats_file": None,
        "time_range": None,
        "stats": None,
    }

    manager: FDSNDownloadManager | None = None
    try:
        manager = FDSNDownloadManager.load(config)
    except (OSError, ValidationError, ValueError) as e:
        report["error"] = {"type": "config", "message": str(e)}

    if manager is not None:
        archive = manager.writer.sds_archive
        log_file = archive / LOG_FILE_NAME
        stats_file = stats_file or archive / STATS_FILE_NAME
        report.update(
            sds_archive=str(archive),
            log_file=str(log_file),
            stats_file=str(stats_file),
            time_range=[d.isoformat() for d in manager.time_range],
        )
        with _logging(log_file, log_level):
            logger.info("fdsn-rush %s, config %s", __version__, config)
            try:
                asyncio.run(manager.download(metadata_only=metadata_only))
            except Exception as e:
                logger.exception("Download failed")
                # TaskGroup wraps worker errors in an ExceptionGroup
                leaf = e.exceptions[0] if isinstance(e, BaseExceptionGroup) else e
                report["error"] = {"type": type(leaf).__name__, "message": str(leaf)}
        report["stats"] = manager.stats_report()

    report["finished"] = datetime.now(UTC).isoformat()
    code = _status(report)
    report["status"] = {
        ExitCode.OK: "ok",
        ExitCode.PARTIAL: "partial",
    }.get(code, "error")
    report["exit_code"] = int(code)

    if stats_file is not None:
        _write_json(stats_file, report)
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return code
