---
icon: lucide/bot
---

# Scripting and automation

`--non-interactive` replaces the live view with output that a script, a scheduler or an AI agent can parse.

```sh
fdsn-rush download config.json --non-interactive > summary.json
echo $?
```

## What you get

| Where                              | What                                                                  |
| ---------------------------------- | --------------------------------------------------------------------- |
| stdout                             | One JSON document, printed when the run ends.                         |
| stderr                             | Plain log lines with UTC timestamps. No colours, no progress bars.    |
| `<sds_archive>/fdsn-rush.log`      | The same log lines. The file is appended to on every run.             |
| `<sds_archive>/fdsn-rush-stats.json` | The JSON document from stdout. Change the path with `--stats-file`. |

`-v` adds debug output, including the request URLs, to stderr and to the log file.

## Exit codes

| Code | `status`  | Meaning                                                                          |
| ---- | --------- | -------------------------------------------------------------------------------- |
| `0`  | `ok`      | Finished. Dayfiles that the server has no data for (404) are not failures.       |
| `1`  | `error`   | The run stopped, for example because a server was unreachable.                   |
| `2`  | `error`   | The configuration file is missing or invalid. No log file is written.            |
| `3`  | `partial` | Finished, but some dayfiles failed (HTTP errors other than 404, timeouts).       |

Run again after a `1` or `3`: the archive is resumed and only the missing dayfiles are requested. See [Resuming and updating archives](resuming.md).

## The summary

```json
{
  "status": "ok",
  "version": "0.2.0",
  "config": "config.json",
  "metadata_only": false,
  "started": "2024-01-03T10:00:00+00:00",
  "finished": "2024-01-03T10:00:05+00:00",
  "error": null,
  "sds_archive": "data",
  "log_file": "data/fdsn-rush.log",
  "stats_file": "data/fdsn-rush-stats.json",
  "time_range": ["2024-01-01", "2024-01-02"],
  "stats": {
    "manager": { "start_time": "…", "end_time": "…", "elapsed_seconds": 4.4 },
    "writer": { "total_files_saved": 1, "total_bytes_written": 1900544, "archive_size": 1900544 },
    "clients": [
      {
        "url": "https://geofon.gfz.de/",
        "n_requests": 1,
        "n_bytes_downloaded": 1463296,
        "n_chunks_total": 1,
        "n_completed": 1,
        "n_no_data": 0,
        "n_failed": 0,
        "n_stations": 1,
        "n_stations_completed": 1
      }
    ]
  },
  "exit_code": 0
}
```

`error`
:   `null`, or `{"type": ..., "message": ...}`. The type is `config` for a configuration problem, otherwise the name of the exception.

`stats`
:   `null` when the configuration could not be loaded. `n_no_data` counts dayfiles answered with 404, `n_failed` counts the other failures.

`n_chunks_total`, `n_completed`
:   Dayfiles planned and finished per client. Dayfiles already in the archive are not planned.
