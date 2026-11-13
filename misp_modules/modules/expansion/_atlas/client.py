"""Minimal RIPE Atlas API v2 client used by the Atlas MISP modules."""

import time

import requests

API_BASE = "https://atlas.ripe.net/api/v2"

# Upper bound for a single call to RIPE Atlas when MISP gives no time budget.
DEFAULT_TIMEOUT = 30

# MISP closes the connection to the module server once its own timeout
# (Plugin.Enrichment_timeout, 10 seconds by default) runs out, and the module
# answer is then lost. The module has to give up on RIPE Atlas before that,
# keeping this margin to build and send its own answer.
TIMEOUT_MARGIN = 3
MINIMUM_TIMEOUT = 2


class AtlasError(Exception):
    """Raised when the RIPE Atlas API cannot be used as expected."""


class AtlasTimeout(AtlasError):
    """Raised when RIPE Atlas does not answer within the time budget."""


class Deadline:
    """Time budget of one module run, shared by its calls to RIPE Atlas."""

    def __init__(self, misp_timeout=None):
        try:
            budget = float(misp_timeout) - TIMEOUT_MARGIN
        except (TypeError, ValueError):
            budget = DEFAULT_TIMEOUT
        self.budget = max(MINIMUM_TIMEOUT, min(budget, DEFAULT_TIMEOUT))
        self.start = time.monotonic()

    def remaining(self):
        """Seconds left for the next call, never below the minimum."""
        return max(MINIMUM_TIMEOUT, self.budget - (time.monotonic() - self.start))


def _request(method, path, api_key, deadline, **kwargs):
    headers = {
        "Authorization": f"Key {api_key}",
        "Accept": "application/json",
    }
    try:
        response = requests.request(
            method,
            f"{API_BASE}{path}",
            headers=headers,
            timeout=deadline.remaining(),
            **kwargs,
        )
    except requests.Timeout as exc:
        raise AtlasTimeout(
            "RIPE Atlas did not answer in time. Raising Plugin.Enrichment_timeout in the MISP server"
            " settings gives the module more time."
        ) from exc
    except requests.RequestException as exc:
        raise AtlasError(f"RIPE Atlas is not reachable: {exc}") from exc

    if response.status_code in (401, 403):
        raise AtlasError(
            f"RIPE Atlas refused the API key (HTTP {response.status_code}). Check that it can schedule"
            " measurements and read non-public results."
        )
    if not response.ok:
        raise AtlasError(f"RIPE Atlas returned HTTP {response.status_code}: {response.text[:200]}")
    try:
        return response.json()
    except ValueError:
        raise AtlasError(f"RIPE Atlas returned a response that is not JSON (HTTP {response.status_code}).") from None


def create_measurement(payload, api_key, deadline):
    """POST a measurement request and return one measurement id per definition.

    The ids come back in the same order as the definitions of the payload.
    """
    try:
        body = _request("POST", "/measurements/", api_key, deadline, json=payload)
    except AtlasTimeout as exc:
        # The request may have reached RIPE Atlas: the measurement can exist,
        # and be charged, even though its id never came back.
        raise AtlasTimeout(
            f"{exc} The measurement may have been created anyway: check your measurements on RIPE Atlas"
            " before launching it again."
        ) from exc
    ids = body.get("measurements") or []
    if len(ids) != len(payload["definitions"]):
        raise AtlasError(
            f"RIPE Atlas returned {len(ids)} measurement ids for {len(payload['definitions'])} definitions."
        )
    return ids


def get_measurement(msm_id, api_key, deadline):
    """GET the measurement metadata (status, probes_scheduled, ...)."""
    return _request("GET", f"/measurements/{msm_id}/", api_key, deadline)


def get_results(msm_id, api_key, deadline):
    """GET the results of a measurement as a list."""
    body = _request("GET", f"/measurements/{msm_id}/results/", api_key, deadline)
    return body if isinstance(body, list) else body.get("results", [])


def get_probe(probe_id, api_key, deadline):
    """GET a probe, for the country, ASN and coordinates of the map."""
    return _request("GET", f"/probes/{probe_id}/", api_key, deadline)


def results_url(msm_id):
    """Return the public API URL of the results of a measurement."""
    return f"{API_BASE}/measurements/{msm_id}/results/"
