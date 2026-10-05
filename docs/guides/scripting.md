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

`--non-interactive` switches off the live view, progress bars and log lines. The only thing printed is a few `key: value` lines on stdout, and stderr stays empty:

```text
log_file: data/fdsn-rush.log
stats_file: data/fdsn-rush-stats.json
downloading: https://geofon.gfz.de/
files: 3
no_data: 0
failed: 0
elapsed: 4.4s
status: ok
```

`downloading`
:   A server that is being downloaded from. One line per server.

`files`
:   Dayfiles saved in this run.

`no_data`
:   Dayfiles the server answered with 404.

`failed`
:   Dayfiles that failed with another error (HTTP errors other than 404, timeouts).

`error`
:   Only present when something went wrong: `<ExceptionName>: <message>`, or the validation message for `invalid_config`.

`status` is always the last line. The exit code follows it:

| Code | `status`         | Meaning                                                                    |
| ---- | ---------------- | -------------------------------------------------------------------------- |
| `0`  | `ok`             | Finished. Dayfiles the server has no data for (404) are not failures.      |
| `1`  | `error`          | The run stopped, for example because a server was unreachable.             |
| `2`  | `invalid_config` | The configuration file is missing or invalid. Nothing is written to disk.  |
| `3`  | `partial`        | Finished, but `failed` is not `0`.                                         |

Run again after a `1` or `3`: the archive is resumed and only the missing dayfiles are requested. See [Resuming and updating archives](resuming.md).

## Files in the archive

Every `download` run, interactive or not, writes two files into the SDS archive:

`<sds_archive>/fdsn-rush.log`
:   The log, appended to on every run. `-v` adds debug output, including the request URLs. Read it for the details behind an `error` or a `partial` run.

`<sds_archive>/fdsn-rush-stats.json`
:   Statistics as compact JSON, rewritten at the start, whenever a file has been downloaded and at the end. Poll it for progress. It is replaced atomically, so it never holds a half-written document.

```json
{"manager":{"start_time":"2024-01-03T10:00:01Z","end_time":"2024-01-03T10:00:05Z","elapsed_seconds":4.4},"writer":{"total_files_saved":1,"total_bytes_written":1900544,"archive_size":1900544},"clients":[{"n_requests":1,"n_bytes_downloaded":1463296,"n_chunks_total":1,"n_completed":1,"n_no_data":0,"n_failed":0,"n_stations":1,"url":"https://geofon.gfz.de/","n_stations_completed":1}]}
```

`n_chunks_total` and `n_completed` count the planned and finished dayfiles per server. Dayfiles already in the archive are not planned.
