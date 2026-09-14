"""Launch flow shared by the four RIPE Atlas launcher modules."""

import json
from datetime import datetime, timezone

from pymisp import MISPEvent

from .. import check_input_attribute, checking_error, standard_error_message
from .client import AtlasError, create_measurement
from .config import AtlasConfig, AtlasConfigError
from .definitions import UnsupportedTargetError, build_launch_payload, estimate_credits, target_address_family
from .objects import REFERENCE_RELATIONSHIP, build_measurement_object

REQUIRED_ATTRIBUTE_FIELDS = ("type", "uuid", "value")


def target_from_attribute(attribute, config):
    """Return the value to measure, taken from the enriched attribute."""
    if attribute["type"] != "domain|ip":
        return attribute["value"]
    domain, separator, address = attribute["value"].partition("|")
    if not separator:
        raise UnsupportedTargetError(f"Malformed domain|ip attribute: {attribute['value']}.")
    return address if config.composite_use_ip else domain


def launch(request, measurement_type, supported_attributes, extra_fields=None):
    """Create a one-off measurement and return the objects describing it.

    A target given as a name is measured over IPv4 and IPv6, which creates
    two measurements and therefore two objects, one per measurement id.

    The objects hold only what is known locally. The status of a measurement
    and the number of probes it reached are read by the collector module:
    right after the POST the API has not published them yet, and it does so
    at a different moment for each measurement of the same request.
    """
    config = AtlasConfig(request.get("config"))

    attribute = request.get("attribute")
    if not attribute or not check_input_attribute(attribute, requirements=REQUIRED_ATTRIBUTE_FIELDS):
        raise ValueError(f"{standard_error_message}, {checking_error}.")
    if attribute["type"] not in supported_attributes:
        raise ValueError("Unsupported attribute type.")

    target = target_from_attribute(attribute, config)
    target_family = target_address_family(target)
    payload = build_launch_payload(measurement_type, target, target_family, config, extra_fields)

    definition_count = len(payload["definitions"])
    credits_needed = estimate_credits(measurement_type, config.probes_requested, definition_count)
    if credits_needed > config.max_credits:
        raise ValueError(
            f"This measurement would cost up to {credits_needed} credits ({definition_count} measurement(s) of"
            f" {config.probes_requested} probes), above the 'max_credits' setting of {config.max_credits}."
        )

    measurement_ids = create_measurement(payload, config.api_key)
    launch_time = datetime.now(tz=timezone.utc)

    event = MISPEvent()
    event.add_attribute(**attribute)
    for msm_id, definition in zip(measurement_ids, payload["definitions"]):
        measurement = build_measurement_object(
            msm_id,
            measurement_type,
            target,
            definition["af"],
            config.is_public,
            launch_time,
        )
        measurement.add_reference(attribute["uuid"], REFERENCE_RELATIONSHIP)
        event.add_object(measurement)

    # Avoid serialization issue
    event = json.loads(event.to_json())
    return {"results": {"Object": event["Object"], "Attribute": event["Attribute"]}}


def handle_launch(q, measurement_type, supported_attributes, extra_fields=None):
    """Entry point of a launcher module, turning failures into MISP errors."""
    if q is False:
        return False
    try:
        request = json.loads(q)
    except ValueError:
        return {"error": "The request is not valid JSON."}
    try:
        return launch(request, measurement_type, supported_attributes, extra_fields)
    except (AtlasConfigError, AtlasError, UnsupportedTargetError, ValueError) as exc:
        return {"error": str(exc)}
