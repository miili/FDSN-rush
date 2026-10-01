---
icon: lucide/folder-tree
---

# Working with the archive

FDSN Rush writes a standard [SDS] (SeisComP Data Structure) archive with StationXML metadata next to it. Every major seismology toolkit reads it directly, with no import step.

## Layout

```text
data/                                 ← writer.sds_archive
├── 2026/                             ← year
│   └── GE/                           ← network
│       └── APE/                      ← station
│           └── HHZ.D/                ← channel, D = data
│               └── GE.APE..HHZ.D.2026.244
└── remote_errors.log                 ← see "Resuming and updating"
metadata/                             ← metadata_path
└── GE.xml                            ← StationXML, one file per network
```

- File names follow `NET.STA.LOC.CHA.D.YEAR.DOY`, with the day of year zero-padded to three digits. An empty location code leaves two consecutive dots, as in `GE.APE..HHZ`.
- Each file holds one channel for one UTC day, cut at midnight and stored as STEIM-compressed MiniSEED records.
- Each `metadata/<NET>.xml` holds the full instrument response of all channels of the selected stations in that network, for the requested time range.

## Reading waveforms

=== "ObsPy"

    ```python
    from obspy import UTCDateTime, read_inventory
    from obspy.clients.filesystem.sds import Client

    client = Client("data")
    inventory = read_inventory("metadata/GE.xml")

    t = UTCDateTime("2026-09-01T12:00:00")
    stream = client.get_waveforms("GE", "APE", "", "HH?", t, t + 600)
    stream.remove_response(inventory=inventory, output="VEL")
    ```

=== "Pyrocko Squirrel"

    ```python
    from pyrocko import util
    from pyrocko.squirrel import Squirrel

    sq = Squirrel()
    sq.add(["data", "metadata"])

    tmin = util.str_to_time("2026-09-01 12:00:00")
    traces = sq.get_waveforms(codes="GE.APE..HH?", tmin=tmin, tmax=tmin + 600)
    ```

=== "SeisComP"

    Point a record stream at the archive:

    ```sh
    scrttv -I sdsarchive:///path/to/data
    ```

## Indexing new files with Squirrel

If you work with [Pyrocko Squirrel], FDSN Rush can register each day file in a Squirrel environment as soon as it is written. Later Squirrel queries then need no re-scan:

```json
"writer": {
  "sds_archive": "data",
  "squirrel_environment": "."
}
```

The path must point to an existing Squirrel environment, which you create with `squirrel init`.

[SDS]: https://www.seiscomp.de/doc/apps/slarchive.html#slarchive-section-sds
[Pyrocko Squirrel]: https://pyrocko.org/docs/current/apps/squirrel/
