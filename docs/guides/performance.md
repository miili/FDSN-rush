---
icon: lucide/gauge
---

# Servers and performance

Each entry in `clients` is one FDSN data centre with its own connection pool, workers and rate limit. All clients download in parallel.

## Choosing a data centre

Set `url` to the base address of any FDSN web service. FDSN Rush adds the standard `/fdsnws/station/1/` and `/fdsnws/dataselect/1/` paths itself.

```json
"clients": [
  { "url": "https://geofon.gfz.de/" }
]
```

Fields you leave out take their defaults, so a client can be as short as this. Commonly used data centres:

| Data centre         | `url`                               |
| ------------------- | ----------------------------------- |
| GEOFON (GFZ)        | `https://geofon.gfz.de/`            |
| ORFEUS              | `https://orfeus-eu.org/`            |
| INGV                | `https://webservices.ingv.it/`      |
| ETH Zurich          | `https://eida.ethz.ch/`             |
| EarthScope (IRIS)   | `https://service.earthscope.org/`   |

## Several data centres

Add one client per data centre when your networks are archived in different places:

```json
"clients": [
  { "url": "https://geofon.gfz.de/" },
  { "url": "https://webservices.ingv.it/" }
],
"station_selection": ["GE", "IV"]
```

Each client downloads every station *it* offers that matches `station_selection`.

!!! warning "Avoid overlapping data centres"

    If two clients offer the same station, both download it at the same time into the same day file. The result is unreliable. Make sure each network in `station_selection` is served by only one of your clients. If needed, split the download into one configuration file per data centre, writing to the same archive one after another.

## Tuning a client

The defaults are polite to public servers and fast enough for most archives. All options are listed in the [configuration reference](../reference/configuration.md#clients).

`n_workers` (default 8, max 64)
:   Number of day files downloaded at the same time. More workers help with high-latency servers. Ask the data centre before going far beyond the default.

`rate_limit` (default 10)
:   Maximum number of new requests per second. If the server sends an `X-RateLimit-Limit` header, FDSN Rush switches to the server's value and logs a warning.

`n_connections` (default 24, max 128)
:   Size of the HTTP connection pool. Keep it at or above `n_workers`.

`timeout` (default 30 s)
:   How long a request may wait for the next piece of data before it is abandoned. Raise it for slow servers that take long to assemble a day file. Timed-out day files are retried on the next run.

`chunk_size` (default `"4.0MiB"`)
:   How much data is read from the network before it is written to disk. Accepts units such as `"1MiB"` or `"16MiB"` (minimum `1MiB`).

The live panel shows the current download speed per server, which helps you judge the effect of a change.
