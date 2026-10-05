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
| [`check`](#check)       | Validate a configuration file.                       |
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

Validate a configuration file.

```sh
fdsn-rush check FILE
```

It loads the file in strict mode, as `download` does, and prints `FILE is valid`. An invalid file raises the validation error and exits with `1`. Nothing is contacted or written.

## `metadata`

Fetch the station inventory and write the StationXML to `metadata_path`, but download no waveforms.

```sh
fdsn-rush metadata FILE
```

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

Every run appends its log to `<config>.log` next to the configuration file (`config.json` → `config.log`) and keeps `fdsn-rush-stats.json` in the SDS archive up to date.

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
