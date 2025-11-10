# FDSN Rush

*Fast and modern FDSN Download*

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Pre-commit](https://github.com/miili/FDSN-rush/actions/workflows/pre-commit.yaml/badge.svg)](https://github.com/miili/FDSN-rush/actions/workflows/pre-commit.yaml)

*FDSN Rush* allows to download seismic waveform data from [FDSN](https://www.fdsn.org/services/) servers in a fast, reproducible and reliable way.

## Installation

Installation using Python's pip

```sh
pip install git+https://github.com/miili/fdsn-rush
```

The user CLI is exposed as `fdsn-rush` command.

```sh
$> fdsn-rush


 Usage: fdsn-rush [OPTIONS] COMMAND [ARGS]...

 FDSN Download to SDS Archive

╭─ Options ────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────╮
│ init       Print the configuration.                                                  │
│ download   Download data from FDSN to local SDS archive.                             │
│ convert    Convert existing MiniSEED files to SDS archive.                           │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

## Download data

Create a new config file and write it out to `config.json` with the following command:

```sh
fdsn-rush init > config.json
```

In this config file configure:

1. FDSN servers to fetch data from, in this example <https://geofon.gfz.de>.
2. Timerange to download, here substitutes `today` and `yesterday` are allowed.
3. Stations NSL codes (SEED convention `<network>.<station>.<location>`) to download.
4. The channel priority. In the default config `HH` channels would have the highest priority.

If you have an [EIDA](https://www.orfeus-eu.org/data/eida/) key to access restricted waveform data, put the path into `Client.eida_key`.

The MiniSeed data will be writen out into an [SDS](https://www.seiscomp.de/seiscomp3/doc/applications/slarchive/SDS.html) directory structure located at `data/`. All metadata will be saved in a `metadata/` folder.

```json{
  "writer": {
    "sds_archive": "data/",
    "steim_compression": 1,
    "record_length": 4096,
    "min_length_seconds": "PT1M",
    "squirrel_environment": null
  },
  "clients": [
    {
      "url": "https://geofon.gfz.de/",
      "timeout": 30.0,
      "n_workers": 8,
      "n_connections": 24,
      "chunk_size": "4.0MiB",
      "rate_limit": 20,
      "eida_key": null
    }
  ],
  "metadata_path": "metadata",
  "time_range": [
    "2025-11-03",
    "today"
  ],
  "station_selection": [
    "2D.."
  ],
  "channel_priority": [
    "HH[ZNE12]",
    "EH[ZNE12]",
    "HN[ZNE12]"
  ],
  "station_blacklist": [],
  "min_channels_per_station": 3,
  "min_sampling_rate": 100.0,
  "max_sampling_rate": 200.0
}
```

### Start the Download

Start the asynchronous download with:

```sh
fdsn-rush download config.json
```

### Converting existing MiniSeed data to SDS Archive

This can be useful to convert unstructured MiniSeed data to an [SDS archive structure](https://www.seiscomp.de/seiscomp3/doc/applications/slarchive/SDS.html).

```sh
fdsn-rush convert in-folder/ out-sds-folder/
```
