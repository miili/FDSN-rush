---
icon: lucide/folder-input
---

# Converting MiniSEED to SDS

Have a directory of MiniSEED files from a field campaign, a datalogger dump or another tool? `fdsn-rush convert` sorts them into an SDS archive with one file per channel and UTC day, the same layout `download` produces.

```sh
fdsn-rush convert raw-data/ sds/
```

## What it does

1. **Scan.** `raw-data/` is searched recursively. Every file that starts with a MiniSEED record is used, regardless of its extension. All other files are skipped.
2. **Split.** Traces that cross midnight (UTC) are split into one piece per day.
3. **Write.** Each piece is appended to its SDS day file under `sds/`, with 4096-byte records and STEIM compression.

Files are processed in parallel. A progress bar shows the scan and the conversion.

!!! note "File names must contain a dot"

    The scan only considers files whose name contains a dot, such as `station.mseed` or `GE.APE..HHZ.D.2026.244`. Files without one, such as `datafile`, are ignored. Rename them before converting.

## Options

`--rename FROM=TO`
:   Rename network, station, location or channel codes. Repeatable. See [Renaming codes](#renaming-codes).

`--steim 1|2`
:   STEIM compression level (default `2`).

`--n-workers N`
:   Number of files converted at the same time (default `64`). Lower it on network file systems.

## Renaming codes

Campaign data is often recorded with a placeholder network, a datalogger serial as station code or non-standard channel names. `--rename FROM=TO` fixes the codes while converting:

```sh
fdsn-rush convert raw-data/ sds/ \
  --rename '1X...=2D...' \
  --rename '...EN1=...ENE' \
  --rename '...EN2=...ENN'
```

Both sides are written as `NET.STA.LOC.CHA`. Missing trailing parts are empty, so `1X=2D` is the same as `1X...=2D...`.

| Part    | In `FROM`                                                    | In `TO`                                 |
| ------- | ------------------------------------------------------------ | --------------------------------------- |
| empty   | matches any code                                             | keeps the code                          |
| `--`    | matches the blank location                                   | sets the blank location                 |
| other   | fnmatch pattern, e.g. `STA0?` or `EH*`                       | the new code, letters and digits only   |

`TO` codes must fit MiniSEED: up to 2 characters for the network and location, 5 for the station and 3 for the channel.

The rules are applied to every trace **in the given order**, and each rule sees the codes left by the rules before it. In the example above, the channel rules match any network, so they also apply after `1X` has become `2D`. A rule that should apply only to the renamed network must use the new code (`2D...EN1=...ENE`).

More examples:

```sh
--rename '.A1B2=.STA01'      # datalogger serial to station code
--rename '..--.=..00.'       # blank location to 00
--rename '..00.=..--.'       # location 00 to blank
```

After the conversion, every rename is logged (`Renamed 1X.STA01..EN1 to 2D.STA01..ENE`). If several source codes end up in the same target, for example two stations renamed to one code, a warning lists them. Their data is appended to the same day files without an overlap check.

## Things to know

!!! warning "Run each conversion once"

    `convert` **appends** to existing day files. If you convert the same input into the same output twice, every trace ends up in the archive twice. To redo a conversion, write to a new, empty directory.

- Merging several input directories into one archive is fine, as long as each input is converted only once.
- If a day file cannot be written, the error is logged and the file path is added to `errors.txt` in the output directory.
- `convert` writes waveforms only. Get matching StationXML with `fdsn-rush metadata` if the stations are available from an FDSN server.
