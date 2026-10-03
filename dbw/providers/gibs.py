"""NASA GIBS true-colour snapshot for the report map underlay. Manual option (`--basemap gibs`),
never on the daily default path. No key. Not a numeric provider: nothing here is stored or scored."""
import urllib.error
import urllib.request

from dbw.providers.base import USER_AGENT, FetchError

WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
LAYER = "VIIRS_NOAA20_CorrectedReflectance_TrueColor"
ATTRIBUTION = ("Imagery: we acknowledge the use of imagery provided by services from NASA's Global Imagery "
               "Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS).")


def build_url(bbox, day, width, height, layer=LAYER):
    """WMS 1.3.0 GetMap. `bbox` = (lat_min, lat_max, lon_min, lon_max); with EPSG:4326 the BBOX
    parameter is ordered lat_min,lon_min,lat_max,lon_max."""
    lat0, lat1, lon0, lon1 = bbox
    return (f"{WMS}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={layer}&CRS=EPSG:4326"
            f"&BBOX={lat0},{lon0},{lat1},{lon1}&WIDTH={width}&HEIGHT={height}"
            f"&FORMAT=image/jpeg&TIME={day.isoformat()}")


def http_get_bytes(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code}", reachable=e.code < 500) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FetchError(f"network: {e}") from e


def fetch_image(bbox, day, width=900, height=700, fetch=http_get_bytes):
    """(RGB array | None, reason). reason is '' on success. An undecodable or empty (one flat
    colour, no imagery for that day) image is a failure with a reason, never a blank underlay."""
    try:
        data = fetch(build_url(bbox, day, width, height), timeout=30)
        from io import BytesIO

        from PIL import Image
        import numpy as np
        img = np.asarray(Image.open(BytesIO(data)).convert("RGB"))
    except FetchError as e:
        return None, f"GIBS fetch failed ({e})"
    except Exception as e:  # undecodable body: an HTML/XML error page served with HTTP 200
        return None, f"GIBS image unreadable ({type(e).__name__})"
    if img.std() < 2.0:
        return None, "GIBS image empty (no imagery for this date and area)"
    return img, ""
