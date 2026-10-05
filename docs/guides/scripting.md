---
icon: lucide/bot
---

# Scripting and automation

`--non-interactive` (`-n`) replaces the live view with a few `key: value` lines on stdout that a script or an AI agent can parse. `download` and `metadata` accept it.

```sh
fdsn-rush download config.json -n
```

```text
sds_folder: data
metadata_folder: metadata
stations: 1
in_archive: 0
to_download: 1
downloading: https://geofon.gfz.de/
files: 1
no_data: 0
failed: 0
elapsed: 2.785s
status: ok
```

Nothing else is printed, and stderr stays empty.

`stations`, `in_archive`, `to_download`
:   The plan per server: matching stations, day files already in the archive and day files requested.

`files`
:   Day files saved in this run.

`no_data`, `failed`
:   Day files the server answered with 404, and day files that failed otherwise (other HTTP errors, timeouts).

`error`
:   Only present when the run stopped: `<ExceptionName>: <message>`.

`status` is always the last line and sets the exit code:

| Code | `status`  | Meaning                                                                  |
| ---- | --------- | ------------------------------------------------------------------------ |
| `0`  | `ok`      | Finished. Day files the server has no data for (404) are not failures.   |
| `1`  | `error`   | The run stopped, for example because a server was unreachable.           |
| `2`  | `partial` | Finished, but `failed` is not `0`.                                       |

Run again after a `1` or `2`: only the missing day files are requested. See [Resuming and updating archives](resuming.md). Validate a configuration file first with [`check`](../reference/cli.md#check).

## Files in the archive

Every `download` and `metadata` run, interactive or not, writes two files into `sds_folder`:

`fdsn-rush.log`
:   The log, appended to on every run. `-v` adds debug output, including the request URLs. Read it for the details behind an `error` or a `partial` run.

`fdsn-rush-stats.json`
:   Statistics as compact JSON, rewritten at the start, whenever a day file is finished and at the end. Poll it for progress. It is replaced atomically, so it never holds a half-written document.

```json
{"manager":{"start_time":"2024-01-03T10:00:01Z","end_time":"2024-01-03T10:00:05Z","elapsed_seconds":4.4},"writer":{"total_files_saved":1,"total_bytes_written":1900544,"archive_size":1900544},"clients":[{"n_requests":1,"n_bytes_downloaded":1463296,"n_chunks_total":1,"n_completed":1,"n_no_data":0,"n_failed":0,"n_stations":1,"url":"https://geofon.gfz.de/","n_stations_completed":1}]}
```
