"""atlas_collect — collect the results of a RIPE Atlas measurement."""

from ._atlas.collector import handle_collect

misperrors = {"error": "Error"}

mispattributes = {
    "input": ["ripe-atlas-measurement"],
    "format": "misp_standard",
}

moduleinfo = {
    "version": "0.1",
    "author": "Guillermo Pereyra, LACNIC CSIRT",
    "description": (
        "Collect the results of a RIPE Atlas measurement described by a ripe-atlas-measurement object, either"
        " launched from MISP by the RIPE Atlas launcher modules or created elsewhere. Collecting only reads"
        " from RIPE Atlas and spends no credits."
    ),
    "module-type": ["expansion"],
    "name": "RIPE Atlas Collect",
    "logo": "",
    "requirements": [
        "A RIPE Atlas API key allowed to read non-public results.",
        "ripe.atlas.sagan, to parse the results.",
    ],
    "features": (
        "Reads the msm-id of the enriched object, fetches the measurement status and results, and returns a new"
        " ripe-atlas-result object with the probes scheduled and reached, the IP addresses the probes measured,"
        ' an RTT summary and the raw results as an attachment. Its msm-id is tagged ripe-atlas:status="collected",'
        ' "partial" or "failed", and the object references the measurement with a derived-from relationship.'
        " The enriched object is left untouched, so every collection adds its own result object. Only ping"
        " measurements are supported for now."
    ),
    "references": [
        "https://atlas.ripe.net/docs/apis/rest-api-manual/measurements/",
        "https://ripe-atlas-sagan.readthedocs.io/",
    ],
    "input": "A ripe-atlas-measurement object.",
    "output": "One ripe-atlas-result object referencing the enriched measurement object.",
}

moduleconfig = ["api_key"]


def handler(q=False):
    return handle_collect(q)


def introspection():
    return mispattributes


def version():
    moduleinfo["config"] = moduleconfig
    return moduleinfo
