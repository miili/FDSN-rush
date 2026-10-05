from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date
from itertools import groupby
from typing import TYPE_CHECKING, Annotated, Literal, Self

import aiohttp
from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    model_validator,
)

from fdsn_rush.client import HEADERS, _post_body, get_error_str
from fdsn_rush.models.station import Stations, parse_stations
from fdsn_rush.utils import NSL, NSLType

if TYPE_CHECKING:
    from fdsn_rush.client import FDSNClient


logger = logging.getLogger(__name__)

# Campi Flegrei caldera, Italy
CAMPI_FLEGREI = (40.827, 14.139)

STATION_OPTIONS = {"level": "channel", "format": "text", "nodata": "404"}
# A selection line with every part as wildcard, see `_post_body`
ALL_STATIONS = NSL("", "", "")


def _check_server_pattern(nsl: NSL) -> NSL:
    """FDSN servers only support the wildcards `*` and `?`, not `[...]`."""
    if any("[" in code for code in nsl):
        raise ValueError(
            f"invalid selection {nsl.pretty}, FDSN servers only support"
            " the wildcards `*` and `?`"
        )
    return nsl


def _check_network(network: str) -> str:
    _check_server_pattern(NSL(network, "", "")._check())
    return network


type NetworkCode = Annotated[str, AfterValidator(_check_network)]
type ServerNSL = Annotated[NSLType, AfterValidator(_check_server_pattern)]


def _network_lines(networks: set[str]) -> list[NSL]:
    """Return one selection line per network, or a single wildcard line."""
    if not networks:
        return [ALL_STATIONS]
    return [NSL(network, "", "") for network in sorted(networks)]


class Selection(BaseModel):
    selection: Literal["Selection"] = "Selection"

    exclude_stations: set[NSLType] = Field(
        default_factory=set,
        description="NSL selections for stations to exclude from download. "
        "Empty codes are wildcards, codes may contain fnmatch patterns",
    )

    include_restricted: bool = Field(
        default=True,
        description="Include restricted stations, which need an EIDA token to download",
    )

    @classmethod
    def _get_subclasses(cls) -> tuple[type[Selection], ...]:
        return tuple(cls.__subclasses__())

    def _options(self, **options: float) -> dict[str, str]:
        """Return the station query options, extended by `options`."""
        query = dict(STATION_OPTIONS)
        if not self.include_restricted:
            query["includerestricted"] = "FALSE"
        query.update({key: str(value) for key, value in options.items()})
        return query

    def _requests(self) -> Iterator[tuple[str, dict[str, str], list[NSL]]]:
        """Yield a label, the options and the selection lines of each request."""
        raise NotImplementedError("This method should be implemented in subclasses.")

    async def get_available_stations(
        self,
        client: FDSNClient,
        starttime: date,
        endtime: date,
    ) -> Stations:
        """Fetch the stations of the selection from the FDSN service.

        Args:
            client: The FDSN client to use for the requests.
            starttime: The start time of the selection.
            endtime: The end time of the selection.

        Returns:
            Stations: The available stations.
        """
        logger.info("Preparing FDSN stations: %s", client.url)
        stations = Stations()

        async with aiohttp.ClientSession(
            base_url=str(client.url),
            timeout=aiohttp.ClientTimeout(total=client.timeout),
            headers=HEADERS,
        ) as session:
            for label, options, nsls in self._requests():
                body = _post_body(options, nsls, starttime, endtime)
                async with session.post(
                    "/fdsnws/station/1/query", data=body
                ) as response:
                    logger.debug("Fetching available stations from %s", response.url)
                    if response.status == 404:
                        logger.warning("No stations found for %s", label)
                        continue
                    try:
                        response.raise_for_status()
                    except aiohttp.ClientResponseError as e:
                        logger.error(
                            "Failed to fetch stations for %s from %s: %d %s (%s)",
                            label,
                            client.url,
                            e.status,
                            get_error_str(e.status),
                            e.message,
                        )
                        continue
                    data = await response.text()

                if response.status == 204 or not data.strip():
                    logger.warning("No stations found for %s", label)
                    continue
                try:
                    selected = parse_stations(data)
                except ValueError:
                    # e.g. only aux channels, which are dropped
                    logger.warning("No usable channels found for %s", label)
                    continue
                stations.extend(selected)
                logger.info("Fetched %d stations for %s", selected.n_stations, label)

        logger.info("Got %d stations from %s", stations.n_stations, client.url)
        for exclude in sorted(self.exclude_stations):
            for station in stations.remove(exclude):
                logger.info("Excluding station %s", station.nsl.pretty)

        return stations


class StationSelection(Selection):
    selection: Literal["StationSelection"] = "StationSelection"

    stations: list[ServerNSL] = Field(
        default=[NSL("2D", "", "")],
        min_length=1,
        description="List of NSL selections for stations to download",
    )

    def _requests(self) -> Iterator[tuple[str, dict[str, str], list[NSL]]]:
        # One request per network, so a missing network does not fail the others
        for network, nsls in groupby(
            sorted(self.stations, key=lambda nsl: nsl.network),
            key=lambda nsl: nsl.network,
        ):
            yield f"network {network or '*'}", self._options(), list(nsls)


class GeographicSelection(Selection):
    selection: Literal["GeographicSelection"] = "GeographicSelection"

    networks: set[NetworkCode] = Field(
        default_factory=set,
        description="Network codes to select within the area, all networks if empty. "
        "Codes may contain fnmatch patterns",
    )

    minlatitude: float = Field(
        default=40.68,
        ge=-90.0,
        le=90.0,
        description="Minimum latitude in degrees",
    )
    maxlatitude: float = Field(
        default=40.98,
        ge=-90.0,
        le=90.0,
        description="Maximum latitude in degrees",
    )
    minlongitude: float = Field(
        default=13.94,
        ge=-180.0,
        le=180.0,
        description="Minimum longitude in degrees",
    )
    maxlongitude: float = Field(
        default=14.34,
        ge=-180.0,
        le=180.0,
        description="Maximum longitude in degrees",
    )

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.minlatitude >= self.maxlatitude:
            raise ValueError("minlatitude must be smaller than maxlatitude")
        if self.minlongitude >= self.maxlongitude:
            raise ValueError("minlongitude must be smaller than maxlongitude")
        return self

    def _requests(self) -> Iterator[tuple[str, dict[str, str], list[NSL]]]:
        options = self._options(
            minlatitude=self.minlatitude,
            maxlatitude=self.maxlatitude,
            minlongitude=self.minlongitude,
            maxlongitude=self.maxlongitude,
        )
        label = (
            f"latitude {self.minlatitude}..{self.maxlatitude}, "
            f"longitude {self.minlongitude}..{self.maxlongitude}"
        )
        yield label, options, _network_lines(self.networks)


class RadiusSelection(Selection):
    selection: Literal["RadiusSelection"] = "RadiusSelection"

    networks: set[NetworkCode] = Field(
        default_factory=set,
        description="Network codes to select within the area, all networks if empty. "
        "Codes may contain fnmatch patterns",
    )

    latitude: float = Field(
        default=CAMPI_FLEGREI[0],
        ge=-90.0,
        le=90.0,
        description="Latitude of the center point in degrees",
    )
    longitude: float = Field(
        default=CAMPI_FLEGREI[1],
        ge=-180.0,
        le=180.0,
        description="Longitude of the center point in degrees",
    )
    minradius: float = Field(
        default=0.0,
        ge=0.0,
        le=180.0,
        description="Minimum radius from the center point in degrees",
    )
    maxradius: float = Field(
        default=0.15,
        gt=0.0,
        le=180.0,
        description="Maximum radius from the center point in degrees",
    )

    @model_validator(mode="after")
    def _check_radius(self) -> Self:
        if self.minradius >= self.maxradius:
            raise ValueError("minradius must be smaller than maxradius")
        return self

    def _requests(self) -> Iterator[tuple[str, dict[str, str], list[NSL]]]:
        options = self._options(
            latitude=self.latitude,
            longitude=self.longitude,
            maxradius=self.maxradius,
        )
        if self.minradius:
            options["minradius"] = str(self.minradius)
        label = (
            f"radius {self.minradius}..{self.maxradius} deg "
            f"around {self.latitude}, {self.longitude}"
        )
        yield label, options, _network_lines(self.networks)


type SelectionType = Annotated[
    StationSelection | GeographicSelection | RadiusSelection,
    Field(discriminator="selection"),
]
