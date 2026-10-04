# FDSN web service spec notes

Summary of `fdsnws-station-1.1` and `fdsnws-dataselect-1.1` (both dated 2019-06-27). Fetch the PDFs with `cd reference && just` and `grep` the `.txt` files for the full text.

Both specs defer to "FDSN-WS-Specification-Commonalities" 1.1 for versioning, the calling pattern, error responses and the `version`/`application.wadl` methods. That document is not in `reference/`: fdsn.org does not publish it at a stable PDF URL, and https://github.com/FDSN/WebServiceSpecificationCommonalities only tracks issues. Claims below marked *(unverified)* come from examples or from Commonalities, not from the two specs.

The table column "Support" (required/optional) says which parameters a **server** must implement. It does not mean a client must send them. For example, the dataselect GET example leaves out `location` and `channel`, and `minlatitude` is "required" but has a default.

## Common to both services

- Methods are `query`, `version` and `application.wadl` under `/fdsnws/<service>/1/` (the path is taken from the examples). dataselect adds the optional `queryauth`, which requests HTTP digest auth (RFC 2617).
- GET takes `key=value` pairs, each at most once. A repeated key gives an undefined result.
- POST puts everything in the body: options as `key=value` lines, then one selection per line, `NET STA LOC CHA STARTTIME ENDTIME`. The station changelog (2013-09-18) says servers must support POST in 1.1. The dataselect spec has no such sentence.
- A blank location is sent as `--`, which the server translates to two spaces. In a POST body `--` is mandatory, since spaces separate the fields.
- Multiple codes are comma-separated. Codes may be "wildcards", but the syntax is not defined here (`*`/`?` is *unverified*).
- Times have type `time` and unit UTC. The examples use `2012-01-01T00:00:00` with no zone. ISO 8601 is *unverified*.
- `nodata=204` (the default) or `404` sets the status for "valid request, no data".
- 413: per the changelog, it means the request entity is too large *or* the resulting data set would be. The second meaning extends HTTP.

## dataselect `query`

- Parameters servers must support: `starttime`/`start`, `endtime`/`end`, `network`/`net`, `station`/`sta`, `location`/`loc`, `channel`/`cha`.
- Optional: `quality` (`D`, `R`, `Q`, `M` or `B`, default `B`; handling depends on the data center), `minimumlength` (seconds, default 0.0), `longestonly` (default FALSE), `format` (only `miniseed`, the default), `nodata`.
- The response is a miniSEED stream (`application/vnd.fdsn.mseed`). The data center may remove duplicated data or prune to the exact window, or it may not. The data is expected to be raw. This is why `writer.py` degaps and chops to the day itself.

## station `query`

- Parameters servers must support: the dataselect selection parameters (same aliases), plus `minlatitude`/`minlat`, `maxlatitude`/`maxlat`, `minlongitude`/`minlon`, `maxlongitude`/`maxlon` (inclusive bounding box) and `level`.
- Time filters: `starttime`/`endtime` select epochs that *intersect* the range (changelog 2013-09-18). `startbefore`, `startafter`, `endbefore` and `endafter` filter on the start or end of an epoch. `updatedafter` filters by metadata update time ("highly recommended").
- Radius search (optional): `latitude`/`lat`, `longitude`/`lon`, `minradius` and `maxradius`, all in degrees.
- `level` is `network`, `station`, `channel` or `response`. The default is `station`.
- `format` is `xml` (StationXML, `application/xml`, the default) or `text` (`text/plain`). A text request at `level=response` "should generate an error".
- Other options: `includerestricted` (default TRUE), `includeavailability` (default FALSE), `matchtimeseries` (default FALSE; TRUE limits results to metadata that also has matching time series data), `nodata`.

### Text format

Fields are separated by `|`, and fields cannot contain `|`. Lines starting with `#` are comments; servers use them for the header.

- network: `Network|Description|StartTime|EndTime|TotalStations`
- station: `Network|Station|Latitude|Longitude|Elevation|SiteName|StartTime|EndTime`
- channel: `Network|Station|Location|Channel|Latitude|Longitude|Elevation|Depth|Azimuth|Dip|SensorDescription|Scale|ScaleFrequency|ScaleUnits|SampleRate|StartTime|EndTime` (17 columns; parsed by `models/station.py`)

`Scale` is the total sensitivity (StationXML `InstrumentSensitivity`, SEED stage 0). `ScaleFrequency` is the frequency at which `Scale` is valid, and `ScaleUnits` are the units after `Scale` is applied. `StartTime`/`EndTime` are the operating times of the channel, station or network, depending on the level. `Latitude`/`Longitude` are station or channel coordinates, depending on the level.
