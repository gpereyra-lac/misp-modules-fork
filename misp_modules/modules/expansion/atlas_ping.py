"""atlas_ping — launch a one-off RIPE Atlas ping measurement."""

from ._atlas.launcher import handle_launch

MEASUREMENT_TYPE = "ping"

misperrors = {"error": "Error"}

mispattributes = {
    "input": ["ip-src", "ip-dst", "hostname", "domain", "domain|ip"],
    "format": "misp_standard",
}

moduleinfo = {
    "version": "0.1",
    "author": "Guillermo Pereyra, LACNIC CSIRT",
    "description": (
        "Launch a one-off ping measurement on RIPE Atlas towards an IP address or a name, to see how the"
        " target answers from several vantage points. Running this module sends real traffic from RIPE Atlas"
        " probes to the target and spends credits."
    ),
    "module-type": ["expansion"],
    "name": "RIPE Atlas Ping",
    "logo": "",
    "requirements": [
        "A RIPE Atlas API key allowed to schedule measurements and to read non-public results.",
        "RIPE Atlas credits: a one-off ping result costs 6 credits per probe.",
    ],
    "features": (
        "Creates a one-off ping measurement and returns a ripe-atlas-measurement object holding the"
        ' measurement id, tagged ripe-atlas:status="pending". The results are collected afterwards by the'
        " atlas_collect module. A target given as a name is resolved by each probe and measured over both"
        " IPv4 and IPv6, which creates two measurements and therefore two objects. Measurements are private"
        " unless the allow_public setting says otherwise."
    ),
    "references": [
        "https://atlas.ripe.net/docs/apis/rest-api-manual/measurements/creating-measurements/",
        "https://atlas.ripe.net/docs/apis/rest-api-manual/credits/",
    ],
    "input": "An IP address, a hostname, a domain, or a domain|ip attribute.",
    "output": "One ripe-atlas-measurement object per measurement created, referencing the input attribute.",
}

moduleconfig = [
    "api_key",
    "opsec_ack",
    "probes_requested",
    "probe_source_type",
    "probe_source_value",
    "max_credits",
    "allow_public",
    "composite_use_ip",
]


def handler(q=False):
    return handle_launch(q, MEASUREMENT_TYPE, mispattributes["input"])


def introspection():
    return mispattributes


def version():
    moduleinfo["config"] = moduleconfig
    return moduleinfo
