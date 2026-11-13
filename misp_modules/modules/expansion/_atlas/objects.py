"""Build the ripe-atlas-measurement and ripe-atlas-result MISP objects."""

import io
import json
from pathlib import Path

from pymisp import MISPObject

from .client import results_url

OBJECT_NAME = "ripe-atlas-measurement"
RESULT_OBJECT_NAME = "ripe-atlas-result"

# Relationship from a result object to the measurement it was collected from.
# References live on their source object, and the measurement object cannot
# be modified, so the link starts at the result.
RESULT_REFERENCE_RELATIONSHIP = "derived-from"

# The object template is not part of misp-objects yet, so it travels with the
# modules. The layout mirrors the misp-objects repository to keep both copies
# in sync.
MISP_OBJECTS_PATH = str(Path(__file__).parent / "misp-objects" / "objects")

STATUS_TAG = 'ripe-atlas:status="{status}"'

# The measurement id identifies the object, so it carries the status tag.
# The tag cannot be attached to the object itself: MISP objects do not hold
# tags (PyMISP issue 168), only their attributes do.
STATUS_TAG_RELATION = "msm-id"

# A launched measurement is never tagged again: enrichment modules cannot
# modify existing objects, so each collection creates a ripe-atlas-result
# object carrying its own status instead.
LAUNCHED_STATUS = "launched"

# Relationship between the measurement object and the enriched attribute.
REFERENCE_RELATIONSHIP = "describes"


def build_measurement_object(
    msm_id,
    measurement_type,
    target,
    address_family,
    is_public,
    launch_time,
    probes_requested,
):
    """Return the object describing a measurement that was just launched."""
    measurement = MISPObject(OBJECT_NAME, standalone=False, misp_objects_path_custom=MISP_OBJECTS_PATH)

    identifier = measurement.add_attribute(STATUS_TAG_RELATION, value=str(msm_id))
    identifier.add_tag(STATUS_TAG.format(status=LAUNCHED_STATUS))

    measurement.add_attribute("measurement-type", value=measurement_type)
    measurement.add_attribute("target", value=target)
    measurement.add_attribute("af", value=str(address_family))
    measurement.add_attribute("is-public", value=is_public)
    measurement.add_attribute("results-url", value=results_url(msm_id))
    measurement.add_attribute("launch-time", value=launch_time)
    measurement.add_attribute("probes-requested", value=probes_requested)

    return measurement


def build_result_object(msm_id, collection_status, measurement_status, collection_time, summary, raw_results):
    """Return the object holding one collection of the results of a measurement.

    ``summary`` comes from the parser of the measurement type. Its RTT values
    are left out when no probe got a reply, and the probes scheduled when the
    API did not report them.
    """
    result = MISPObject(RESULT_OBJECT_NAME, standalone=False, misp_objects_path_custom=MISP_OBJECTS_PATH)

    identifier = result.add_attribute(STATUS_TAG_RELATION, value=str(msm_id))
    identifier.add_tag(STATUS_TAG.format(status=collection_status))

    result.add_attribute("status", value=measurement_status)
    result.add_attribute("collection-time", value=collection_time)
    if summary.get("probes_scheduled") is not None:
        result.add_attribute("probes-scheduled", value=summary["probes_scheduled"])
    result.add_attribute("results-received", value=summary["results_received"])
    result.add_attribute("probes-reached-target", value=summary["probes_reached_target"])
    for address in summary["observed_ips"]:
        result.add_attribute("observed-ip", value=address)
    for relation in ("rtt-min", "rtt-median", "rtt-max"):
        value = summary.get(relation.replace("-", "_"))
        if value is not None:
            result.add_attribute(relation, value=value)

    raw = json.dumps(raw_results).encode()
    result.add_attribute(
        "raw-results",
        value=f"ripe-atlas-{msm_id}-results.json",
        data=io.BytesIO(raw),
    )

    return result
