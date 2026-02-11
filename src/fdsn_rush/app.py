from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import rich
import typer
from pydantic import DirectoryPath, NewPath
from rich.logging import RichHandler

from fdsn_rush.convert import convert_sds
from fdsn_rush.manager import FDSNDownloadManager
from fdsn_rush.stats import live_view

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

app = typer.Typer(
    name="fdsn-rush",
    help="Fast and modern FDSN Download",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def init():
    """Print the configuration."""
    client = FDSNDownloadManager()
    rich.print_json(client.model_dump_json())


@app.command()
def download(
    file: Annotated[
        Path,
        typer.Argument(
            ...,
            help="Path to the configuration file",
        ),
    ],
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True)] = 0,
) -> None:
    """Download data from FDSN to local SDS archive."""
    client = FDSNDownloadManager.load(file)

    log_level = logging.INFO
    if verbose >= 1:
        log_level = logging.DEBUG

    logging.root.setLevel(log_level)

    async def run_download() -> None:
        download = asyncio.create_task(client.download())
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
