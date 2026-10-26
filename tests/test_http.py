"""Tests for _HTTPClient internals: init, helpers, response handling, retries."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from urllib3.exceptions import MaxRetryError, NewConnectionError

from mudrex import __version__ as package_version
from mudrex._exceptions import MudrexAPIError, MudrexRequestError
from mudrex._http import MAX_RETRY_AFTER, _HTTPClient
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
        self.assertEqual(
            client._session.headers["X-Mudrex-SDK-Version"],
            package_version,
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

    def test_success_scalar_returned_as_is(self):
        resp = _make_response(200, {"success": True, "data": "62888.3"})
        self.assertEqual(_HTTPClient._handle_response(resp), "62888.3")

    def test_success_none_data_returns_none(self):
        resp = _make_response(200, {"success": True, "data": None})
        self.assertIsNone(_HTTPClient._handle_response(resp))

    def test_success_bool_data_returned_as_is(self):
        resp = _make_response(200, {"success": True, "data": True})
        self.assertIs(_HTTPClient._handle_response(resp), True)

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

    def test_429_json_body_exposes_retry_after(self):
        resp = _make_response(429, {
            "success": False,
            "errors": [{"code": 5002, "text": "API rate limit exceeded"}],
        })
        resp.headers = {"Retry-After": "7"}
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.retry_after, 7)

    def test_429_empty_body_exposes_retry_after(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 429
        resp.text = ""
        resp.headers = {"Retry-After": "3"}
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.retry_after, 3)

    def test_429_malformed_body_exposes_retry_after(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 429
        resp.text = "nope"
        resp.json.side_effect = json.JSONDecodeError("x", "", 0)
        resp.headers = {"Retry-After": "11"}
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.retry_after, 11)

    def test_429_non_json_body_raises_api_error_with_retry_after(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 429
        resp.text = "<html>Too Many Requests</html>"
        resp.json.side_effect = ValueError("not json")
        resp.headers = {"Retry-After": "9"}
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(ctx.exception.message, "API rate limit exceeded")
        self.assertEqual(ctx.exception.retry_after, 9)
        self.assertIs(ctx.exception.response, resp)

    def test_429_missing_or_bad_retry_after_is_none(self):
        for headers in (
            {}, {"Retry-After": "soon"}, {"Retry-After": "-5"},
            {"Retry-After": "1.5"}, {"Retry-After": "\u00b2"},
            {"Retry-After": "\u0663"}, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
        ):
            resp = _make_response(429, {"success": False, "message": "slow down"})
            resp.headers = headers
            with self.assertRaises(MudrexAPIError) as ctx:
                _HTTPClient._handle_response(resp)
            self.assertIsNone(ctx.exception.retry_after)

    def test_request_versions_for_all_verbs(self):
        client = _HTTPClient(api_secret="s")
        client._session.request = MagicMock(
            return_value=_make_response(200, {"success": True, "data": {}})
        )
        for verb in (client._get, client._post, client._patch, client._delete):
            client._session.request.reset_mock()
            verb("/x", version="v2")
            self.assertTrue(
                client._session.request.call_args[1]["url"].endswith("/fapi/v2/x")
            )
            client._session.request.reset_mock()
            verb("/x")
            self.assertTrue(
                client._session.request.call_args[1]["url"].endswith("/fapi/v1/x")
            )

    def test_non_429_error_has_no_retry_after(self):
        resp = _make_response(500, {"success": False, "message": "boom"})
        resp.headers = {"Retry-After": "5"}
        with self.assertRaises(MudrexAPIError) as ctx:
            _HTTPClient._handle_response(resp)
        self.assertIsNone(ctx.exception.retry_after)

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


class TestPostRetryPolicy(unittest.TestCase):

    def test_post_read_timeout_sent_once_and_raises(self):
        client = _HTTPClient(api_secret="s", max_retries=3)
        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.ReadTimeout("read timed out"),
        ) as mock_request:
            with self.assertRaises(MudrexRequestError):
                client._post("/futures/order", body={"quantity": "1"}, version="v2")
        self.assertEqual(mock_request.call_count, 1)

    def test_post_connection_reset_sent_once_and_raises(self):
        client = _HTTPClient(api_secret="s", max_retries=3)
        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.ConnectionError("Connection aborted"),
        ) as mock_request:
            with self.assertRaises(MudrexRequestError):
                client._post("/futures/positions/p1/close")
        self.assertEqual(mock_request.call_count, 1)

    def test_post_retried_on_connect_error(self):
        client = _HTTPClient(api_secret="s", max_retries=3)
        success = _make_response(200, {"success": True, "data": {"ok": 1}})
        refused = requests.exceptions.ConnectionError(
            MaxRetryError(None, "/", reason=NewConnectionError(None, "refused"))
        )
        with patch.object(
            client._session, "request",
            side_effect=[refused, requests.exceptions.ConnectTimeout("t"), success],
        ) as mock_request:
            result = client._post("/futures/order", body={"quantity": "1"})
        self.assertEqual(result["ok"], 1)
        self.assertEqual(mock_request.call_count, 3)

    def test_post_connect_errors_still_capped_by_max_retries(self):
        client = _HTTPClient(api_secret="s", max_retries=2)
        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.ConnectTimeout("t"),
        ) as mock_request:
            with self.assertRaises(MudrexRequestError):
                client._post("/futures/order")
        self.assertEqual(mock_request.call_count, 3)

    def test_get_read_timeout_still_retried(self):
        client = _HTTPClient(api_secret="s", max_retries=1)
        success = _make_response(200, {"success": True, "data": None})
        with patch.object(
            client._session, "request",
            side_effect=[requests.exceptions.ReadTimeout("t"), success],
        ) as mock_request:
            client._get("/test")
        self.assertEqual(mock_request.call_count, 2)


def _resp_429(retry_after=None, body=None):
    resp = _make_response(429, body)
    resp.headers = {} if retry_after is None else {"Retry-After": retry_after}
    return resp


class TestRateLimitRetry(unittest.TestCase):

    def _client(self, max_retries=3):
        return _HTTPClient(api_secret="s", max_retries=max_retries)

    def test_retry_after_returned_unclamped(self):
        resp = _resp_429("86400")
        self.assertEqual(_HTTPClient._retry_after(resp), 86400)

    def test_429_within_limit_sleeps_and_retries(self):
        client = self._client()
        ok = _make_response(200, {"success": True, "data": {"ok": 1}})
        with patch.object(
            client._session, "request", side_effect=[_resp_429("2"), ok]
        ) as mock_request, patch("mudrex._http.time.sleep") as sleep:
            result = client._get("/test")
        self.assertEqual(result["ok"], 1)
        self.assertEqual(mock_request.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_429_at_limit_is_retried(self):
        client = self._client()
        ok = _make_response(200, {"success": True, "data": None})
        with patch.object(
            client._session, "request",
            side_effect=[_resp_429(str(MAX_RETRY_AFTER)), ok],
        ), patch("mudrex._http.time.sleep") as sleep:
            client._get("/test")
        sleep.assert_called_once_with(MAX_RETRY_AFTER)

    def test_huge_retry_after_raises_immediately_with_real_value(self):
        client = self._client()
        with patch.object(
            client._session, "request", return_value=_resp_429("86400")
        ) as mock_request, patch("mudrex._http.time.sleep") as sleep:
            with self.assertRaises(MudrexAPIError) as ctx:
                client._get("/test")
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(ctx.exception.retry_after, 86400)
        self.assertEqual(mock_request.call_count, 1)
        sleep.assert_not_called()

    def test_just_above_limit_raises_immediately(self):
        client = self._client()
        with patch.object(
            client._session, "request",
            return_value=_resp_429(str(MAX_RETRY_AFTER + 1)),
        ) as mock_request, patch("mudrex._http.time.sleep"):
            with self.assertRaises(MudrexAPIError) as ctx:
                client._get("/test")
        self.assertEqual(ctx.exception.retry_after, MAX_RETRY_AFTER + 1)
        self.assertEqual(mock_request.call_count, 1)

    def test_missing_or_invalid_retry_after_raises_immediately(self):
        for value in (None, "soon", "-5", "1.5", "Wed, 21 Oct 2026 07:28:00 GMT"):
            client = self._client()
            with patch.object(
                client._session, "request", return_value=_resp_429(value)
            ) as mock_request, patch("mudrex._http.time.sleep") as sleep:
                with self.assertRaises(MudrexAPIError) as ctx:
                    client._get("/test")
            self.assertIsNone(ctx.exception.retry_after)
            self.assertEqual(mock_request.call_count, 1)
            sleep.assert_not_called()

    def test_retries_capped_by_max_retries(self):
        client = self._client(max_retries=2)
        with patch.object(
            client._session, "request", return_value=_resp_429("1")
        ) as mock_request, patch("mudrex._http.time.sleep") as sleep:
            with self.assertRaises(MudrexAPIError) as ctx:
                client._get("/test")
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(ctx.exception.retry_after, 1)
        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_max_retries_zero_does_not_retry_429(self):
        client = self._client(max_retries=0)
        with patch.object(
            client._session, "request", return_value=_resp_429("1")
        ) as mock_request, patch("mudrex._http.time.sleep") as sleep:
            with self.assertRaises(MudrexAPIError):
                client._get("/test")
        self.assertEqual(mock_request.call_count, 1)
        sleep.assert_not_called()

    def test_429_with_empty_body_retried(self):
        client = self._client()
        ok = _make_response(200, {"success": True, "data": None})
        with patch.object(
            client._session, "request", side_effect=[_resp_429("1"), ok]
        ) as mock_request, patch("mudrex._http.time.sleep"):
            client._get("/test")
        self.assertEqual(mock_request.call_count, 2)

    def test_post_429_is_retried(self):
        client = self._client()
        ok = _make_response(200, {"success": True, "data": {"order_id": "o1"}})
        with patch.object(
            client._session, "request", side_effect=[_resp_429("1"), ok]
        ) as mock_request, patch("mudrex._http.time.sleep"):
            result = client._post("/futures/order", body={"quantity": "1"}, version="v2")
        self.assertEqual(result["order_id"], "o1")
        self.assertEqual(mock_request.call_count, 2)

    def test_429_retries_share_budget_with_network_retries(self):
        client = self._client(max_retries=2)
        ok = _make_response(200, {"success": True, "data": None})
        with patch.object(
            client._session, "request",
            side_effect=[
                requests.exceptions.ConnectionError("x"), _resp_429("1"), _resp_429("1"),
            ],
        ) as mock_request, patch("mudrex._http.time.sleep"):
            with self.assertRaises(MudrexAPIError):
                client._get("/test")
        self.assertEqual(mock_request.call_count, 3)


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


class TestPingIndependentOfResponseUnwrapping(unittest.TestCase):
    """_ping uses the raw session, not _get, so null/scalar data is irrelevant."""

    def test_ping_ok_when_data_is_null(self):
        client = _HTTPClient(api_secret="s")
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.text = json.dumps({"success": True, "data": None})
        with patch.object(client._session, "get", return_value=resp):
            self.assertIsNone(client._ping())


if __name__ == "__main__":
    unittest.main()
