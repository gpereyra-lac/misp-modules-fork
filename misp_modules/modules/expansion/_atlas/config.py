"""Configuration shared by the RIPE Atlas expansion modules.

MISP passes enrichment settings as plain strings taken from the server
settings (``Plugin.Enrichment_<module>_<key>``), so every value is parsed
and validated here instead of in each module.
"""

# Probe selection types accepted by POST /api/v2/measurements/.
# The REST manual lists different sets on different pages: the probes array
# page lists area, country, prefix, asn, probes and msm, while the
# measurement creation page uses region. Both spellings are accepted.
PROBE_SOURCE_TYPES = ("area", "country", "countries", "region", "prefix", "asn", "probes", "msm")

# The administrator has to copy this value, exactly, into the module
# settings before any measurement can be launched.
OPSEC_ACK_VALUE = "I understand that the target will see traffic from RIPE Atlas probes"

DEFAULT_PROBES_REQUESTED = 5
DEFAULT_PROBE_SOURCE_TYPE = "region"
DEFAULT_PROBE_SOURCE_VALUE = "lacnic"
DEFAULT_MAX_CREDITS = 100

_TRUE_VALUES = ("true", "yes", "on", "1")
_FALSE_VALUES = ("false", "no", "off", "0", "")


class AtlasConfigError(Exception):
    """Raised when the module configuration is missing or invalid."""


def _read_string(config, key):
    value = config.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _read_bool(config, key, default):
    value = _read_string(config, key)
    if not value:
        return default
    if value.lower() in _TRUE_VALUES:
        return True
    if value.lower() in _FALSE_VALUES:
        return False
    raise AtlasConfigError(f"Setting '{key}' must be a boolean, got '{value}'.")


def _read_positive_int(config, key, default):
    value = _read_string(config, key)
    if not value:
        return default
    try:
        number = int(value)
    except ValueError:
        raise AtlasConfigError(f"Setting '{key}' must be a whole number, got '{value}'.") from None
    if number < 1:
        raise AtlasConfigError(f"Setting '{key}' must be greater than zero, got {number}.")
    return number


class AtlasConfig:
    """Validated view of the ``moduleconfig`` of a launcher module."""

    def __init__(self, module_config):
        config = module_config or {}

        self.api_key = _read_string(config, "api_key")
        if not self.api_key:
            raise AtlasConfigError("The RIPE Atlas API key is missing.")

        acknowledgement = _read_string(config, "opsec_ack")
        if acknowledgement != OPSEC_ACK_VALUE:
            raise AtlasConfigError(
                "This module launches real measurements: the target sees traffic coming from RIPE Atlas"
                " probes and every result is charged in credits. To acknowledge that, set the 'opsec_ack'"
                f" setting of this module to exactly: {OPSEC_ACK_VALUE}"
            )

        self.probes_requested = _read_positive_int(config, "probes_requested", DEFAULT_PROBES_REQUESTED)
        self.max_credits = _read_positive_int(config, "max_credits", DEFAULT_MAX_CREDITS)

        self.probe_source_type = _read_string(config, "probe_source_type") or DEFAULT_PROBE_SOURCE_TYPE
        if self.probe_source_type not in PROBE_SOURCE_TYPES:
            supported = ", ".join(PROBE_SOURCE_TYPES)
            raise AtlasConfigError(
                f"Setting 'probe_source_type' must be one of: {supported}. Got '{self.probe_source_type}'."
            )

        self.probe_source_value = _read_string(config, "probe_source_value")
        if not self.probe_source_value:
            if self.probe_source_type != DEFAULT_PROBE_SOURCE_TYPE:
                raise AtlasConfigError(
                    f"Setting 'probe_source_value' is required when 'probe_source_type' is '{self.probe_source_type}'."
                )
            self.probe_source_value = DEFAULT_PROBE_SOURCE_VALUE

        # Measurements are private unless the administrator opts in. A
        # measurement can be made public afterwards, never the other way round.
        self.is_public = _read_bool(config, "allow_public", False)

        # For domain|ip attributes, measure the domain by default so that each
        # probe resolves it and regional differences show up.
        self.composite_use_ip = _read_bool(config, "composite_use_ip", False)

    def address_families(self, target_family):
        """Return the address families to measure for a target.

        A target given as an IP address is measured in its own family. A
        target given as a name is measured in both.
        """
        if target_family in (4, 6):
            return [target_family]
        return [4, 6]
