---
icon: lucide/key-round
---

# Restricted data with EIDA tokens

Some networks embargo their data for a period, or restrict it to registered users. Data centres in the European Integrated Data Archive ([EIDA]) grant access with a personal **EIDA token**: a PGP-signed file that identifies you to every EIDA node.

## 1. Get a token

Request a token from the EIDA authentication service with your institutional account, and save it, for example as `~/.eidatoken`. The file looks like this:

```text title="~/.eidatoken"
-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA256

{"valid_until": "2026-10-30T12:00:00.000000Z", "cn": "...", "mail": "you@example.org", ...}
-----BEGIN PGP SIGNATURE-----
...
-----END PGP SIGNATURE-----
```

Tokens are valid for a limited time. FDSN Rush checks the expiry date before downloading and stops with a clear error if the token has expired.

## 2. Add it to the client

Set `eida_key` on each client that should use the token:

```json title="config.json" hl_lines="5"
"clients": [
  {
    "url": "https://geofon.gfz.de/",
    "n_workers": 8,
    "eida_key": "~/.eidatoken"
  }
]
```

The path must point to an existing file.

## 3. Download

```sh
fdsn-rush download config.json
```

At startup the token is exchanged for temporary credentials at the node's `/fdsnws/dataselect/1/auth` endpoint. All waveform requests then go to the authenticated `queryauth` endpoint:

```text
INFO     Preparing PGP authentication using key: /home/you/.eidatoken
INFO     Using EIDA token for you@example.org valid until 2026-10-30 12:00:00+00:00
```

!!! warning "Access is granted per network"

    A token proves who you are. It does not grant access to every network. If you are not authorised for a network, its requests fail with *401 Unauthorized* or *403 Forbidden*. Ask the network operator for access.

## Several EIDA nodes

The token is valid at every EIDA node, but each client authenticates separately. Set `eida_key` on every client in `clients` that serves restricted data. See [Servers and performance](performance.md) for configuring several data centres.

[EIDA]: https://www.orfeus-eu.org/data/eida/
