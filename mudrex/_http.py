import json
import logging
import os
import time

import requests
from requests.exceptions import ConnectionError, ConnectTimeout, Timeout
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError

from ._exceptions import MudrexAPIError, MudrexRequestError
from ._types import MudrexResponse

try:
    from ._version import __version__ as _SDK_VERSION
except ImportError:
    _SDK_VERSION = "0.0.0.dev0"

BASE_URL = "https://trade.mudrex.com"
DEFAULT_TIMEOUT = 10
# A 429 is retried only when Retry-After is at or below this many seconds.
MAX_RETRY_AFTER = 30

logger = logging.getLogger("mudrex")


class _HTTPClient:
    """Low-level HTTP transport for the Mudrex FAPI.

    Handles authentication headers, request dispatch, response parsing,
    and retries.  No proactive throttling — requests fire immediately.  A 429
    is retried after its ``Retry-After`` wait when that is at most
    ``MAX_RETRY_AFTER`` seconds; other API errors are surfaced as exceptions.
    """

    def __init__(
        self,
        api_secret=None,
        timeout=None,
        max_retries=3,
        log_requests=False,
    ):
        self._api_secret = api_secret or os.environ.get("MUDREX_API_SECRET")
        if not self._api_secret:
            raise ValueError(
                "API secret is required. "
                "Pass api_secret= or set the MUDREX_API_SECRET environment variable."
            )

        self._timeout = timeout or DEFAULT_TIMEOUT
        self._max_retries = max_retries
        self._log_requests = log_requests

        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Authentication": self._api_secret,
                "Accept": "application/json",
                "X-Mudrex-SDK-Version": _SDK_VERSION,
            }
        )

    def _ping(self):
        """Hit ``/futures/ping`` to verify connectivity and authentication.

        Raises ``MudrexAPIError`` on bad credentials (401) and
        ``MudrexRequestError`` on network failure.
        """
        url = f"{BASE_URL}/fapi/v1/futures/ping"
        try:
            response = self._session.get(url, timeout=self._timeout)
        except (ConnectionError, Timeout) as e:
            raise MudrexRequestError(
                f"Cannot reach Mudrex API: {e}", original_error=e
            )

        if response.status_code == 401:
            try:
                data = response.json()
                errors = data.get("errors", [])
                msg = errors[0]["text"] if errors else "Invalid API secret"
            except (ValueError, KeyError, IndexError):
                msg = "Invalid API secret"
            raise MudrexAPIError(message=msg, code=401, response=response)

        if response.status_code != 200:
            raise MudrexAPIError(
                message=f"Ping failed with status {response.status_code}",
                code=response.status_code,
                response=response,
            )

    # ── internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _clean_params(params):
        """Remove ``None`` values so they don't appear in the query string."""
        if not params:
            return None
        cleaned = {k: v for k, v in params.items() if v is not None}
        return cleaned or None

    @staticmethod
    def _prepare_body(body):
        """Remove ``None`` values from the body. No type conversion — client is responsible for correct types."""
        if not body:
            return None
        prepared = {k: v for k, v in body.items() if v is not None}
        return prepared or None

    # ── request / response ──────────────────────────────────────────────

    def _request(self, method, path, params=None, body=None, version="v1"):
        url = f"{BASE_URL}/fapi/{version}{path}"
        params = self._clean_params(params)
        body = self._prepare_body(body)

        headers = {}
        if method in ("POST", "PATCH", "DELETE") and body is not None:
            headers["Content-Type"] = "application/json"

        if self._log_requests:
            logger.debug("%s %s params=%s body=%s", method, url, params, body)

        retries_left = self._max_retries
        while True:
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=body,
                    headers=headers,
                    timeout=self._timeout,
                )
            except (ConnectionError, Timeout) as e:
                retries_left -= 1
                # A POST may have reached the exchange before the failure
                # (e.g. read timeout), so resending could duplicate it. Only
                # retry it when the request provably never left.
                if method == "POST" and not self._never_sent(e):
                    raise MudrexRequestError(str(e), original_error=e)
                if retries_left < 0:
                    raise MudrexRequestError(str(e), original_error=e)
                continue

            # 429 means the request was rejected before processing, so any
            # method (POST included) is safe to resend after the wait.
            if response.status_code == 429 and retries_left > 0:
                wait = self._retry_after(response)
                if wait is not None and wait <= MAX_RETRY_AFTER:
                    retries_left -= 1
                    if self._log_requests:
                        logger.debug("429 on %s %s, retrying in %ss", method, url, wait)
                    time.sleep(wait)
                    continue
            break

        if self._log_requests:
            logger.debug(
                "Response %s: %s", response.status_code, response.text[:500]
            )

        return self._handle_response(response)

    @staticmethod
    def _never_sent(exc):
        """True if ``exc`` means the request never reached the server."""
        if isinstance(exc, ConnectTimeout):
            return True
        if isinstance(exc, Timeout):
            return False
        reason = getattr(exc.args[0], "reason", None) if exc.args else None
        return isinstance(reason, (NewConnectionError, ConnectTimeoutError))

    @staticmethod
    def _parse_error_payload(data, status_code):
        """Extract message and code from API error payload.

        Handles both top-level ``errors`` and double-encoded ``message``
        (e.g. message is a JSON string containing errors).
        """
        errors = data.get("errors") if isinstance(data, dict) else None
        if errors and isinstance(errors, list) and len(errors) > 0:
            first = errors[0]
            if isinstance(first, dict):
                return (
                    first.get("text", "Unknown error"),
                    first.get("code", status_code),
                )
        msg_raw = data.get("message") if isinstance(data, dict) else None
        if isinstance(msg_raw, str) and msg_raw.strip():
            try:
                nested = json.loads(msg_raw)
                return _HTTPClient._parse_error_payload(nested, status_code)
            except (json.JSONDecodeError, TypeError):
                return (msg_raw.strip(), status_code)
        return (f"Request failed with status {status_code}", status_code)

    @staticmethod
    def _retry_after(response):
        """Return the ``Retry-After`` header as int seconds, or ``None``.

        The value is returned as sent (not capped); ``None`` if the header is
        missing or not a non-negative integer.
        """
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        try:
            value = str(headers.get("Retry-After")).strip()
        except AttributeError:
            return None
        if not (value.isascii() and value.isdigit()):
            return None
        try:
            return int(value)
        except ValueError:  # absurdly long digit string
            return None

    @staticmethod
    def _handle_response(response):
        raw_text = (response.text or "").strip()
        status = response.status_code

        # Empty body: avoid json(); 2xx is success (e.g. 204 No Content), else error
        if not raw_text:
            if 200 <= status < 300:
                return None
            if status == 429:
                raise MudrexAPIError(
                    message="API rate limit exceeded",
                    code=429,
                    response=response,
                    retry_after=_HTTPClient._retry_after(response),
                )
            raise MudrexAPIError(
                message=f"Empty response body (HTTP {status})",
                code=status,
                response=response,
            )

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            # Body is not valid JSON; for 429 we still want a clear message
            if status == 429:
                raise MudrexAPIError(
                    message="API rate limit exceeded",
                    code=429,
                    response=response,
                    retry_after=_HTTPClient._retry_after(response),
                )
            raise MudrexAPIError(
                message=f"Invalid JSON response: {raw_text[:200]}",
                code=status,
                response=response,
            )

        if status >= 400 or not data.get("success", False):
            message, code = _HTTPClient._parse_error_payload(data, status)
            raise MudrexAPIError(
                message=message,
                code=code,
                response=response,
                retry_after=(
                    _HTTPClient._retry_after(response) if status == 429 else None
                ),
            )

        result = data.get("data")
        if isinstance(result, dict):
            return MudrexResponse(result)
        if isinstance(result, list):
            return [
                MudrexResponse(item) if isinstance(item, dict) else item
                for item in result
            ]
        # ``None`` (data: null) and scalars (e.g. a price string) are returned as-is.
        return result

    # ── convenience verbs ───────────────────────────────────────────────

    def _get(self, path, params=None, version="v1"):
        return self._request("GET", path, params=params, version=version)

    def _post(self, path, params=None, body=None, version="v1"):
        return self._request(
            "POST", path, params=params, body=body, version=version
        )

    def _patch(self, path, params=None, body=None, version="v1"):
        return self._request(
            "PATCH", path, params=params, body=body, version=version
        )

    def _delete(self, path, params=None, version="v1"):
        return self._request("DELETE", path, params=params, version=version)
