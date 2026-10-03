"""Provider registry: every source name maps to an object with .source and .fetch(box, day)."""
from dbw.providers import noaa_erddap, openmeteo
from dbw.providers.base import http_get

ATTRIBUTIONS = {"noaa_erddap": noaa_erddap.ATTRIBUTION, "openmeteo": openmeteo.ATTRIBUTION}


def all_source_names():
    return list(noaa_erddap.SOURCES) + list(openmeteo.SOURCES)


def build_providers(names=None, get=http_get):
    """Providers for `names` (default: all). Raises KeyError for an unknown source name."""
    names = list(names) if names else all_source_names()
    cache = {}  # one Open-Meteo request serves both of its variables
    out = {}
    for n in names:
        if n in noaa_erddap.SOURCES:
            out[n] = noaa_erddap.ErddapProvider(n, http_get=get)
        elif n in openmeteo.SOURCES:
            out[n] = openmeteo.OpenMeteoProvider(n, http_get=get, cache=cache)
        else:
            raise KeyError(n)
    return out
