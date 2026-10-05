---
icon: lucide/bot
---

# Scripting and automation

`--non-interactive` replaces the live view with output that a script, a scheduler or an AI agent can parse.

```sh
fdsn-rush download config.json --non-interactive > report.json
echo $?
```

## Output

| Where                                | What                                                                              |
| ------------------------------------ | --------------------------------------------------------------------------------- |
| stdout                               | One compact JSON report, printed when the run ends.                               |
| stderr and `<sds_archive>/fdsn-rush.log` | Plain log lines with UTC timestamps. The file is appended to on every run. `-v` adds debug output. |
| `<sds_archive>/fdsn-rush-stats.json` | The same report, rewritten every `--stats-interval` seconds (default 5) while the run is going. Change the path with `--stats-file`. |

Poll the stats file for progress. It is replaced atomically, so it never holds a half-written document. `status` is `running` until the run ends.

## Exit codes

| Code | `status`         | Meaning                                                                    |
| ---- | ---------------- | -------------------------------------------------------------------------- |
| `0`  | `ok`             | Finished. Dayfiles the server has no data for (404) are not failures.      |
| `1`  | `error`          | The run stopped, for example because a server was unreachable.             |
| `2`  | `invalid_config` | The configuration file is missing or invalid. No log file is written.      |
| `3`  | `partial`        | Finished, but some dayfiles failed (HTTP errors other than 404, timeouts). |

Run again after a `1` or `3`: the archive is resumed and only the missing dayfiles are requested. See [Resuming and updating archives](resuming.md).

## The report

```json
{"status":"ok","updated":"2024-01-03T10:00:05Z","log_file":"data/fdsn-rush.log","stats_file":"data/fdsn-rush-stats.json","time_range":["2024-01-01","2024-01-02"],"stats":{"manager":{"start_time":"2024-01-03T10:00:01Z","end_time":"2024-01-03T10:00:05Z","elapsed_seconds":4.4},"writer":{"total_files_saved":1,"total_bytes_written":1900544,"archive_size":1900544},"clients":[{"n_requests":1,"n_bytes_downloaded":1463296,"n_chunks_total":1,"n_completed":1,"n_no_data":0,"n_failed":0,"n_stations":1,"url":"https://geofon.gfz.de/","n_stations_completed":1}]}}
```

Fields that are not set, such as `error` on success, are left out.

`error`
:   `"<ExceptionName>: <message>"`, or the validation message for `invalid_config`.

`stats.clients[]`
:   One entry per server. `n_chunks_total` and `n_completed` count the planned and finished dayfiles. Dayfiles already in the archive are not planned. `n_no_data` counts 404 answers and `n_failed` the other failures.
