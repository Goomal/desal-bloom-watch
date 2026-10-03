"""Shared provider types: BoxStats / NoData, the HTTP helper, and box statistics."""
import math
import statistics
import urllib.error
import urllib.request
from dataclasses import dataclass

USER_AGENT = "desal-bloom-watch/0.1 (+personal open-source project)"


@dataclass(frozen=True)
class BoxStats:
    valid_count: int
    total_count: int
    mean: float
    median: float | None  # None where the statistic is meaningless (wind direction)
    p90: float | None
    min: float | None
    max: float | None
    data_time: str | None = None


@dataclass(frozen=True)
class NoData:
    """Missing data. Never zero-filled. `reachable` is False for network/5xx failures
    (the service could not be talked to), True when the service answered but had nothing."""
    reason: str
    total_count: int | None = None
    reachable: bool = True


class FetchError(Exception):
    def __init__(self, message, reachable=False):
        super().__init__(message)
        self.reachable = reachable


class UpstreamUnreachable(RuntimeError):
    """NOAA could not be reached (5xx, timeout, network) and the command cannot go on. `reason` is the short cause."""
    def __init__(self, message, reason=None):
        super().__init__(message)
        self.reason = reason or message


def http_get(url, timeout=30, retries=1):
    """GET text. One retry on timeouts, network errors and 5xx. 4xx is final."""
    last = None
    for _ in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise FetchError(f"HTTP {e.code}", reachable=True) from e
            last = FetchError(f"HTTP {e.code}", reachable=False)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = FetchError(f"network: {e}", reachable=False)
    raise last


def percentile(sorted_values, q):
    """Linear-interpolation percentile (q in 0..1) of an already sorted, non-empty list."""
    rank = q * (len(sorted_values) - 1)
    lo = math.floor(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (rank - lo) * (sorted_values[hi] - sorted_values[lo])


def summarize(values, total_count, data_time=None):
    """BoxStats from the valid (non-NaN, non-None) values, or NoData if there are none."""
    valid = sorted(v for v in values if v is not None and not math.isnan(v))
    if not valid:
        return NoData(f"all_nan: 0/{total_count} valid", total_count=total_count)
    return BoxStats(len(valid), total_count, statistics.fmean(valid), statistics.median(valid),
                    percentile(valid, 0.9), valid[0], valid[-1], data_time)
