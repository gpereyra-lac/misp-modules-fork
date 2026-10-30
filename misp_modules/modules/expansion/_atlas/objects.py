"""Build the ripe-atlas-measurement MISP object."""

from pathlib import Path

from pymisp import MISPObject

from .client import results_url

OBJECT_NAME = "ripe-atlas-measurement"

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
