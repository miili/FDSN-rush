---
icon: lucide/filter
---

# Selecting stations and channels

Four settings control *what* FDSN Rush downloads:

- `station_selection` and `station_blacklist`: which stations.
- `channel_priority` and `min_channels_per_station`: which channels per station.
- `min_sampling_rate` and `max_sampling_rate`: which sampling rates are acceptable.
- `time_range`: which days.

## Stations

Stations are written as `NET.STA.LOC` codes, following the SEED convention. Parts you leave empty match anything:

| Selection   | Matches                                       |
| ----------- | --------------------------------------------- |
| `"GE"`      | every station of network `GE`                 |
| `"GE.APE"`  | station `APE` of network `GE`, all locations  |
| `"GE.APE.00"` | location `00` of `GE.APE`                   |
| `"GE.A*"`   | all `GE` stations whose code starts with `A`  |
| `"*.STU"`   | station `STU` in any network                  |

Codes can contain shell-style wildcards: `*` (anything), `?` (one character) and `[...]` (one of a set of characters).

```json
"station_selection": ["GE", "2D.ST0?", "Z3.A*"],
"station_blacklist": ["GE.UGM", "2D.ST05"]
```

`station_blacklist` uses the same syntax. A station is downloaded if it matches *any* entry in `station_selection` and *no* entry in `station_blacklist`.

!!! note "How the server is queried"

    FDSN Rush sends one station query per network in your selection. It asks for the channel-level inventory and then applies the selection and blacklist locally. Keep the network code explicit (`"GE.A*"` rather than `"*.A*"`) so the server returns only what you need.

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

Run with `--metadata-only` to fetch the inventory and StationXML only:

```sh
fdsn-rush download config.json --metadata-only
```

Inspect `metadata/<NET>.xml` to check which stations and channels your selection covers before you start a large download.
