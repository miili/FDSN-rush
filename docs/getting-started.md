---
icon: lucide/rocket
---

# Getting started

This page takes you from installation to a working archive. You will download two days of broadband data for two [GEOFON] stations, which is about 140 MB.

## Install

FDSN Rush requires **Python 3.12 or newer**. Install it as a standalone command-line tool:

=== "uv"

    ```sh
    uv tool install fdsn-rush
    ```

=== "pipx"

    ```sh
    pipx install fdsn-rush
    ```

=== "pip"

    ```sh
    pip install fdsn-rush
    ```

Check that the `fdsn-rush` command is available:

```sh
fdsn-rush --version
```

To upgrade later, run `uv tool upgrade fdsn-rush`, `pipx upgrade fdsn-rush` or `pip install -U fdsn-rush`.

??? note "Development version"

    To try unreleased changes, install from the `main` branch:

    ```sh
    uv tool install git+https://github.com/miili/FDSN-rush
    ```

## Create a configuration

Each download is described by a JSON file. Create a project directory and write the default configuration into it:

```sh
mkdir my-archive && cd my-archive
fdsn-rush init > config.json
```

Open `config.json` and change the station selection and the time range, the two values you will change most often:

```json title="config.json" hl_lines="22-34 40"
{
  "writer": {
    "sds_archive": "data",
    "steim_compression": 1,
    "record_length": 4096,
    "min_length_seconds": "PT1M",
    "fix_date_suffixes": false,
    "squirrel_environment": null
  },
  "clients": [
    {
      "url": "https://geofon.gfz.de/",
      "timeout": 30.0,
      "n_workers": 8,
      "n_connections": 24,
      "chunk_size": "4.0MiB",
      "rate_limit": 10,
      "eida_key": null
    }
  ],
  "metadata_path": "metadata",
  "time_range": [
    "2026-09-01",
    "2026-09-03"
  ],
  "station_selections": [
    {
      "selection": "StationSelection",
      "exclude_stations": [],
      "include_restricted": true,
      "stations": [
        "GE.APE.",
        "GE.STU."
      ]
    }
  ],
  "channel_priority": [
    "HH[ZNE12]",
    "EH[ZNE12]",
    "HN[ZNE12]"
  ],
  "min_channels_per_station": 3,
  "min_sampling_rate": 100.0,
  "max_sampling_rate": 200.0
}
```

This configuration does the following:

- It asks GEOFON (`clients`) for stations `APE` and `STU` of the `GE` network (`station_selections`).
- It downloads the UTC days **September 1 and 2**. The end of `time_range` is exclusive.
- It prefers `HH` channels and falls back to `EH`, then `HN` (`channel_priority`). It takes a channel group only if all three components are available (`min_channels_per_station`).
- It writes waveforms to `data/` and StationXML to `metadata/`.

!!! tip

    `time_range` accepts `"today"` and `"yesterday"` as well as ISO dates. With `["2026-01-01", "today"]` you get everything up to and including yesterday, the last complete day.

## Download

```sh
fdsn-rush download config.json
```

FDSN Rush first fetches the station inventory and the StationXML. Then it checks the archive and downloads the missing day files. A live panel shows the download speed, the number of finished stations and the progress:

```text
INFO     Got 2 stations from https://geofon.gfz.de/
INFO     Downloading metadata for network GE (2 stations)
INFO     Discovered 12 remote dayfiles
INFO     Found 12 dayfiles to download
INFO     Starting download from https://geofon.gfz.de/ with 8 workers
INFO     Finished download GE.APE..HHZ for 2026-09-01 (10.7MiB ↓1.0MiB/s)
INFO     Saved data/2026/GE/APE/HHZ.D/GE.APE..HHZ.D.2026.244
...
INFO     All downloads completed successfully.
```

Add `-v` for debug output, including the exact request URLs.

## Inspect the result

```text
my-archive/
├── config.json
├── data/
│   └── 2026/
│       └── GE/
│           ├── APE/
│           │   ├── HHE.D/
│           │   │   ├── GE.APE..HHE.D.2026.244
│           │   │   └── GE.APE..HHE.D.2026.245
│           │   ├── HHN.D/ ...
│           │   └── HHZ.D/ ...
│           └── STU/ ...
└── metadata/
    └── GE.xml
```

Each file holds one channel for one UTC day, named `NET.STA.LOC.CHA.D.YEAR.DOY` with the day of year zero-padded to three digits. This is the standard SDS layout. Read the data with the tools you already use, as shown in [Working with the archive](guides/using-the-archive.md).

## Run it again

Run the same command a second time:

```sh
fdsn-rush download config.json
```

```text
INFO     Discovered 12 remote dayfiles
INFO     Found 12 dayfiles already downloaded in the archive
INFO     Found 0 dayfiles to download
```

Nothing is downloaded twice. Extend the time range, or use `"today"` as the end, and the next run fetches only the new days. If you stop a download with ++ctrl+c++, the same command picks up where it left off. See [Resuming and updating archives](guides/resuming.md).

## Next steps

- [Select stations and channels](guides/selecting-data.md): by code, area or radius, exclusions and channel priorities.
- [Restricted data with EIDA tokens](guides/restricted-data.md): download embargoed data.
- [Configuration reference](reference/configuration.md): every option explained.

[GEOFON]: https://geofon.gfz.de/
