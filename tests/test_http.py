"""Tests for _HTTPClient internals: init, helpers, response handling, retries."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from mudrex._exceptions import MudrexAPIError, MudrexRequestError
from mudrex._http import _HTTPClient
from mudrex._types import MudrexResponse


def _make_response(status_code=200, body=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = json.dumps(body) if body else ""
    resp.json.return_value = body
    return resp


class TestHTTPClientInit(unittest.TestCase):

    def test_init_with_api_secret(self):
        client = _HTTPClient(api_secret="test_secret")
        self.assertEqual(client._api_secret, "test_secret")
        self.assertEqual(
            client._session.headers["X-Authentication"], "test_secret"
        )

    @patch.dict(os.environ, {"MUDREX_API_SECRET": "env_secret"})
    def test_init_from_env(self):
        client = _HTTPClient()
        self.assertEqual(client._api_secret, "env_secret")

    def test_init_no_secret_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MUDREX_API_SECRET", None)
            with self.assertRaises(ValueError) as ctx:
                _HTTPClient()
            self.assertIn("API secret is required", str(ctx.exception))

    def test_init_defaults(self):
        client = _HTTPClient(api_secret="s")
        self.assertEqual(client._timeout, 10)
        self.assertEqual(client._max_retries, 3)
        self.assertFalse(client._log_requests)

    def test_init_custom_params(self):
        client = _HTTPClient(
            api_secret="s", timeout=30, max_retries=5, log_requests=True
        )
        self.assertEqual(client._timeout, 30)
        self.assertEqual(client._max_retries, 5)
        self.assertTrue(client._log_requests)


class TestCleanParams(unittest.TestCase):

    def test_none_input(self):
        self.assertIsNone(_HTTPClient._clean_params(None))

    def test_empty_dict(self):
        self.assertIsNone(_HTTPClient._clean_params({}))

    def test_removes_none_values(self):
        result = _HTTPClient._clean_params({"a": 1, "b": None, "c": "x"})
        self.assertEqual(result, {"a": 1, "c": "x"})

    def test_keeps_empty_string(self):
        result = _HTTPClient._clean_params({"is_symbol": "true", "x": None})
        self.assertEqual(result, {"is_symbol": "true"})

    def test_keeps_zero(self):
        result = _HTTPClient._clean_params({"offset": 0})
        self.assertEqual(result, {"offset": 0})

    def test_all_none_returns_none(self):
        self.assertIsNone(_HTTPClient._clean_params({"a": None, "b": None}))


class TestPrepareBody(unittest.TestCase):

    def test_none_input(self):
        self.assertIsNone(_HTTPClient._prepare_body(None))

    def test_empty_dict(self):
        self.assertIsNone(_HTTPClient._prepare_body({}))

    def test_removes_none_values(self):
        result = _HTTPClient._prepare_body({"a": 1, "b": None})
        self.assertEqual(result, {"a": 1})

    def test_preserves_all_types(self):
        result = _HTTPClient._prepare_body({
            "qty": "0.001",
            "lev": 10,
            "flag": True,
        })
        self.assertEqual(result, {
            "qty": "0.001",
            "lev": 10,
            "flag": True,
        })

    def test_keeps_false_values(self):
        result = _HTTPClient._prepare_body({"reduce_only": False})
        self.assertEqual(result, {"reduce_only": False})

    def test_all_none_returns_none(self):
        self.assertIsNone(_HTTPClient._prepare_body({"a": None}))


class TestHandleResponse(unittest.TestCase):

    def test_success_dict(self):
        resp = _make_response(200, {"success": True, "data": {"id": "abc"}})
        result = _HTTPClient._handle_response(resp)
        self.assertIsInstance(result, MudrexResponse)
        self.assertEqual(result["id"], "abc")

    def test_success_list(self):
        resp = _make_response(200, {
            "success": True,
            "data": [{"id": "a"}, {"id": "b"}],
        })
        result = _HTTPClient._handle_response(resp)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], MudrexResponse)

    def test_success_scalar_wrapped_in_response(self):
        resp = _make_response(200, {"success": True, "data": "62888.3"})
        result = _HTTPClient._handle_response(resp)
        self.assertIsInstance(result, MudrexResponse)
        self.assertEqual(result.result, "62888.3")

    def test_success_none_data_wrapped_in_response(self):
        resp = _make_response(200, {"success": True, "data": None})
        result = _HTTPClient._handle_response(resp)
        self.assertIsInstance(result, MudrexResponse)
        self.assertIsNone(result.result)

    def test_api_error_with_errors_array(self):
        resp = _make_response(400, {
            "success": False,
            "errors": [{"code": 400, "text": "Bad request"}],
        })
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(ctx.exception.message, "Bad request")
        self.assertEqual(ctx.exception.response, resp)

    def test_api_error_without_errors_array(self):
        resp = _make_response(500, {"success": False})
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, 500)

    def test_api_error_success_false_200(self):
        resp = _make_response(200, {
            "success": False,
            "errors": [{"code": 1001, "text": "Rate limited"}],
        })
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, 1001)

    def test_invalid_json(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.text = "not json"
        resp.json.side_effect = ValueError("No JSON")
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertIn("Invalid JSON", ctx.exception.message)

    def test_http_error_no_success_field(self):
        resp = _make_response(403, {"error": "forbidden"})
        with self.assertRaises(MudrexAPIError):
            _HTTPClient._handle_response(resp)

    def test_list_with_non_dict_items(self):
        resp = _make_response(200, {
            "success": True,
            "data": ["abc", 123, {"id": "x"}],
        })
        result = _HTTPClient._handle_response(resp)
        self.assertEqual(result[0], "abc")
        self.assertEqual(result[1], 123)
        self.assertIsInstance(result[2], MudrexResponse)

    def test_empty_body_204_returns_none(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 204
        resp.text = ""
        result = _HTTPClient._handle_response(resp)
        self.assertIsNone(result)

    def test_empty_body_429_raises_rate_limit_message(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 429
        resp.text = ""
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(ctx.exception.message, "API rate limit exceeded")

    def test_empty_body_500_raises_empty_response_message(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        resp.text = ""
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, 500)
        self.assertIn("Empty response body", ctx.exception.message)

    def test_429_malformed_body_raises_rate_limit_message(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 429
        resp.text = "not valid json"
        resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(ctx.exception.message, "API rate limit exceeded")

    def test_double_encoded_error_message_parsed(self):
        resp = _make_response(429, {
            "success": False,
            "message": '{"errors":[{"code":5002,"text":"API rate limit exceeded"}]}',
        })
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, 5002)
        self.assertEqual(ctx.exception.message, "API rate limit exceeded")


class TestNetworkRetries(unittest.TestCase):

    def test_retries_on_connection_error(self):
        client = _HTTPClient(api_secret="s", max_retries=2)
        success_resp = _make_response(200, {"success": True, "data": {"ok": 1}})

        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise requests.exceptions.ConnectionError("conn fail")
            return success_resp

        with patch.object(client._session, "request", side_effect=side_effect):
            result = client._request("GET", "/test")
            self.assertEqual(result["ok"], 1)
            self.assertEqual(call_count, 3)

    def test_retries_on_timeout(self):
        client = _HTTPClient(api_secret="s", max_retries=1)
        success_resp = _make_response(200, {"success": True, "data": None})

        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.exceptions.Timeout("timed out")
            return success_resp

        with patch.object(client._session, "request", side_effect=side_effect):
            client._request("GET", "/test")
            self.assertEqual(call_count, 2)

    def test_raises_after_retries_exhausted(self):
        client = _HTTPClient(api_secret="s", max_retries=2)

        with patch.object(
            client._session,
            "request",
            side_effect=requests.exceptions.ConnectionError("down"),
        ):
            with self.assertRaises(MudrexRequestError) as ctx:
                client._request("GET", "/test")
            self.assertIn("down", ctx.exception.message)
            self.assertIsNotNone(ctx.exception.original_error)


class TestMudrexResponse(unittest.TestCase):

    def test_dict_access(self):
        r = MudrexResponse({"order_id": "abc"})
        self.assertEqual(r["order_id"], "abc")

    def test_attribute_access(self):
        r = MudrexResponse({"order_id": "abc"})
        self.assertEqual(r.order_id, "abc")

    def test_missing_attribute_raises(self):
        r = MudrexResponse({"order_id": "abc"})
        with self.assertRaises(AttributeError):
            _ = r.nonexistent

    def test_repr(self):
        r = MudrexResponse({"id": 1})
        self.assertIn("MudrexResponse", repr(r))


class TestPing(unittest.TestCase):

    def _make_client(self):
        return _HTTPClient(api_secret="test_secret")

    def test_ping_success(self):
        client = self._make_client()
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.json.return_value = {"code": 200, "text": "pong"}
        with patch.object(client._session, "get", return_value=resp):
            client._ping()

    def test_ping_bad_secret(self):
        client = self._make_client()
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {
            "success": False,
            "errors": [{"text": "Invalid Authentication", "code": 3100}],
        }
        with patch.object(client._session, "get", return_value=resp):
            with self.assertRaises(MudrexAPIError) as ctx:
                client._ping()
            self.assertEqual(ctx.exception.code, 401)
            self.assertIn("Invalid Authentication", ctx.exception.message)

    def test_ping_network_error(self):
        client = self._make_client()
        with patch.object(
            client._session, "get",
            side_effect=requests.exceptions.ConnectionError("unreachable"),
        ):
            with self.assertRaises(MudrexRequestError) as ctx:
                client._ping()
            self.assertIn("Cannot reach", ctx.exception.message)

    def test_ping_timeout(self):
        client = self._make_client()
        with patch.object(
            client._session, "get",
            side_effect=requests.exceptions.Timeout("timed out"),
        ):
            with self.assertRaises(MudrexRequestError):
                client._ping()

    def test_ping_unexpected_status(self):
        client = self._make_client()
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 503
        resp.json.return_value = {}
        with patch.object(client._session, "get", return_value=resp):
            with self.assertRaises(MudrexAPIError) as ctx:
                client._ping()
            self.assertEqual(ctx.exception.code, 503)


if __name__ == "__main__":
    unittest.main()
