"""Unit tests for atlas_collect (mocked RIPE Atlas API, no network)."""

import base64
import json
from pathlib import Path
from unittest.mock import patch

from misp_modules.modules.expansion import atlas_collect

COLLECTOR = "misp_modules.modules.expansion._atlas.collector"

MEASUREMENT_UUID = "8c5e3a5e-0b4f-4f6f-9d1a-0d3c2b1a9e01"
MSM_ID = "236530947"

# Synthetic ping results in the RIPE Atlas format: three probes answered and
# one got no reply.
RESULTS = json.loads((Path(__file__).parent / "results_atlas_collect_ping.json").read_text())


def _metadata(status_id=4, status_name="Stopped", probes_scheduled=4, measurement_type="ping"):
    return {
        "id": int(MSM_ID),
        "type": measurement_type,
        "status": {"id": status_id, "name": status_name},
        "probes_scheduled": probes_scheduled,
    }


def _object(**values):
    attributes = {"msm-id": MSM_ID, "measurement-type": "ping"}
    attributes.update(values)
    return {
        "name": "ripe-atlas-measurement",
        "uuid": MEASUREMENT_UUID,
        "Attribute": [
            {"object_relation": relation, "value": value} for relation, value in attributes.items() if value is not None
        ],
    }


def _query(source=None, **config_overrides):
    config = {"api_key": "test-key"}
    config.update(config_overrides)
    return json.dumps(
        {
            "module": "atlas_collect",
            "object": _object() if source is None else source,
            "config": config,
        }
    )


def _run(query, metadata=None, results=None):
    """Run the handler with the API mocked."""
    metadata = _metadata() if metadata is None else metadata
    results = RESULTS if results is None else results
    with (
        patch(f"{COLLECTOR}.get_measurement", return_value=metadata) as get_measurement,
        patch(f"{COLLECTOR}.get_results", return_value=results) as get_results,
    ):
        response = atlas_collect.handler(query)
    return response, get_measurement, get_results


def _result_object(response):
    objects = response["results"]["Object"]
    assert len(objects) == 1
    return objects[0]


def _relations(obj):
    relations = {}
    for attribute in obj["Attribute"]:
        relations.setdefault(attribute["object_relation"], []).append(attribute)
    return relations


def _value(obj, relation):
    return _relations(obj)[relation][0]["value"]


def _tag(obj):
    return [tag["name"] for tag in _relations(obj)["msm-id"][0]["Tag"]]


def test_returns_a_new_result_object():
    response, _, _ = _run(_query())
    result = _result_object(response)
    assert result["name"] == "ripe-atlas-result"
    assert _value(result, "msm-id") == MSM_ID
    assert "collection-time" in _relations(result)


def test_result_references_the_measurement():
    result = _result_object(_run(_query())[0])
    references = result["ObjectReference"]
    assert len(references) == 1
    assert references[0]["referenced_uuid"] == MEASUREMENT_UUID
    assert references[0]["relationship_type"] == "derived-from"


def test_enriched_object_is_not_returned():
    """MISP cannot update an existing object, so it must not be echoed."""
    response, _, _ = _run(_query())
    assert all(obj["name"] != "ripe-atlas-measurement" for obj in response["results"]["Object"])
    assert "Attribute" not in response["results"]


def test_ping_summary():
    result = _result_object(_run(_query())[0])
    assert int(_value(result, "results-received")) == 4
    assert int(_value(result, "probes-scheduled")) == 4
    # The fourth probe got no reply.
    assert int(_value(result, "probes-reached-target")) == 3
    assert float(_value(result, "rtt-min")) == 2.393
    # Median of the per-probe medians 2.402, 47.076 and 139.2.
    assert float(_value(result, "rtt-median")) == 47.076
    assert float(_value(result, "rtt-max")) == 140.1


def test_observed_ips_are_distinct():
    result = _result_object(_run(_query())[0])
    assert [attribute["value"] for attribute in _relations(result)["observed-ip"]] == ["200.3.14.10"]


def test_observed_ips_are_not_ids_indicators():
    """They may belong to shared infrastructure such as a CDN."""
    result = _result_object(_run(_query())[0])
    assert all(attribute["to_ids"] is False for attribute in _relations(result)["observed-ip"])


def test_real_ipv6_results_from_a_cdn():
    """Results of msm 236556669: ping to www.apple.com from probes worldwide."""
    real = json.loads((Path(__file__).parent / "results_236556669.json").read_text())
    metadata = _metadata(status_id=2, status_name="Ongoing", probes_scheduled=10)
    result = _result_object(_run(_query(), metadata=metadata, results=real)[0])
    assert _tag(result) == ['ripe-atlas:status="collected"']
    assert int(_value(result, "results-received")) == 10
    assert int(_value(result, "probes-reached-target")) == 9
    assert len(_relations(result)["observed-ip"]) == 9
    assert float(_value(result, "rtt-min")) == 1.097
    assert float(_value(result, "rtt-median")) == 14.707
    assert float(_value(result, "rtt-max")) == 248.787


def test_raw_results_are_attached():
    result = _result_object(_run(_query())[0])
    attachment = _relations(result)["raw-results"][0]
    assert attachment["value"] == f"ripe-atlas-{MSM_ID}-results.json"
    assert json.loads(base64.b64decode(attachment["data"])) == RESULTS


def test_measurement_status_is_recorded():
    result = _result_object(_run(_query())[0])
    assert _value(result, "status") == "Stopped"


def test_terminal_status_is_collected():
    result = _result_object(_run(_query())[0])
    assert _tag(result) == ['ripe-atlas:status="collected"']


def test_all_probes_delivered_is_collected_while_ongoing():
    metadata = _metadata(status_id=2, status_name="Ongoing", probes_scheduled=4)
    result = _result_object(_run(_query(), metadata=metadata)[0])
    assert _tag(result) == ['ripe-atlas:status="collected"']


def test_missing_results_while_ongoing_is_partial():
    metadata = _metadata(status_id=2, status_name="Ongoing", probes_scheduled=10)
    result = _result_object(_run(_query(), metadata=metadata)[0])
    assert _tag(result) == ['ripe-atlas:status="partial"']


def test_failed_status_is_failed():
    metadata = _metadata(status_id=7, status_name="Failed")
    result = _result_object(_run(_query(), metadata=metadata, results=[])[0])
    assert _tag(result) == ['ripe-atlas:status="failed"']


def test_stopped_without_results_is_failed():
    result = _result_object(_run(_query(), results=[])[0])
    assert _tag(result) == ['ripe-atlas:status="failed"']
    assert int(_value(result, "results-received")) == 0
    assert "rtt-min" not in _relations(result)


def test_type_is_read_from_the_api_when_missing():
    """An object created by hand may only hold the msm-id."""
    source = _object(**{"measurement-type": None})
    response, _, get_results = _run(_query(source))
    assert _result_object(response)["name"] == "ripe-atlas-result"
    get_results.assert_called_once()


def test_unsupported_type_collects_nothing():
    metadata = _metadata(measurement_type="traceroute")
    response, _, get_results = _run(_query(), metadata=metadata)
    assert "not supported yet" in response["error"]
    get_results.assert_not_called()


def test_type_reported_by_the_api_wins_over_the_object():
    """A hand-made object may say ping for a dns measurement."""
    metadata = _metadata(measurement_type="dns")
    response, _, get_results = _run(_query(), metadata=metadata)
    assert "Collecting dns measurements is not supported yet" in response["error"]
    get_results.assert_not_called()


def test_recurring_measurements_are_rejected():
    metadata = _metadata(status_id=2, status_name="Ongoing")
    metadata["is_oneoff"] = False
    response, _, get_results = _run(_query(), metadata=metadata)
    assert "recurring" in response["error"]
    get_results.assert_not_called()


def test_missing_api_key_collects_nothing():
    response, get_measurement, _ = _run(_query(api_key=""))
    assert "API key" in response["error"]
    get_measurement.assert_not_called()


def test_other_objects_are_rejected():
    source = {"name": "domain-ip", "uuid": MEASUREMENT_UUID, "Attribute": []}
    response, get_measurement, _ = _run(_query(source))
    assert "ripe-atlas-measurement" in response["error"]
    get_measurement.assert_not_called()


def test_object_without_measurement_id_is_rejected():
    source = _object(**{"msm-id": None})
    response, get_measurement, _ = _run(_query(source))
    assert "msm-id" in response["error"]
    get_measurement.assert_not_called()


def test_api_errors_reach_the_analyst():
    from misp_modules.modules.expansion._atlas.client import AtlasError

    with patch(f"{COLLECTOR}.get_measurement", side_effect=AtlasError("RIPE Atlas refused the API key (HTTP 403).")):
        response = atlas_collect.handler(_query())
    assert response["error"].startswith("RIPE Atlas refused the API key")


def test_introspection_and_version():
    assert atlas_collect.introspection() == atlas_collect.mispattributes
    moduleinfo = atlas_collect.version()
    assert moduleinfo["config"] == atlas_collect.moduleconfig
    assert moduleinfo["module-type"] == ["expansion"]
