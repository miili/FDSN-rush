---
icon: lucide/settings
---

# Configuration

A download is configured in a single JSON file. Generate one with all defaults filled in:

```sh
fdsn-rush init > config.json
```

??? example "Default configuration"

    ```python exec="on" result="json"
    from fdsn_rush.manager import FDSNDownloadManager

    print(FDSNDownloadManager().model_dump_json(indent=2))
    ```

You can leave out any option, and it takes its default. The smallest useful configuration is:

```json title="config.json"
{
  "station_selection": {"selection": "StationSelection", "stations": ["GE.APE"]},
  "time_range": ["2026-09-01", "2026-09-03"]
}
```

The file is validated strictly when it is loaded. Malformed values are reported with the name of the option before any request is made. Relative paths are resolved against the directory you run `fdsn-rush` from.

!!! warning "Check the spelling of options"

    Unknown options are ignored. A misspelled option such as `station_selecton` therefore leaves the real option at its default.

## Top level

`station_selection`
:   **Object** · default: all stations of network `2D` · see [Station selection](#station-selection)

    Which stations to download: by code, in a bounding box or within a radius.

`time_range`
:   **Pair of dates** · default: the last seven days, `["<7 days ago>", "today"]`

    `[start, end]` as ISO dates (`"2026-09-01"`) or `"today"` / `"yesterday"`. UTC days from `start` up to, but not including, `end` are downloaded. `start` must not be after `end`.

`channel_priority`
:   **List of channel patterns** · default `["HH[ZNE12]", "EH[ZNE12]", "HN[ZNE12]"]`

    Channel groups in order of preference. For each station and day, the first pattern that matches at least `min_channels_per_station` channels is downloaded. See [Channels](../guides/selecting-data.md#channels).

`min_channels_per_station`
:   **Integer** · default `1`

    Minimum number of channels a pattern in `channel_priority` must match to be used. Set it to `3` to require complete three-component recordings.

`min_sampling_rate`
:   **Number (Hz)** · default `100.0`

    Channels sampled below this rate are skipped. `0` disables the check.

`max_sampling_rate`
:   **Number (Hz)** · default `200.0`

    Channels sampled above this rate are skipped. `0` disables the check.

`metadata_path`
:   **Path** · default `"metadata"`

    Directory for StationXML files with full instrument responses, one `<NET>.xml` per network. The files are overwritten on every run.

`writer`
:   **Object** · see [Writer](#writer)

`clients`
:   **List of objects** · default: one GEOFON client · see [Clients](#clients)

## Station selection

`station_selection` picks the stations by one of three methods, chosen with `selection`. The FDSN server does the selecting. Each client queries its own server with the same selection.

=== "By code"

    ```python exec="on" result="json"
    from fdsn_rush.selection import StationSelection

    selection = StationSelection(stations=["GE", "IV.CPOZ"])
    print('"station_selection": ' + selection.model_dump_json(indent=2))
    ```

=== "Bounding box"

    ```python exec="on" result="json"
    from fdsn_rush.selection import GeographicSelection

    selection = GeographicSelection()
    print('"station_selection": ' + selection.model_dump_json(indent=2))
    ```

=== "Radius"

    ```python exec="on" result="json"
    from fdsn_rush.selection import RadiusSelection

    selection = RadiusSelection()
    print('"station_selection": ' + selection.model_dump_json(indent=2))
    ```

The defaults of the bounding box and the radius cover the Campi Flegrei caldera, Italy.

`selection`
:   **`"StationSelection"`, `"GeographicSelection"` or `"RadiusSelection"`** · required

    The selection method. It decides which of the options below apply.

`stations`
:   **List of station codes** · default `["2D.."]` · `StationSelection` only

    Stations to download, as `NET.STA.LOC` codes. Empty parts match anything, and codes may contain the wildcards `*` and `?`. At least one entry is required. See [Selecting stations and channels](../guides/selecting-data.md#stations).

`minlatitude`, `maxlatitude`
:   **Number (degrees)** · default `40.68`, `40.98` · `GeographicSelection` only

    Latitude bounds of the box, inclusive. `minlatitude` must be smaller than `maxlatitude`.

`minlongitude`, `maxlongitude`
:   **Number (degrees)** · default `13.94`, `14.34` · `GeographicSelection` only

    Longitude bounds of the box, inclusive. `minlongitude` must be smaller than `maxlongitude`, so a box cannot cross the antimeridian.

`latitude`, `longitude`
:   **Number (degrees)** · default `40.827`, `14.139` · `RadiusSelection` only

    Centre of the circle.

`minradius`, `maxradius`
:   **Number (degrees)** · default `0.0`, `0.15` · `RadiusSelection` only

    Stations between `minradius` and `maxradius` from the centre are selected. A `minradius` above `0` selects a ring.

`networks`
:   **List of network codes** · default `[]` (all networks) · `GeographicSelection` and `RadiusSelection`

    Limits the area to these networks. Codes may contain the wildcards `*` and `?`.

`exclude_stations`
:   **List of station codes** · default `[]`

    Stations to drop from the selection, as `NET.STA.LOC` codes. They are matched locally, so the wildcards `*`, `?` and `[...]` all work.

`include_restricted`
:   **Boolean** · default `true`

    Include stations with restricted data. Set it to `false` if you have no [EIDA token](../guides/restricted-data.md) for them, so they are not requested at all.

## Writer

Controls how day files are written to the SDS archive.

```json
"writer": {
  "sds_archive": "data",
  "steim_compression": 1,
  "record_length": 4096,
  "min_length_seconds": "PT1M",
  "fix_date_suffixes": false,
  "squirrel_environment": null
}
```

`sds_archive`
:   **Path** · default `"data"`

    Root directory of the SDS archive. It is created if it does not exist. It also holds `remote_errors.log`, as explained in [Missing data](../guides/resuming.md#missing-data-and-remote_errorslog).

`steim_compression`
:   **`1` or `2`** · default `1`

    STEIM compression of the MiniSEED records. STEIM2 produces smaller files for most seismic data.

`record_length`
:   **`512` or `4096`** · default `4096`

    MiniSEED record length in bytes.

`min_length_seconds`
:   **ISO 8601 duration** · default `"PT1M"` (one minute)

    Traces shorter than this are dropped before writing. Examples: `"PT30S"`, `"PT5M"`. Plain numbers are not accepted.

`fix_date_suffixes`
:   **Boolean** · default `false`

    Repairs archives written by older versions that did not zero-pad the day of year, for example `.5` instead of `.005`. The files are renamed in place on startup.

`squirrel_environment`
:   **Path or `null`** · default `null`

    Path to an existing [Pyrocko Squirrel](https://pyrocko.org/docs/current/apps/squirrel/) environment. Each new day file is added to it right after it is written.

## Clients

Each entry in `clients` is one FDSN data centre. All clients download in parallel. See [Servers and performance](../guides/performance.md).

```json
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
]
```

`url`
:   **URL** · default `"https://geofon.gfz.de/"`

    Base URL of the FDSN web service, without the `/fdsnws/...` path.

`timeout`
:   **Number (seconds)** · default `30.0`, minimum `1`

    How long to wait for data before a request is abandoned.

`n_workers`
:   **Integer** · default `8`, range `1`–`64`

    Number of day files downloaded concurrently from this server.

`n_connections`
:   **Integer** · default `24`, range `1`–`128`

    Size of the HTTP connection pool.

`chunk_size`
:   **Byte size** · default `"4.0MiB"`, minimum `"1MiB"`

    Size of the chunks the download stream is read in.

`rate_limit`
:   **Integer (requests/second)** · default `10`, minimum `1`

    Maximum rate of new waveform requests. It is replaced by the server's `X-RateLimit-Limit` header if one is sent.

`eida_key`
:   **Path or `null`** · default `null`

    Path to an EIDA token file for restricted data. `~` is expanded, and the file must exist. See [Restricted data with EIDA tokens](../guides/restricted-data.md).
