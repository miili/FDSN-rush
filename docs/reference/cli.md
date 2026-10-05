---
icon: lucide/terminal
---

# Command line

```text
fdsn-rush [OPTIONS] COMMAND [ARGS]...
```

| Command                 | Purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| [`init`](#init)         | Print a configuration file with all defaults.        |
| [`check`](#check)       | Show what `download` would do, without writing anything. |
| [`metadata`](#metadata) | Download only the station inventory and StationXML.  |
| [`download`](#download) | Download data from FDSN servers into an SDS archive. |
| [`convert`](#convert)   | Sort existing MiniSEED files into an SDS archive.    |

Every command accepts `--help`.

## `init`

Print the default configuration as JSON.

```sh
fdsn-rush init > config.json
```

The defaults are documented in the [configuration reference](configuration.md).

## `check`

Show what [`download`](#download) would do, without writing anything.

```sh
fdsn-rush check FILE
```

It validates the configuration, fetches the station inventory from each server and prints `key: value` lines:

```text
server: https://geofon.gfz.de/
stations: 2
dayfiles: 14
in_archive: 6
to_download: 8
status: ok
```

`stations`
:   Stations that match your selection and blacklist.

`dayfiles`, `in_archive`, `to_download`
:   Channel-days that pass the selection, how many of them are already in the archive, and how many a `download` would request.

The exit code is `0` for `ok`, `1` if a server could not be reached and `2` for an invalid configuration. Nothing is written to disk: no archive, no log file, no StationXML.

## `metadata`

Fetch the station inventory and write the StationXML to `metadata_path`, but download no waveforms.

```sh
fdsn-rush metadata [OPTIONS] FILE
```

It takes the same options as [`download`](#download), `-v` and `-n`.

## `download`

Download waveforms and StationXML as described in a configuration file.

```sh
fdsn-rush download [OPTIONS] FILE
```

`FILE`
:   Path to the configuration file.

`-v`, `--verbose`
:   Show debug output, including the request URLs.

`-n`, `--non-interactive`
:   Run without console output except a few `key: value` lines on stdout, and exit with a status code. See [Scripting and automation](../guides/scripting.md).

Every run writes `fdsn-rush.log` and `fdsn-rush-stats.json` into the SDS archive.

The command exits once all clients have finished. Running it again resumes or extends the archive. See [Resuming and updating archives](../guides/resuming.md).

## `convert`

Sort MiniSEED files from a directory tree into an SDS archive.

```sh
fdsn-rush convert [OPTIONS] INPUT OUTPUT
```

`INPUT`
:   Directory that is searched recursively for MiniSEED files.

`OUTPUT`
:   Root directory of the SDS archive to write.

`--network CODE`
:   Overwrite the network code of all traces.

`--steim 1|2`
:   STEIM compression level. Default: `2`.

`--n-workers N`
:   Number of files converted concurrently. Default: `64`.

See [Converting MiniSEED to SDS](../guides/convert.md) for details and caveats.
