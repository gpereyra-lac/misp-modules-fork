"""Minimal RIPE Atlas API v2 client used by the Atlas MISP modules."""

import requests

API_BASE = "https://atlas.ripe.net/api/v2"
TIMEOUT = 30


class AtlasError(Exception):
    """Raised when the RIPE Atlas API cannot be used as expected."""


def _request(method, path, api_key, **kwargs):
    headers = {
        "Authorization": f"Key {api_key}",
        "Accept": "application/json",
    }
    try:
        response = requests.request(method, f"{API_BASE}{path}", headers=headers, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise AtlasError(f"RIPE Atlas is not reachable: {exc}") from exc

    if response.status_code in (401, 403):
        raise AtlasError(
            f"RIPE Atlas refused the API key (HTTP {response.status_code}). Check that it can schedule"
            " measurements and read non-public results."
        )
    if not response.ok:
        raise AtlasError(f"RIPE Atlas returned HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


def create_measurement(payload, api_key):
    """POST a measurement request and return one measurement id per definition.

    The ids come back in the same order as the definitions of the payload.
    """
    body = _request("POST", "/measurements/", api_key, json=payload)
    ids = body.get("measurements") or []
    if len(ids) != len(payload["definitions"]):
        raise AtlasError(
            f"RIPE Atlas returned {len(ids)} measurement ids for {len(payload['definitions'])} definitions."
        )
    return ids


def get_measurement(msm_id, api_key):
    """GET the measurement metadata (status, probes_scheduled, ...)."""
    return _request("GET", f"/measurements/{msm_id}/", api_key)


def get_results(msm_id, api_key):
    """GET the results of a measurement as a list."""
    body = _request("GET", f"/measurements/{msm_id}/results/", api_key)
    return body if isinstance(body, list) else body.get("results", [])


def get_probe(probe_id, api_key):
    """GET a probe, for the country, ASN and coordinates of the map."""
    return _request("GET", f"/probes/{probe_id}/", api_key)


def results_url(msm_id):
    """Return the public API URL of the results of a measurement."""
    return f"{API_BASE}/measurements/{msm_id}/results/"
