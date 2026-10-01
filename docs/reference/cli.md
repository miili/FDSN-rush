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
