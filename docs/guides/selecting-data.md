---
icon: lucide/filter
---

# Selecting stations and channels

Four settings control *what* FDSN Rush downloads:

- `station_selection`: which stations, by code, in a bounding box or within a radius.
- `channel_priority` and `min_channels_per_station`: which channels per station.
- `min_sampling_rate` and `max_sampling_rate`: which sampling rates are acceptable.
- `time_range`: which days.

## Stations

`station_selection` chooses the stations in one of three ways, set by `selection`. The FDSN server applies the selection and returns the matching channel inventory. All options are listed in the [configuration reference](../reference/configuration.md#station-selection).

### By code

```json
"station_selection": {
  "selection": "StationSelection",
  "stations": ["GE", "2D.ST0?", "Z3.A*"]
}
```

Stations are written as `NET.STA.LOC` codes, following the SEED convention. Parts you leave empty match anything:

| Selection   | Matches                                       |
| ----------- | --------------------------------------------- |
| `"GE"`      | every station of network `GE`                 |
| `"GE.APE"`  | station `APE` of network `GE`, all locations  |
| `"GE.APE.00"` | location `00` of `GE.APE`                   |
| `"GE.A*"`   | all `GE` stations whose code starts with `A`  |
| `"*.STU"`   | station `STU` in any network                  |

Codes can contain the wildcards `*` (anything) and `?` (one character). FDSN servers reject `[...]`, so it is refused when the configuration is loaded.

FDSN Rush sends one station query per network. A network that the server does not know is logged as a warning and does not affect the others.

### In a bounding box

```json
"station_selection": {
  "selection": "GeographicSelection",
  "minlatitude": 40.68,
  "maxlatitude": 40.98,
  "minlongitude": 13.94,
  "maxlongitude": 14.34,
  "networks": ["IV"]
}
```

Selects every station inside the box, bounds included. `networks` limits the box to some networks and may contain `*` and `?`. Leave it empty (the default) to get all networks.

### Within a radius

```json
"station_selection": {
  "selection": "RadiusSelection",
  "latitude": 40.827,
  "longitude": 14.139,
  "maxradius": 0.15
}
```

Selects every station within `maxradius` degrees of the centre. Set `minradius` to get a ring instead of a disc. `networks` works as for the bounding box.

The defaults of both area selections cover the Campi Flegrei caldera, which INGV (`https://webservices.ingv.it/`) serves.

### Excluding stations

Every selection takes `exclude_stations`, in the same `NET.STA.LOC` syntax:

```json
"station_selection": {
  "selection": "RadiusSelection",
  "exclude_stations": ["IV.CPOZ", "IV.CS*"]
}
```

Excluded stations are removed after the server has answered, so `[...]` works here too (`"IV.CA[AB]*"`).

### Restricted stations

Some stations are only available with an [EIDA token](restricted-data.md). Without one, set `"include_restricted": false` so that they are not selected at all instead of failing at download time.

## Channels

Stations often record several channel groups, for example a broadband seismometer on `HH?` and a strong-motion sensor on `HN?`. `channel_priority` is an ordered list of channel patterns. **For each station and each day**, FDSN Rush takes the first pattern that matches at least `min_channels_per_station` channels and ignores the rest:

```json
"channel_priority": ["HH[ZNE12]", "EH[ZNE12]", "HN[ZNE12]"],
"min_channels_per_station": 3
```

With this configuration:

- A station with `HHZ`, `HHN` and `HHE` gets its three `HH` channels.
- A station with only `EHZ`, `EHN` and `EHE` gets the `EH` channels.
- A station with `HHZ` alone and no complete group is skipped. With `min_channels_per_station` set to `1`, it would get `HHZ`.

Because the decision is made per day, a station that was upgraded from short-period to broadband mid-campaign gets `EH` before the upgrade and `HH` after it.

Patterns use the same wildcard syntax as stations. `"HH?"` matches all `HH` channels, `"HH[ZNE]"` only the standard orientations, and `"*Z"` every vertical component.

!!! tip "State-of-health channels are ignored"

    Auxiliary channels, such as voltages, temperatures, mass positions and `LDO` pressure, are filtered from the inventory. They are never downloaded, even if a pattern would match them.

## Sampling rates

Channels outside `[min_sampling_rate, max_sampling_rate]` (in Hz) are skipped. A warning names each skipped channel. The defaults (100–200 Hz) suit local and regional seismology. To download long-period `LH?` channels at 1 Hz:

```json
"channel_priority": ["LH[ZNE]"],
"min_sampling_rate": 1.0,
"max_sampling_rate": 1.0
```

Set either value to `0` to disable that bound.

## Time range

`time_range` is a pair `[start, end]` of UTC dates. FDSN Rush downloads whole days from `start` up to, but **not including**, `end`.

| `time_range`                    | Days downloaded                        |
| ------------------------------- | -------------------------------------- |
| `["2026-09-01", "2026-09-03"]`  | September 1 and 2                      |
| `["2026-01-01", "today"]`       | January 1 up to and including yesterday |
| `["yesterday", "today"]`        | yesterday only                         |

Downloads always cover whole UTC days. A channel is only requested on days that fall within its epoch in the station inventory.

## Checking a selection without downloading waveforms

Run `metadata` to fetch the inventory and StationXML only:

```sh
fdsn-rush metadata config.json
```

Open `metadata/<NET>.xml` to see which stations and channels your selection covers before you start a large download. To catch typos in the configuration file itself, run `fdsn-rush check config.json`.
