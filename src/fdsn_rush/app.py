from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from pathlib import Path
from typing import Annotated, NoReturn

import rich
import typer
from pydantic import DirectoryPath, NewPath
from rich.logging import RichHandler

from fdsn_rush import __version__
from fdsn_rush.convert import convert_sds
from fdsn_rush.manager import LOG_FILE_NAME, FDSNDownloadManager, Report
from fdsn_rush.stats import live_view

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO",
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler(tracebacks_show_locals=False)],
)

EXIT_CODES = {"ok": 0, "error": 1, "invalid_config": 2, "partial": 3}

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


def _finish(report: Report) -> NoReturn:
    """Print the report as the only output and exit with its status code."""
    sys.stdout.write(report.model_dump_json(exclude_none=True) + "\n")
    raise typer.Exit(EXIT_CODES[report.status])


@app.command()
def download(
    file: Annotated[
        Path,
        typer.Argument(
            ...,
            help="Path to the configuration file",
        ),
    ],
    metadata_only: Annotated[
        bool,
        typer.Option("--metadata-only", "-m", is_flag=True),
    ] = False,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True),
    ] = 0,
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--non-interactive",
            "-n",
            help=(
                "No live view and no console output except one JSON report "
                "on stdout. Exit code: 0 ok, 1 error, 2 invalid config, 3 partial."
            ),
        ),
    ] = False,
) -> None:
    """Download data from FDSN to local SDS archive."""
    logging.root.setLevel(logging.DEBUG if verbose >= 1 else logging.INFO)
    if non_interactive:
        rich.reconfigure(quiet=True)  # live view, progress bars and Rich log lines

    try:
        client = FDSNDownloadManager.load(file)
    except (OSError, ValueError) as e:
        if not non_interactive:
            raise
        _finish(Report(status="invalid_config", error=str(e)))

    archive = client.writer.sds_archive
    archive.mkdir(parents=True, exist_ok=True)
    log_file = logging.FileHandler(archive / LOG_FILE_NAME)
    log_file.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    logging.root.addHandler(log_file)

    if non_interactive:
        with contextlib.suppress(Exception):  # kept in the report and the log file
            asyncio.run(client.download(metadata_only=metadata_only))
        _finish(client.report())

    async def run_download() -> None:
        download = asyncio.create_task(client.download(metadata_only=metadata_only))
        stats_view = asyncio.create_task(live_view())
        await download
        stats_view.cancel()

    asyncio.run(run_download())


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
