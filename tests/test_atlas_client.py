"""Unit tests for the RIPE Atlas client shared by the Atlas modules."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from misp_modules.modules.expansion._atlas import client

REQUEST = "misp_modules.modules.expansion._atlas.client.requests.request"
PAYLOAD = {"definitions": [{"type": "ping"}]}


def _response(status=200, body=None, text=""):
    response = MagicMock()
    response.status_code = status
    response.ok = status < 400
    response.text = text
    if isinstance(body, Exception):
        response.json.side_effect = body
    else:
        response.json.return_value = body
    return response


def test_deadline_keeps_a_margin_below_the_misp_timeout():
    assert client.Deadline(10).budget == 10 - client.TIMEOUT_MARGIN


def test_deadline_without_misp_timeout_uses_the_default():
    assert client.Deadline(None).budget == client.DEFAULT_TIMEOUT
    assert client.Deadline("not a number").budget == client.DEFAULT_TIMEOUT


def test_deadline_never_goes_below_the_minimum():
    assert client.Deadline(1).budget == client.MINIMUM_TIMEOUT
    assert client.Deadline(1).remaining() >= client.MINIMUM_TIMEOUT


def test_deadline_is_capped_by_the_default():
    assert client.Deadline(600).budget == client.DEFAULT_TIMEOUT


def test_calls_use_the_remaining_time():
    with patch(REQUEST, return_value=_response(body=[])) as request:
        client.get_results(1, "key", client.Deadline(10))
    assert 0 < request.call_args.kwargs["timeout"] <= 10 - client.TIMEOUT_MARGIN


def test_timeout_on_launch_warns_that_the_measurement_may_exist():
    with patch(REQUEST, side_effect=requests.Timeout()):
        with pytest.raises(client.AtlasTimeout) as error:
            client.create_measurement(PAYLOAD, "key", client.Deadline(10))
    assert "may have been created anyway" in str(error.value)


def test_timeout_on_read_suggests_raising_the_misp_timeout():
    with patch(REQUEST, side_effect=requests.Timeout()):
        with pytest.raises(client.AtlasTimeout) as error:
            client.get_results(1, "key", client.Deadline(10))
    assert "Plugin.Enrichment_timeout" in str(error.value)
    assert "may have been created" not in str(error.value)


def test_response_that_is_not_json_is_an_atlas_error():
    with patch(REQUEST, return_value=_response(body=ValueError("no json"), text="<html>")):
        with pytest.raises(client.AtlasError) as error:
            client.get_results(1, "key", client.Deadline(10))
    assert "not JSON" in str(error.value)


def test_refused_key_is_explained():
    with patch(REQUEST, return_value=_response(status=403)):
        with pytest.raises(client.AtlasError) as error:
            client.get_results(1, "key", client.Deadline(10))
    assert "refused the API key" in str(error.value)
