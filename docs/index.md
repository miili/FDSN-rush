---
icon: lucide/house
---

# FDSN Rush

**Fast, reproducible downloads of seismic waveform data from [FDSN] web services into a local [SDS] archive.**

You describe *what* you want in one JSON file: data centres, stations, channels and a time range. FDSN Rush works out what is missing locally and downloads it concurrently. It writes clean day files and saves the matching station metadata next to them. Run the same command again tomorrow and it fetches only the new data.

```sh
uv tool install git+https://github.com/miili/FDSN-rush
fdsn-rush init > config.json
fdsn-rush download config.json
```

<div class="grid cards" markdown>

-   :lucide-rocket: &nbsp; **[Getting started](getting-started.md)**

    ---

    Install FDSN Rush and download your first two days of data in five minutes.

-   :lucide-filter: &nbsp; **[Select stations and channels](guides/selecting-data.md)**

    ---

    Pick networks and stations with wildcards, and set which channels to prefer.

-   :lucide-refresh-cw: &nbsp; **[Keep an archive up to date](guides/resuming.md)**

    ---

    Resume interrupted downloads and add new days automatically.

-   :lucide-settings: &nbsp; **[Configuration reference](reference/configuration.md)**

    ---

    Every option in `config.json`, with defaults.

</div>

## Features

**Concurrent and rate-limited**
:   Each data centre gets a pool of async workers that stream data straight to disk. The request rate stays within the server's limit, and FDSN Rush adopts the limit a server announces in its `X-RateLimit-Limit` header.

**Resumable by design**
:   Day files already in the archive are skipped. Unfinished downloads are cleaned up and repeated on the next run. Day files a server reports as missing (HTTP 404) are logged, so they are not requested again.

**Clean SDS output**
:   One MiniSEED file per channel and UTC day, cut at midnight, with contiguous traces merged and STEIM compression. Very short fragments are dropped. Any tool that reads SDS works with the result: ObsPy, Pyrocko and SeisComP.

**Channel priorities**
:   List the channels you want in order of preference, for example broadband `HH?` before short-period `EH?`. FDSN Rush picks the best channel group each station has, day by day.

**Metadata included**
:   Full-response StationXML is saved for every network, ready for instrument correction.

**Restricted data**
:   Download embargoed data from [EIDA] nodes with your personal EIDA token.

[FDSN]: https://www.fdsn.org/webservices/
[SDS]: https://www.seiscomp.de/doc/apps/slarchive.html#slarchive-section-sds
[EIDA]: https://www.orfeus-eu.org/data/eida/
