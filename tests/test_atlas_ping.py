"""Unit tests for atlas_ping (mocked RIPE Atlas API, no network)."""

import json
from unittest.mock import patch

from misp_modules.modules.expansion import atlas_ping
from misp_modules.modules.expansion._atlas.config import OPSEC_ACK_VALUE

LAUNCHER = "misp_modules.modules.expansion._atlas.launcher.create_measurement"

ATTRIBUTE_UUID = "5b582d80-7a7e-4b6a-9f22-77656e72bb3b"

BASE_CONFIG = {
    "api_key": "test-key",
    "opsec_ack": OPSEC_ACK_VALUE,
    "probes_requested": "5",
    "probe_source_type": "region",
    "probe_source_value": "lacnic",
    "max_credits": "100",
}


def _query(attribute_type, value, **config_overrides):
    config = dict(BASE_CONFIG)
    config.update(config_overrides)
    return json.dumps(
        {
            "module": "atlas_ping",
            "attribute": {"type": attribute_type, "value": value, "uuid": ATTRIBUTE_UUID},
            "config": config,
        }
    )


def _run(query, measurement_ids=(1,)):
    """Run the handler with the API mocked, returning the result and the payload."""
    captured = {}

    def fake_create(payload, api_key):
        captured["payload"] = payload
        captured["api_key"] = api_key
        return list(measurement_ids)[: len(payload["definitions"])]

    with patch(LAUNCHER, side_effect=fake_create) as create:
        result = atlas_ping.handler(query)
    return result, captured, create


def _relations(obj):
    return {attribute["object_relation"]: attribute for attribute in obj["Attribute"]}


def test_ip_target_builds_one_definition():
    result, captured, _ = _run(_query("ip-dst", "45.33.32.156"))
    definitions = captured["payload"]["definitions"]
    assert len(definitions) == 1
    assert definitions[0]["type"] == "ping"
    assert definitions[0]["af"] == 4
    assert definitions[0]["target"] == "45.33.32.156"
    # An address needs no resolution, so the probes must not resolve it.
    assert definitions[0]["resolve_on_probe"] is False
    assert captured["payload"]["is_oneoff"] is True
    assert "error" not in result


def test_ipv6_target_keeps_its_own_family():
    _, captured, _ = _run(_query("ip-dst", "2001:13c7:7002:4000::10"))
    assert [definition["af"] for definition in captured["payload"]["definitions"]] == [6]


def test_named_target_builds_one_definition_per_family():
    _, captured, _ = _run(_query("domain", "example.org"), measurement_ids=(101, 102))
    definitions = captured["payload"]["definitions"]
    assert [definition["af"] for definition in definitions] == [4, 6]
    assert all(definition["resolve_on_probe"] is True for definition in definitions)
    # The two measurements share a target, so the family tells them apart.
    assert definitions[0]["description"].endswith("(IPv4)")
    assert definitions[1]["description"].endswith("(IPv6)")


def test_named_target_returns_one_object_per_measurement():
    result, _, _ = _run(_query("domain", "example.org"), measurement_ids=(101, 102))
    objects = result["results"]["Object"]
    assert len(objects) == 2
    assert [_relations(obj)["msm-id"]["value"] for obj in objects] == ["101", "102"]
    assert [_relations(obj)["af"]["value"] for obj in objects] == ["4", "6"]
    for obj in objects:
        assert obj["name"] == "ripe-atlas-measurement"
        assert obj["ObjectReference"][0]["referenced_uuid"] == ATTRIBUTE_UUID


def test_measurement_id_carries_the_pending_tag():
    result, _, _ = _run(_query("ip-dst", "45.33.32.156"))
    identifier = _relations(result["results"]["Object"][0])["msm-id"]
    assert [tag["name"] for tag in identifier["Tag"]] == ['ripe-atlas:status="pending"']


def test_object_holds_only_locally_known_fields():
    """The status and the scheduled probes are left to the collector module."""
    result, _, _ = _run(_query("ip-dst", "45.33.32.156"))
    relations = _relations(result["results"]["Object"][0])
    assert set(relations) == {
        "msm-id",
        "measurement-type",
        "target",
        "af",
        "is-public",
        "results-url",
        "launch-time",
    }


def test_measurements_are_private_by_default():
    result, captured, _ = _run(_query("ip-dst", "45.33.32.156"))
    assert captured["payload"]["definitions"][0]["is_public"] is False
    assert _relations(result["results"]["Object"][0])["is-public"]["value"] is False


def test_public_measurements_need_an_explicit_setting():
    _, captured, _ = _run(_query("ip-dst", "45.33.32.156", allow_public="true"))
    assert captured["payload"]["definitions"][0]["is_public"] is True


def test_probe_source_comes_from_the_configuration():
    _, captured, _ = _run(_query("ip-dst", "45.33.32.156", probe_source_type="area", probe_source_value="WW"))
    assert captured["payload"]["probes"] == [{"requested": 5, "type": "area", "value": "WW"}]


def test_composite_attribute_measures_the_domain():
    _, captured, _ = _run(_query("domain|ip", "example.org|45.33.32.156"), measurement_ids=(101, 102))
    assert captured["payload"]["definitions"][0]["target"] == "example.org"


def test_composite_attribute_can_measure_the_address():
    _, captured, _ = _run(_query("domain|ip", "example.org|45.33.32.156", composite_use_ip="true"))
    definitions = captured["payload"]["definitions"]
    assert len(definitions) == 1
    assert definitions[0]["target"] == "45.33.32.156"


def test_missing_acknowledgement_launches_nothing():
    result, _, create = _run(_query("ip-dst", "45.33.32.156", opsec_ack=""))
    assert "opsec_ack" in result["error"]
    assert OPSEC_ACK_VALUE in result["error"]
    create.assert_not_called()


def test_missing_api_key_launches_nothing():
    result, _, create = _run(_query("ip-dst", "45.33.32.156", api_key=""))
    assert "API key" in result["error"]
    create.assert_not_called()


def test_non_public_address_launches_nothing():
    result, _, create = _run(_query("ip-dst", "192.168.1.1"))
    assert "non-public" in result["error"]
    create.assert_not_called()


def test_cost_above_the_limit_launches_nothing():
    result, _, create = _run(_query("ip-dst", "45.33.32.156", max_credits="10"))
    # A one-off ping result costs 6 credits per probe.
    assert "30 credits" in result["error"]
    create.assert_not_called()


def test_named_target_costs_twice_as_much():
    result, _, create = _run(_query("domain", "example.org", max_credits="50"))
    assert "60 credits" in result["error"]
    create.assert_not_called()


def test_unknown_probe_source_type_launches_nothing():
    result, _, create = _run(_query("ip-dst", "45.33.32.156", probe_source_type="planet"))
    assert "probe_source_type" in result["error"]
    create.assert_not_called()


def test_unsupported_attribute_type_launches_nothing():
    result, _, create = _run(_query("md5", "d41d8cd98f00b204e9800998ecf8427e"))
    assert result["error"] == "Unsupported attribute type."
    create.assert_not_called()


def test_attribute_without_uuid_launches_nothing():
    query = json.dumps(
        {
            "module": "atlas_ping",
            "attribute": {"type": "ip-dst", "value": "45.33.32.156"},
            "config": dict(BASE_CONFIG),
        }
    )
    result, _, create = _run(query)
    assert "error" in result
    create.assert_not_called()


def test_introspection_and_version():
    assert atlas_ping.introspection() == atlas_ping.mispattributes
    moduleinfo = atlas_ping.version()
    assert moduleinfo["config"] == atlas_ping.moduleconfig
    # Hovering must never launch a measurement.
    assert moduleinfo["module-type"] == ["expansion"]
