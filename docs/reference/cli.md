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

??? example "`fdsn-rush init --help`"

    ```python exec="on" result="ansi"
    from typer.testing import CliRunner

    from fdsn_rush.app import app

    env = {"COLUMNS": "80", "FORCE_COLOR": "1"}
    print(CliRunner().invoke(app, ["init", "--help"], env=env, color=True).output)
    ```

The defaults are documented in the [configuration reference](configuration.md).

## `check`

Validate a configuration file.

```sh
fdsn-rush check FILE
```

??? example "`fdsn-rush check --help`"

    ```python exec="on" result="ansi"
    from typer.testing import CliRunner

    from fdsn_rush.app import app

    env = {"COLUMNS": "80", "FORCE_COLOR": "1"}
    print(CliRunner().invoke(app, ["check", "--help"], env=env, color=True).output)
    ```

It loads the file in strict mode, as `download` does, and prints `FILE is valid`. An invalid file raises the validation error and exits with `1`. Nothing is contacted or written.

## `metadata`

Fetch the station inventory and write the StationXML to `metadata_path`, but download no waveforms.

```sh
fdsn-rush metadata FILE
```

??? example "`fdsn-rush metadata --help`"

    ```python exec="on" result="ansi"
    from typer.testing import CliRunner

    from fdsn_rush.app import app

    env = {"COLUMNS": "80", "FORCE_COLOR": "1"}
    print(CliRunner().invoke(app, ["metadata", "--help"], env=env, color=True).output)
    ```

## `download`

Download waveforms and StationXML as described in a configuration file.

```sh
fdsn-rush download [OPTIONS] FILE
```

??? example "`fdsn-rush download --help`"

    ```python exec="on" result="ansi"
    from typer.testing import CliRunner

    from fdsn_rush.app import app

    env = {"COLUMNS": "80", "FORCE_COLOR": "1"}
    print(CliRunner().invoke(app, ["download", "--help"], env=env, color=True).output)
    ```

`FILE`
:   Path to the configuration file.

`-v`, `--verbose`
:   Show debug output, including the request URLs.

`-n`, `--non-interactive`
:   Run without console output except a few `key: value` lines on stdout, and exit with a status code. See [Scripting and automation](../guides/scripting.md).

Every run writes its log to `<config>.log` next to the configuration file (`config.json` → `config.log`) and keeps `fdsn-rush-stats.json` in the SDS archive up to date.

The command exits once all clients have finished. Running it again resumes or extends the archive. See [Resuming and updating archives](../guides/resuming.md).

## `convert`

Sort MiniSEED files from a directory tree into an SDS archive.

```sh
fdsn-rush convert [OPTIONS] INPUT OUTPUT
```

??? example "`fdsn-rush convert --help`"

    ```python exec="on" result="ansi"
    from typer.testing import CliRunner

    from fdsn_rush.app import app

    env = {"COLUMNS": "80", "FORCE_COLOR": "1"}
    print(CliRunner().invoke(app, ["convert", "--help"], env=env, color=True).output)
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
