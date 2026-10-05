from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import rich
import typer
from pydantic import DirectoryPath, NewPath
from rich.logging import RichHandler

from fdsn_rush import __version__, utils
from fdsn_rush.convert import convert_sds
from fdsn_rush.manager import LOG_FILE_NAME, FDSNDownloadManager
from fdsn_rush.stats import live_view
from fdsn_rush.utils import report

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO",
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler(tracebacks_show_locals=False)],
)

logger = logging.getLogger(__name__)

EXIT_CODES = {"ok": 0, "error": 1, "partial": 2}

app = typer.Typer(
    name="fdsn-rush",
    help="Fast and modern FDSN Download",
    no_args_is_help=True,
    add_completion=False,
)


def _print_version(value: bool) -> None:
    if value:
        rich.print(f"fdsn-rush {__version__}")
        raise typer.Exit


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Fast and modern FDSN Download"""


@app.command()
def init():
    """Print the configuration."""
    client = FDSNDownloadManager()
    rich.print_json(client.model_dump_json())


ConfigFile = Annotated[Path, typer.Argument(help="Path to the configuration file")]
Verbose = Annotated[int, typer.Option("--verbose", "-v", count=True)]
NonInteractive = Annotated[
    bool,
    typer.Option(
        "--non-interactive",
        "-n",
        help=(
            "No live view and no console output except a few key: value lines "
            "on stdout. Exit code: 0 ok, 1 error, 2 partial."
        ),
    ),
]


def _download(file: Path, verbose: int, non_interactive: bool, metadata_only: bool):
    manager = FDSNDownloadManager.load(file)
    logging.root.setLevel(logging.DEBUG if verbose else logging.INFO)
    if non_interactive:
        utils.NON_INTERACTIVE = True
        rich.reconfigure(quiet=True)  # live view, progress bars and Rich log lines

    archive = manager.writer.sds_archive
    archive.mkdir(parents=True, exist_ok=True)
    log_file = logging.FileHandler(archive / LOG_FILE_NAME)
    log_file.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    logging.root.addHandler(log_file)

    async def run() -> None:
        view = asyncio.create_task(live_view())  # silent when quiet
        try:
            await manager.download(metadata_only=metadata_only)
        finally:
            view.cancel()

    status = "ok"
    try:
        asyncio.run(run())
    except Exception as e:
        logger.exception("Download failed")
        # TaskGroup wraps worker errors in an ExceptionGroup
        leaf = e.exceptions[0] if isinstance(e, BaseExceptionGroup) else e
        report("error", f"{type(leaf).__name__}: {leaf}")
        status = "error"

    stats = manager.stats_report()
    n_failed = sum(c.n_failed for c in stats.clients)
    report("files", stats.writer.total_files_saved)
    report("no_data", sum(c.n_no_data for c in stats.clients))
    report("failed", n_failed)
    report("elapsed", f"{stats.manager.elapsed_seconds}s")
    if status == "ok" and n_failed:
        status = "partial"
    report("status", status)
    raise typer.Exit(EXIT_CODES[status])


@app.command()
def download(
    file: ConfigFile, verbose: Verbose = 0, non_interactive: NonInteractive = False
) -> None:
    """Download data from FDSN to local SDS archive."""
    _download(file, verbose, non_interactive, metadata_only=False)


@app.command()
def metadata(
    file: ConfigFile, verbose: Verbose = 0, non_interactive: NonInteractive = False
) -> None:
    """Download only the station inventory and StationXML, no waveforms."""
    _download(file, verbose, non_interactive, metadata_only=True)


@app.command()
def check(file: ConfigFile) -> None:
    """Validate the configuration file."""
    FDSNDownloadManager.load(file)
    rich.print(f"{file} is valid")


@app.command()
def convert(
    input: Annotated[
        DirectoryPath,
        typer.Argument(
            ...,
            help="Path to the input directory containing MiniSEED files",
        ),
    ],
    output: Annotated[
        NewPath,
        typer.Argument(
            ...,
            help="Path to the output directory for SDS archive",
        ),
    ],
    network: Annotated[
        str,
        typer.Option(
            ...,
            help="Network code to set for all traces",
        ),
    ] = "",
    steim: Annotated[
        int,
        typer.Option(
            ...,
            help="STEIM compression type to use (1 or 2)",
        ),
    ] = 2,
    n_workers: Annotated[
        int,
        typer.Option(
            ...,
            help="Number of worker threads for conversion",
        ),
    ] = 64,
) -> None:
    """Convert existing MiniSEED files to SDS archive."""
    if steim not in (1, 2):
        raise typer.BadParameter("STEIM must be either 1 or 2")
    asyncio.run(convert_sds(input, output, network, steim, n_workers))


def main():
    """Main entry point for the SDSCopy application."""
    app()


if __name__ == "__main__":
    main()
