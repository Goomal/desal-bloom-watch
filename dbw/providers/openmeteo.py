"""Open-Meteo provider: daily wind speed/direction and dust/AOD at the box centroid. No key."""
import json
import math
import urllib.parse

from dbw.providers.base import FetchError, NoData, http_get, summarize, BoxStats

ATTRIBUTION = ("Weather and air-quality data by Open-Meteo.com (CC BY 4.0). Free API: "
               "non-commercial use only, under 10,000 calls/day.")

WIND_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# source -> (endpoint, hourly variable, short label)
SOURCES = {
    "openmeteo_wind_speed": (WIND_URL, "wind_speed_10m", "wind"),
    "openmeteo_wind_dir": (WIND_URL, "wind_direction_10m", "wdir"),
    "openmeteo_dust": (AIR_URL, "dust", "dust"),
    "openmeteo_aod": (AIR_URL, "aerosol_optical_depth", "aod"),
}
# wind speed and direction share one request, dust and AOD share the other
_GROUP_VARS = {WIND_URL: "wind_speed_10m,wind_direction_10m",
               AIR_URL: "dust,aerosol_optical_depth"}


def build_url(source, box, day):
    endpoint, _, _ = SOURCES[source]
    lat, lon = box.centroid
    params = {"latitude": round(lat, 4), "longitude": round(lon, 4),
              "hourly": _GROUP_VARS[endpoint], "start_date": day.isoformat(),
              "end_date": day.isoformat(), "timezone": "Asia/Jerusalem"}
    if endpoint == WIND_URL:
        params["wind_speed_unit"] = "ms"
    return endpoint + "?" + urllib.parse.urlencode(params, safe=",")


def circular_mean_deg(degrees):
    s = sum(math.sin(math.radians(d)) for d in degrees)
    c = sum(math.cos(math.radians(d)) for d in degrees)
    return math.degrees(math.atan2(s, c)) % 360


class OpenMeteoProvider:
    def __init__(self, source, http_get=http_get, cache=None):
        if source not in SOURCES:
            raise KeyError(source)
        self.source = source
        self.short = SOURCES[source][2]
        self._get = http_get
        self._cache = cache if cache is not None else {}

    def fetch(self, box, day):
        url = build_url(self.source, box, day)
        try:
            if url not in self._cache:
                self._cache[url] = self._get(url)
            hourly = json.loads(self._cache[url])["hourly"]
        except FetchError as e:
            return NoData(str(e), reachable=e.reachable)
        except (ValueError, KeyError, TypeError) as e:
            return NoData(f"bad json from open-meteo: {e!r}")
        var = SOURCES[self.source][1]
        values = [None if v is None else float(v) for v in hourly.get(var, [])]
        if not values:
            return NoData("empty hourly series", total_count=0)
        data_time = f"{day.isoformat()} (hourly, Asia/Jerusalem)"
        if var != "wind_direction_10m":
            return summarize(values, len(values), data_time)
        valid = [v for v in values if v is not None]
        if not valid:
            return NoData(f"all_nan: 0/{len(values)} valid", total_count=len(values))
        return BoxStats(len(valid), len(values), circular_mean_deg(valid), None, None, None, None,
                        data_time)
