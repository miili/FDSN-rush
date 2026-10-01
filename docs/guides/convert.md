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

`--network CODE`
:   Overwrite the network code of all traces. This is useful for campaign data recorded with a placeholder network:

    ```sh
    fdsn-rush convert raw-data/ sds/ --network 2D
    ```

`--steim 1|2`
:   STEIM compression level (default `2`).

`--n-workers N`
:   Number of files converted at the same time (default `64`). Lower it on network file systems.

## Things to know

!!! warning "Run each conversion once"

    `convert` **appends** to existing day files. If you convert the same input into the same output twice, every trace ends up in the archive twice. To redo a conversion, write to a new, empty directory.

- Merging several input directories into one archive is fine, as long as each input is converted only once.
- If a day file cannot be written, the error is logged and the file path is added to `errors.txt` in the output directory.
- `convert` writes waveforms only. Get matching StationXML with `fdsn-rush download --metadata-only` if the stations are available from an FDSN server.
