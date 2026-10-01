# FDSN Rush

*Fast and modern FDSN Download*

[![PyPI](https://img.shields.io/pypi/v/fdsn-rush)](https://pypi.org/project/fdsn-rush/)
[![Tests](https://github.com/miili/FDSN-rush/actions/workflows/tests.yaml/badge.svg)](https://github.com/miili/FDSN-rush/actions/workflows/tests.yaml)
[![Documentation](https://github.com/miili/FDSN-rush/actions/workflows/docs.yaml/badge.svg)](https://miili.github.io/FDSN-rush/)
[![Pre-commit](https://github.com/miili/FDSN-rush/actions/workflows/pre-commit.yaml/badge.svg)](https://github.com/miili/FDSN-rush/actions/workflows/pre-commit.yaml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

*FDSN Rush* downloads seismic waveform data from [FDSN](https://www.fdsn.org/webservices/) servers into a local [SDS](https://www.seiscomp.de/doc/apps/slarchive.html#slarchive-section-sds) archive in a fast, reproducible and reliable way. It also saves the matching StationXML metadata.

- Concurrent, rate-limited downloads from one or more data centres.
- Resumable: reruns only fetch what is missing.
- Channel priorities, wildcard station selection and sampling-rate filters.
- Restricted data with EIDA tokens.

**Documentation: <https://miili.github.io/FDSN-rush/>**

## Installation

Requires Python 3.11 or newer.

```sh
uv tool install fdsn-rush
# or
pip install fdsn-rush
```

## Quick start

```sh
fdsn-rush init > config.json      # write the default configuration
# edit station_selection and time_range in config.json
fdsn-rush download config.json    # download into data/ and metadata/
```

Convert existing MiniSEED files into an SDS archive:

```sh
fdsn-rush convert in-folder/ out-sds-folder/
```

See the [Getting started guide](https://miili.github.io/FDSN-rush/getting-started/) for a full walkthrough and the [configuration reference](https://miili.github.io/FDSN-rush/reference/configuration/) for all options.
