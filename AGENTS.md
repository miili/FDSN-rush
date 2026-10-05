# AGENTS.md

FDSN Rush: async CLI that downloads seismic waveforms from FDSN web services into a local SDS (SeisComP Data Structure) MiniSEED archive, plus StationXML metadata. Also converts loose MiniSEED files into SDS.

## Commands

Project is managed with `uv` (Python package `fdsn_rush`, src layout, hatchling build). Requires Python 3.12+.

```sh
uv sync                                   # install incl. dev group (pytest, pytest-asyncio, ruff, prek)
uv run fdsn-rush init > config.json       # dump default config
uv run fdsn-rush download config.json -v  # -v = DEBUG logging
uv run fdsn-rush metadata config.json    # inventory + StationXML only
uv run fdsn-rush check config.json       # validate the config only
uv run fdsn-rush download config.json -n  # non-interactive: only key: value lines on stdout
uv run fdsn-rush convert in/ out-sds/ --steim 2 --network XX
uv run prek run --all-files               # lint + format, same hooks as CI
uv run pytest                             # offline, < 1 s
uv run --only-group docs zensical serve   # docs preview on localhost:8000
uv run --only-group docs zensical build --clean --strict  # what CI runs
(cd reference && just)                    # fetch FDSN spec PDFs + .txt (needs just, curl, pdftotext)
```

If another virtualenv is active, `uv` ignores the project `.venv` and warns. Prefix commands with `env -u VIRTUAL_ENV` (or deactivate it).

CI (`.github/workflows/`):
- `pre-commit.yaml` runs the `.pre-commit-config.yaml` hooks through prek: ruff lint + format, plus whitespace/EOF/yaml checks.
- `tests.yaml` runs `uv sync --locked && uv run pytest` on Python 3.12–3.14. Keep `uv.lock` in sync (`uv lock`) or CI fails.
- `docs.yaml` builds the docs strictly on every PR and push, and deploys `site/` to GitHub Pages from `main` only. The repo's Pages source must be set to "GitHub Actions".
- `release.yaml` builds the sdist and wheel on every push to `main` (and on PRs touching packaging). On a `v*` tag it also runs `tests.yaml` (via `workflow_call`), publishes to PyPI with trusted publishing (environment `pypi`), and creates a GitHub release with generated notes.
- `astral-sh/setup-uv` has no floating major tags. Pin a full version (`@v10.2.0`).

Ruff: the rule set is in `pyproject.toml`, and ruff infers the `py312` target from `requires-python`. Rules that bite:
- `T20`: no `print`.
- `DTZ`: datetimes must be timezone-aware.
- `G`: no f-strings in logging calls; use `%s` args.
- `UP017`: use `datetime.UTC`, not `timezone.utc`.
- `ASYNC230`: no `open()` inside `async def`. Move file I/O into a sync helper and call it via `asyncio.to_thread`.

The prek hook pins a newer ruff (v0.16) than older dev installs. Trust `prek run` over a stale local `ruff`.

## Architecture

All modules are in `src/fdsn_rush/`.

- `app.py`: Typer CLI (`init`, `check`, `metadata`, `download`, `convert`). `download` loads the config, adds a file handler for `<config>.log` (next to the config file) to the root logger, runs `manager.download()` with `stats.live_view()`, then prints the summary and exits with `EXIT_CODES[status]` (0 ok, 1 error, 2 partial). `-n` sets `utils.NON_INTERACTIVE` and `rich.reconfigure(quiet=True)`, which also hides the live view. `metadata` runs `manager.download(metadata_only=True)`; `check` only loads (validates) the config.
- `manager.py`: `FDSNDownloadManager` (pydantic model) **is** the JSON config schema. `load()` validates with `strict=True`. Flow: `prepare()` (clients fetch station inventory, writer scans the archive) → `download_metadata()` (StationXML per network into `metadata_path/<NET>.xml`) → per client `get_work()` → `client.download(writer)`. Clients run concurrently in a `TaskGroup`. `download()` rewrites `<sds_archive>/fdsn-rush-stats.json` (a `StatsReport`, atomic) at the start, at the end and whenever a client sets the shared `_file_done` event (once per finished work item). Non-interactive output goes through `utils.report(key, value)`, a no-op unless `utils.NON_INTERACTIVE` is set; call it from any module. Keep it to a few lines: agents pay for every token. `status:` is always last.
  - `get_work()` builds one `DownloadDayfile` per channel per day. `channel_priority` is an ordered list of fnmatch patterns, and the first pattern that yields `>= min_channels_per_station` channels wins for that station-day. Dayfiles already present in the archive are skipped.
- `client.py`: `FDSNClient` does all HTTP via aiohttp against `/fdsnws/station/1/query` (inventory: one POSTed text-format request per network, merged with `Stations.extend`, and a body containing `Error 404` is treated as "no stations"; metadata: StationXML, also POSTed) and `/fdsnws/dataselect/1/query` (or `queryauth` with an EIDA token → digest auth middleware). Downloads use an `asyncio.Queue` of dayfiles, `n_workers` workers, and a rate limiter (`asyncio.Condition` ticked at `rate_limit` Hz; it adopts the server's `X-RateLimit-Limit` header). Data is streamed in `chunk_size` chunks straight to the writer.
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

## FDSN protocol notes

The specs are `fdsnws-station-1.1` and `fdsnws-dataselect-1.1`. Fetch them with `cd reference && just` (git-ignored), then `grep` the `.txt` files. `reference/NOTES.md` summarizes the parameters, defaults and text-format columns. In the spec tables, the "Support" column (required/optional) says what a *server* must implement, not what a client must send.

Spec errata (the PDFs contradict themselves; do not copy these):
- The station table lists the `format` default as `text`, but the prose says StationXML (`xml`) is the default. `xml` is correct.
- The station table gives the `maxlongitude` default as `108.0`; it should be `180.0`.
- The station POST example has an end time before its start time.
- The station changelog mentions a "page 12" for the text template. The PDF has 9 pages.
- The channel text template calls a column `ScaleFrequency`, but the example header says `ScaleFreq`. The code ignores header names.
- The bounding-box example's prose says longitude 112, but its URL uses `minlongitude=122`.

Differences between the code and the spec, to check when working on `client.py`:
- Fixed: waveform requests send a blank location as `--`, times as `YYYY-MM-DDTHH:MM:SS` (`_fdsn_time`) and `format=miniseed`, and inventory requests group by sorted network so each network is queried once. The fake server in `tests/conftest.py` rejects anything else with 400, so a regression fails `test_download`.
- Fixed: station requests (`prepare`, `download_metadata`) are POSTed via `_post_body`: `key=value` option lines, then one `NET STA LOC * START END` line per selection, empty parts as `*`. This avoids the GET cross product (`A.1` + `B.2` becoming `A,B` x `1,2`) and URL length limits. Verified on IRIS and GEOFON. Why not a joined list: `location=,00` returns only `00` for `IU.ANMO` on IRIS, because an empty list entry is the *blank* code.
- Real servers: IRIS 301-redirects http and answers `location=` (empty) and `--` with blank-location channels only. Live checks are in `tests/test_live.py`.
- Not used so far: `quality`, `minimumlength`, `longestonly`, `updatedafter`, `matchtimeseries`, `includerestricted`, `includeavailability`, geographic filters and the `version` method.
- Not in the spec at all: `/fdsnws/dataselect/1/auth` (EIDA token exchange) and the `X-RateLimit-Limit` header. 429 appears only as a label in `ERRORS`, and nothing retries it.
- Text-format times have no zone, so `Channel.from_line` produces naive datetimes. That is harmless while only `.date()` is compared.

## Tests

Tests are offline, except `tests/test_live.py`, which hits IRIS/GEOFON and only runs with `FDSN_RUSH_LIVE=1`. `asyncio_mode = "auto"` is set, so `async def test_*` needs no marker. Shared fixtures are in `tests/conftest.py`:
- `STATION_TEXT`: an inline FDSN station text inventory. It covers the cases the manager must handle:
  - STA01: HH channels, plus an LH channel with too low a sampling rate and an aux LDO channel.
  - STA02: EH channels only; the fake server returns 404 for EHE.
  - STA03: a single HHZ channel whose epoch ends on 2024-01-01.
- `make_mseed`: a factory that builds real MiniSEED bytes with pyrocko.
- `fake_fdsn`: an `aiohttp.test_utils.TestServer` serving station and dataselect queries. Point a `FDSNClient(url=fake_fdsn.url)` at it. Every dataselect query is recorded in `fake_fdsn.dataselect_requests`.

`tests/test_cli.py` is the end-to-end test: it runs `download --non-interactive` through `CliRunner` against `fake_fdsn`. The CLI starts its own event loop, so the tests call it with `await asyncio.to_thread(runner.invoke, ...)`; otherwise it blocks the loop that serves the fake FDSN.

Test modules import constants and types from `conftest` directly (`from conftest import STATION_TEXT`). When changing download, writer or rerun behaviour, extend `tests/test_manager.py::test_download`. It runs a full download twice and checks that the second run makes no new requests.

## Releasing

Published on PyPI as `fdsn-rush` under GPL-3.0-or-later. The version is derived from git tags by `hatch-vcs`. There is no version in `pyproject.toml`. Untagged builds get versions like `0.1.dev56+g965c0dc`.

```sh
git tag -a v0.2.0 -m "v0.2.0" && git push origin v0.2.0   # triggers release.yaml
SETUPTOOLS_SCM_PRETEND_VERSION=0.2.0 uv build             # local build with a fixed version
```

Tags must be `v` + a PEP 440 version (`v0.2.0`, `v0.3.0rc1`), and CI checks that the built files carry exactly that version. The sdist ships `src/` and `tests/` but not `docs/`, so `tests/test_docs.py` skips when the docs are missing.

## Documentation

The user docs are built with [Zensical](https://zensical.org) (config in `zensical.toml`, pages in `docs/`) and published at https://miili.github.io/FDSN-rush/.
- `docs/getting-started.md` is a walkthrough with real output from GEOFON (`GE.APE`, `GE.STU`).
- `docs/guides/` holds task-oriented pages.
- `docs/reference/` holds the configuration and CLI references.

Style: professional and hands-on. Lead with the command or config snippet, keep the explanation short, and state behaviour exactly (e.g. the `time_range` end is exclusive). Verify examples against the code or a real run before documenting them.

When you change behaviour, update the docs in the same change:
- New or renamed config fields go into `docs/reference/configuration.md` as a `` `name` `` definition-list entry. `tests/test_docs.py` fails if a pydantic config field is missing.
- CLI changes go into `docs/reference/cli.md`.
- New pages must be added to `nav` in `zensical.toml`.

## Gotchas

- `.venv` uses Python 3.14, which needs pyrocko ≥ 2026.6 and scipy ≥ 1.17 (older versions have no cp314 wheels and fail to build from source). If a sync tries to build scipy or pyrocko, upgrade the lock rather than installing system BLAS.
- `Stats` instances register in a module-global registry, and `writer.FILE_LOCKS` is module-global too. Both are harmless in tests, but keep it in mind when you create many managers in one process.
- `client.prepare()` appends to `available_stations`, so calling it twice on one client duplicates stations.
- Clients download in parallel and each plans its work independently. Two clients serving the same station download the same day file concurrently into one `.partial` file. The docs warn about this, but it is not handled in code.
- Config models use pydantic's default `extra="ignore"`, so misspelled options are silently dropped.
- `convert` only scans files whose name contains a dot (`rglob("*.*")`). It appends to existing day files, so converting the same input twice duplicates data.
- The git remote is `miili/fdsn-fetch` (the old name). The README badges point at `miili/FDSN-rush`.
