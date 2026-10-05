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
| [`download`](#download) | Download data from FDSN servers into an SDS archive. |
| [`convert`](#convert)   | Sort existing MiniSEED files into an SDS archive.    |

Every command accepts `--help`.

## `init`

Print the default configuration as JSON.

```sh
fdsn-rush init > config.json
```

The defaults are documented in the [configuration reference](configuration.md).

## `download`

Download waveforms and StationXML as described in a configuration file.

```sh
fdsn-rush download [OPTIONS] FILE
```

`FILE`
:   Path to the configuration file.

`-m`, `--metadata-only`
:   Fetch the station inventory and write the StationXML, but download no waveforms.

`-v`, `--verbose`
:   Show debug output, including the request URLs.

`-n`, `--non-interactive`
:   Run without the live view, for scripts and agents. Log lines go to stderr and to `<sds_archive>/fdsn-rush.log`, a JSON report goes to stdout, and the exit code reports the outcome. See [Scripting and automation](../guides/scripting.md).

`--stats-file PATH`
:   Write the JSON report to `PATH` (needs `--non-interactive`). Default: `<sds_archive>/fdsn-rush-stats.json`.

`--stats-interval SECONDS`
:   How often the stats file is rewritten while running (needs `--non-interactive`). Default: `5`.

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
