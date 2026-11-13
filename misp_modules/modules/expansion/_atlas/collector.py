"""Collect flow of the atlas_collect module."""

import json
import statistics
from datetime import datetime, timezone

from pymisp import MISPEvent
from ripe.atlas.sagan import Result

from .client import AtlasError, Deadline, get_measurement, get_results
from .config import AtlasConfigError, read_api_key
from .objects import OBJECT_NAME, RESULT_REFERENCE_RELATIONSHIP, build_result_object

# Statuses after which a measurement delivers no more results.
TERMINAL_STATUS_IDS = (4, 5, 8)  # Stopped, Forced to stop, Archived
FAILED_STATUS_IDS = (6, 7)  # No suitable probes, Failed

SUPPORTED_TYPES = ("ping",)

RTT_DECIMALS = 3


class CollectError(Exception):
    """Raised when the enriched object cannot be collected."""


def collection_status(status_id, results_received, probes_scheduled):
    """Return the tag value of a collection: collected, partial or failed.

    A measurement is complete once its status is terminal or once every
    scheduled probe has delivered a result. The second rule matters because a
    one-off measurement keeps the Ongoing status for minutes after its last
    result has arrived.
    """
    if status_id in FAILED_STATUS_IDS:
        return "failed"
    if status_id in TERMINAL_STATUS_IDS:
        return "collected" if results_received else "failed"
    if probes_scheduled and results_received >= probes_scheduled:
        return "collected"
    return "partial"


def summarize_ping(raw_results):
    """Summarize the results of a ping measurement across all probes."""
    minimums, medians, maximums = [], [], []
    observed_ips = set()
    reached = 0
    for raw in raw_results:
        parsed = Result.get(raw, on_error=Result.ACTION_IGNORE, on_malformation=Result.ACTION_IGNORE)
        if parsed.is_error or parsed.is_malformed:
            continue
        if parsed.destination_address:
            observed_ips.add(parsed.destination_address)
        if parsed.packets_received:
            reached += 1
        if parsed.rtt_min is not None:
            minimums.append(parsed.rtt_min)
            medians.append(parsed.rtt_median)
            maximums.append(parsed.rtt_max)

    summary = {
        "results_received": len(raw_results),
        "probes_reached_target": reached,
        "observed_ips": sorted(observed_ips),
    }
    if minimums:
        summary["rtt_min"] = round(min(minimums), RTT_DECIMALS)
        summary["rtt_median"] = round(statistics.median(medians), RTT_DECIMALS)
        summary["rtt_max"] = round(max(maximums), RTT_DECIMALS)
    return summary


SUMMARIZERS = {"ping": summarize_ping}


def read_measurement_object(request):
    """Return the uuid, measurement id and type of the enriched object."""
    source = request.get("object")
    if not source or source.get("name") != OBJECT_NAME:
        raise CollectError(f"This module runs on a {OBJECT_NAME} object.")
    if not source.get("uuid"):
        raise CollectError("The enriched object has no uuid.")

    values = {attribute.get("object_relation"): attribute.get("value") for attribute in source.get("Attribute", [])}
    msm_id = str(values.get("msm-id") or "").strip()
    if not msm_id.isdigit():
        raise CollectError("The object needs a numeric msm-id.")
    return source["uuid"], msm_id, values.get("measurement-type")


def collect(request):
    """Fetch the results of a measurement and return a new result object.

    The enriched object is never modified: each collection creates its own
    ripe-atlas-result object, referencing the measurement it comes from.
    """
    deadline = Deadline(request.get("timeout"))
    api_key = read_api_key(request.get("config"))
    measurement_uuid, msm_id, object_type = read_measurement_object(request)

    metadata = get_measurement(msm_id, api_key, deadline)
    # RIPE Atlas is the source of truth: an object entered by hand may hold
    # the wrong type, and its results would then go through the wrong parser.
    measurement_type = metadata.get("type") or object_type
    if measurement_type not in SUPPORTED_TYPES:
        raise CollectError(f"Collecting {measurement_type} measurements is not supported yet.")
    # A recurring measurement is never complete and its results grow without
    # bound, so it cannot be collected into a single object.
    if metadata.get("is_oneoff") is False:
        raise CollectError("Collecting recurring measurements is not supported yet, only one-off ones.")

    raw_results = get_results(msm_id, api_key, deadline)
    collection_time = datetime.now(tz=timezone.utc)

    summary = SUMMARIZERS[measurement_type](raw_results)
    summary["probes_scheduled"] = metadata.get("probes_scheduled")

    status = metadata.get("status") or {}
    tag_value = collection_status(status.get("id"), summary["results_received"], summary["probes_scheduled"])

    result = build_result_object(
        msm_id,
        tag_value,
        status.get("name", "Unknown"),
        collection_time,
        summary,
        raw_results,
    )
    result.add_reference(measurement_uuid, RESULT_REFERENCE_RELATIONSHIP)

    event = MISPEvent()
    event.add_object(result)
    # Avoid serialization issue
    event = json.loads(event.to_json())
    return {"results": {"Object": event["Object"]}}


def handle_collect(q):
    """Entry point of atlas_collect, turning failures into MISP errors."""
    if q is False:
        return False
    try:
        request = json.loads(q)
    except ValueError:
        return {"error": "The request is not valid JSON."}
    try:
        return collect(request)
    except (AtlasConfigError, AtlasError, CollectError) as exc:
        return {"error": str(exc)}
