"""Build the payload sent to POST /api/v2/measurements/."""

import ipaddress

MEASUREMENT_TYPES = ("ping", "traceroute", "dns", "sslcert")

# Credits charged per delivered result. A one-off result costs twice as much
# as a result of a recurring measurement, and every measurement created by
# these modules is a one-off.
ONE_OFF_CREDITS_PER_RESULT = {
    "ping": 6,
    "traceroute": 60,
    "dns": 20,
    "sslcert": 20,
}

# The address family is part of the description because a target given as a
# name produces one measurement per family, and both of them share the same
# target. Without it the two objects look identical in the MISP event.
DESCRIPTION_TEMPLATE = "MISP enrichment: {measurement_type} to {target} (IPv{address_family})"


class UnsupportedTargetError(Exception):
    """Raised when RIPE Atlas cannot measure the given target."""


def _check_measurement_type(measurement_type):
    if measurement_type not in MEASUREMENT_TYPES:
        supported = ", ".join(MEASUREMENT_TYPES)
        raise ValueError(f"Unsupported measurement type '{measurement_type}'. Supported types: {supported}.")


def target_address_family(target):
    """Return 4 or 6 if the target is an IP address, None if it is a name.

    Addresses that RIPE Atlas refuses to measure are rejected here, before
    the request is sent.
    """
    try:
        address = ipaddress.ip_address(target)
    except ValueError:
        return None
    if not address.is_global or address.is_multicast:
        raise UnsupportedTargetError(f"RIPE Atlas does not measure non-public addresses such as {target}.")
    return address.version


def estimate_credits(measurement_type, probes_requested, definition_count=1):
    """Return the worst case cost of a one-off measurement, in credits.

    Only probes that deliver a result are charged, so the real cost can be
    lower than this estimate.
    """
    _check_measurement_type(measurement_type)
    return ONE_OFF_CREDITS_PER_RESULT[measurement_type] * probes_requested * definition_count


def build_definition(measurement_type, target, address_family, is_public, resolve_on_probe, extra_fields=None):
    """Return a single entry of the ``definitions`` list."""
    _check_measurement_type(measurement_type)
    definition = {
        "type": measurement_type,
        "af": address_family,
        "target": target,
        "description": DESCRIPTION_TEMPLATE.format(
            measurement_type=measurement_type,
            target=target,
            address_family=address_family,
        ),
        "is_public": is_public,
        "resolve_on_probe": resolve_on_probe,
    }
    if extra_fields:
        definition.update(extra_fields)
    return definition


def build_probe_source(config):
    """Return a single entry of the ``probes`` list."""
    return {
        "requested": config.probes_requested,
        "type": config.probe_source_type,
        "value": config.probe_source_value,
    }


def build_launch_payload(measurement_type, target, target_family, config, extra_fields=None):
    """Return the body of the measurement creation request.

    One definition is built per address family, so a target given as a name
    produces two definitions in a single request, and therefore two
    measurements.
    """
    _check_measurement_type(measurement_type)
    families = config.address_families(target_family)
    resolve_on_probe = target_family is None
    definitions = [
        build_definition(
            measurement_type,
            target,
            family,
            config.is_public,
            resolve_on_probe,
            extra_fields,
        )
        for family in families
    ]
    return {
        "definitions": definitions,
        "probes": [build_probe_source(config)],
        "is_oneoff": True,
    }
