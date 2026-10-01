# AGENTS.md

FDSN Rush: async CLI that downloads seismic waveforms from FDSN web services into a local SDS (SeisComP Data Structure) MiniSEED archive, plus StationXML metadata. Also converts loose MiniSEED files into SDS.

## Commands

Project is managed with `uv` (Python package `fdsn_rush`, src layout, hatchling build). Requires Python 3.11+.

```sh
uv sync                                   # install incl. dev group (pytest, pytest-asyncio, ruff, prek)
uv run fdsn-rush init > config.json       # dump default config
uv run fdsn-rush download config.json -v  # -v = DEBUG logging, -m = metadata only
uv run fdsn-rush convert in/ out-sds/ --steim 2 --network XX
uv run prek run --all-files               # lint + format, same hooks as CI
uv run pytest                             # offline, < 1 s
```

If another virtualenv is active, `uv` ignores the project `.venv` and warns. Prefix commands with `env -u VIRTUAL_ENV` (or deactivate it).

CI (`.github/workflows/`):
- `pre-commit.yaml` runs the `.pre-commit-config.yaml` hooks through prek: ruff lint + format, plus whitespace/EOF/yaml checks.
- `tests.yaml` runs `uv sync --locked && uv run pytest` on Python 3.11–3.14. Keep `uv.lock` in sync (`uv lock`) or CI fails.

Ruff: the rule set is in `pyproject.toml`, and ruff infers the `py311` target from `requires-python`. Rules that bite:
- `T20`: no `print`.
- `DTZ`: datetimes must be timezone-aware.
- `G`: no f-strings in logging calls; use `%s` args.
- `UP017`: use `datetime.UTC`, not `timezone.utc`.
- `ASYNC230`: no `open()` inside `async def`. Move file I/O into a sync helper and call it via `asyncio.to_thread`.

The prek hook pins a newer ruff (v0.16) than older dev installs. Trust `prek run` over a stale local `ruff`.

## Architecture

All modules are in `src/fdsn_rush/`.

- `app.py`: Typer CLI (`init`, `download`, `convert`). `download` runs `FDSNDownloadManager.download()` alongside `stats.live_view()` in one asyncio loop.
- `manager.py`: `FDSNDownloadManager` (pydantic model) **is** the JSON config schema. `load()` validates with `strict=True`. Flow: `prepare()` (clients fetch station inventory, writer scans the archive) → `download_metadata()` (StationXML per network into `metadata_path/<NET>.xml`) → per client `get_work()` → `client.download(writer)`. Clients run concurrently in a `TaskGroup`.
  - `get_work()` builds one `DownloadDayfile` per channel per day. `channel_priority` is an ordered list of fnmatch patterns, and the first pattern that yields `>= min_channels_per_station` channels wins for that station-day. Dayfiles already present in the archive are skipped.
- `client.py`: `FDSNClient` does all HTTP via aiohttp against `/fdsnws/station/1/query` (inventory: one text-format request per network, merged with `Stations.extend`, and a body containing `Error 404` is treated as "no stations"; metadata: StationXML) and `/fdsnws/dataselect/1/query` (or `queryauth` with an EIDA token → digest auth middleware). Downloads use an `asyncio.Queue` of dayfiles, `n_workers` workers, and a rate limiter (`asyncio.Condition` ticked at `rate_limit` Hz; it adopts the server's `X-RateLimit-Limit` header). Data is streamed in `chunk_size` chunks straight to the writer.
- `writer.py`: `SDSWriter` appends chunks to `<sds path>.partial` under per-file async locks. `done()` loads the partial file with pyrocko, degaps it, drops traces shorter than `min_length_seconds`, chops to the UTC day, saves as STEIM1/2 MiniSEED, and removes the partial file. `prepare()` deletes leftover `.partial` and zero-byte files. It can optionally register files in a pyrocko Squirrel env.
- `remote_log.py`: `RemoteLog` persists 404s (read from `ClientResponseError.status`; `.code` is deprecated) as CSV in `<sds_archive>/remote_errors.log`, so known-missing NSLC/day/host combos are skipped on rerun. Only codes in `LOG_ERROR_CODES` are recorded.
- `models/station.py`: `Channel`/`Station`/`Stations` are parsed from FDSN station text format (17 pipe-separated columns). `parse_stations` drops `AUX_CHANNELS` (SOH channels listed in `utils.py`). `SDS_TEMPLATE` defines the on-disk path, with the julian day zero-padded to 3 digits.
- `utils.py`: `NSL` (an Annotated `_NSL` NamedTuple that parses `"NET.STA.LOC"`). `selector.match(station_nsl)` treats `self` as the pattern: empty parts are wildcards, and the rest are fnmatch patterns (e.g. `XX.STA*`)., `NSLC`, `Date` (accepts/serializes `"today"`/`"yesterday"`), `ByteSizeStr`, `FilePath`, `EIDADetails`, `datetime_now()`/`date_today()` (UTC).
- `stats.py`: `Stats` base model. Every instance self-registers in a global `WeakValueDictionary`, and `live_view()` renders all of them as a Rich `Live` panel sorted by `_pos`. To add a stats panel, subclass `Stats` and implement `_render(table)`.
- `convert.py`: standalone MiniSEED → SDS converter (`convert_sds`). It has its own `SDS_TEMPLATE` copy and uses bounded concurrency via an `asyncio.Queue`.

## Conventions

- Every module starts with `from __future__ import annotations` and uses a `logger = logging.getLogger(__name__)`. Log with `%`-style args.
- Config/state objects are pydantic `BaseModel`s. Runtime-only state goes in `PrivateAttr` (`_stats`, `_client`, …). Field `description`s double as config docs.
- Datetimes are always UTC-aware (`datetime_now()`, `DATETIME_MAX`).
- Blocking pyrocko and file I/O is wrapped in `asyncio.to_thread`.
- Validators raise `ValueError`, never `TypeError`. pydantic v2 only turns `ValueError`/`AssertionError` into a `ValidationError`, so `TRY004` is silenced there with `noqa`.
- Commit messages are lowercase `<area>: <summary>`, e.g. `writer: fix short trace logging spam`, `client: no data bugfix`.

## Tests

Tests are fully offline. `asyncio_mode = "auto"` is set, so `async def test_*` needs no marker. Shared fixtures are in `tests/conftest.py`:
- `STATION_TEXT`: an inline FDSN station text inventory. It covers the cases the manager must handle:
  - STA01: HH channels, plus an LH channel with too low a sampling rate and an aux LDO channel.
  - STA02: EH channels only; the fake server returns 404 for EHE.
  - STA03: a single HHZ channel whose epoch ends on 2024-01-01.
- `make_mseed`: a factory that builds real MiniSEED bytes with pyrocko.
- `fake_fdsn`: an `aiohttp.test_utils.TestServer` serving station and dataselect queries. Point a `FDSNClient(url=fake_fdsn.url)` at it. Every dataselect query is recorded in `fake_fdsn.dataselect_requests`.

Test modules import constants and types from `conftest` directly (`from conftest import STATION_TEXT`). When changing download, writer or rerun behaviour, extend `tests/test_manager.py::test_download`. It runs a full download twice and checks that the second run makes no new requests.

## Gotchas

- `.venv` uses Python 3.14, which needs pyrocko ≥ 2026.6 and scipy ≥ 1.17 (older versions have no cp314 wheels and fail to build from source). If a sync tries to build scipy or pyrocko, upgrade the lock rather than installing system BLAS.
- `Stats` instances register in a module-global registry, and `writer.FILE_LOCKS` is module-global too. Both are harmless in tests, but keep it in mind when you create many managers in one process.
- `client.prepare()` appends to `available_stations`, so calling it twice on one client duplicates stations.
- The git remote is `miili/fdsn-fetch` (the old name). The README badges point at `miili/FDSN-rush`.
- The git remote is `miili/fdsn-fetch` (the old name). The README badges point at `miili/FDSN-rush`.
