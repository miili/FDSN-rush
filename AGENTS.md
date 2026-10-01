# AGENTS.md

FDSN Rush: async CLI that downloads seismic waveforms from FDSN web services into a local SDS (SeisComP Data Structure) MiniSEED archive, plus StationXML metadata. Also converts loose MiniSEED files into SDS.

## Commands

Project is managed with `uv` (Python package `fdsn_rush`, src layout, hatchling build).

```sh
uv sync                                   # install incl. dev group (pytest, ruff, pre-commit)
uv run fdsn-rush init > config.json       # dump default config
uv run fdsn-rush download config.json -v  # -v = DEBUG logging, -m = metadata only
uv run fdsn-rush convert in/ out-sds/ --steim 2 --network XX
uv run ruff check --fix && uv run ruff format
uv run pre-commit run --all-files         # what CI runs (.github/workflows/pre-commit.yaml)
uv run pytest
```

CI only runs pre-commit (ruff lint + format, whitespace/EOF/yaml hooks); there is no test job. Ruff rule set is in `pyproject.toml` — note `T20` (no `print`), `DTZ` (timezone-aware datetimes only), `G` (no f-strings in logging calls; use `%s` args).

## Architecture

All modules are in `src/fdsn_rush/`.

- `app.py`: Typer CLI (`init`, `download`, `convert`). `download` runs `FDSNDownloadManager.download()` alongside `stats.live_view()` in one asyncio loop.
- `manager.py`: `FDSNDownloadManager` (pydantic model) **is** the JSON config schema. `load()` validates with `strict=True`. Flow: `prepare()` (clients fetch station inventory, writer scans the archive) → `download_metadata()` (StationXML per network into `metadata_path/<NET>.xml`) → per client `get_work()` → `client.download(writer)`. Clients run concurrently in a `TaskGroup`.
  - `get_work()` builds one `DownloadDayfile` per channel per day. `channel_priority` is an ordered list of fnmatch patterns, and the first pattern that yields `>= min_channels_per_station` channels wins for that station-day. Dayfiles already present in the archive are skipped.
- `client.py`: `FDSNClient` does all HTTP via aiohttp against `/fdsnws/station/1/query` (text format for the inventory, xml for metadata) and `/fdsnws/dataselect/1/query` (or `queryauth` with an EIDA token → digest auth middleware). Downloads use an `asyncio.Queue` of dayfiles, `n_workers` workers, and a rate limiter (`asyncio.Condition` ticked at `rate_limit` Hz; it adopts the server's `X-RateLimit-Limit` header). Data is streamed in `chunk_size` chunks straight to the writer.
- `writer.py`: `SDSWriter` appends chunks to `<sds path>.partial` under per-file async locks. `done()` loads the partial file with pyrocko, degaps it, drops traces shorter than `min_length_seconds`, chops to the UTC day, saves as STEIM1/2 MiniSEED, and removes the partial file. `prepare()` deletes leftover `.partial` and zero-byte files. It can optionally register files in a pyrocko Squirrel env.
- `remote_log.py`: `RemoteLog` persists 404s as CSV in `<sds_archive>/remote_errors.log`, so known-missing NSLC/day/host combos are skipped on rerun. Only codes in `LOG_ERROR_CODES` are recorded.
- `models/station.py`: `Channel`/`Station`/`Stations` are parsed from FDSN station text format (17 pipe-separated columns). `parse_stations` drops `AUX_CHANNELS` (SOH channels listed in `utils.py`). `SDS_TEMPLATE` defines the on-disk path, with the julian day zero-padded to 3 digits.
- `utils.py`: `NSL` (an Annotated `_NSL` NamedTuple that parses `"NET.STA.LOC"`; empty parts act as wildcards in `match()`), `NSLC`, `Date` (accepts/serializes `"today"`/`"yesterday"`), `ByteSizeStr`, `FilePath`, `EIDADetails`, `datetime_now()`/`date_today()` (UTC).
- `stats.py`: `Stats` base model. Every instance self-registers in a global `WeakValueDictionary`, and `live_view()` renders all of them as a Rich `Live` panel sorted by `_pos`. To add a stats panel, subclass `Stats` and implement `_render(table)`.
- `convert.py`: standalone MiniSEED → SDS converter (`convert_sds`). It has its own `SDS_TEMPLATE` copy and uses bounded concurrency via an `asyncio.Queue`.

## Conventions

- Every module starts with `from __future__ import annotations` and uses a `logger = logging.getLogger(__name__)`. Log with `%`-style args.
- Config/state objects are pydantic `BaseModel`s. Runtime-only state goes in `PrivateAttr` (`_stats`, `_client`, …). Field `description`s double as config docs.
- Datetimes are always UTC-aware (`datetime_now()`, `DATETIME_MAX`).
- Blocking pyrocko I/O is wrapped in `asyncio.to_thread`.
- Commit messages are lowercase `<area>: <summary>`, e.g. `writer: fix short trace logging spam`, `client: no data bugfix`.

## Gotchas

- `requires-python = ">=3.10"`, but the code uses `asyncio.TaskGroup`, which needs Python 3.11+.
- The tests are stale and partly network-bound. `tests/test_client.py` calls APIs that no longer exist (`prepare(selection=...)` without dates, `n_station()`). `tests/test_manager.py` hits geofon.gfz.de. `tests/test_station.py` needs `tests/data/*.txt` fixtures, which are not in the repo.
- The git remote is `miili/fdsn-fetch` (the old name). The README badges point at `miili/FDSN-rush`.
