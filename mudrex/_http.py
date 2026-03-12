import json
import logging
import os
from decimal import Decimal

import requests

from ._exceptions import MudrexAPIError, MudrexRequestError
from ._types import MudrexResponse

BASE_URL = "https://trade.mudrex.com"
DEFAULT_TIMEOUT = 10

logger = logging.getLogger("mudrex")


class _HTTPClient:
    """Low-level HTTP transport for the Mudrex FAPI.

    Handles authentication headers, request dispatch, response parsing,
    and network-error retries.  No rate-limit throttling — requests fire
    immediately; API errors (including rate-limit) are surfaced as exceptions.
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
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
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
        """Remove ``None`` values and convert ``Decimal`` to ``str``."""
        if not body:
            return None
        prepared = {}
        for k, v in body.items():
            if v is None:
                continue
            if isinstance(v, Decimal):
                prepared[k] = str(v)
            else:
                prepared[k] = v
        return prepared or None

    # ── request / response ──────────────────────────────────────────────

    def _request(self, method, path, params=None, body=None):
        url = f"{BASE_URL}/fapi/v1{path}"
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
                break
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as e:
                retries_left -= 1
                if retries_left < 0:
                    raise MudrexRequestError(str(e), original_error=e)

        if self._log_requests:
            logger.debug(
                "Response %s: %s", response.status_code, response.text[:500]
            )

        return self._handle_response(response)

    @staticmethod
    def _handle_response(response):
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            raise MudrexAPIError(
                message=f"Invalid JSON response: {response.text[:200]}",
                code=response.status_code,
                response=response,
            )

        if response.status_code >= 400 or not data.get("success", False):
            errors = data.get("errors", [])
            if errors:
                message = errors[0].get("text", "Unknown error")
                code = errors[0].get("code", response.status_code)
            else:
                message = f"Request failed with status {response.status_code}"
                code = response.status_code
            raise MudrexAPIError(
                message=message, code=code, response=response
            )

        result = data.get("data")
        if isinstance(result, dict):
            return MudrexResponse(result)
        if isinstance(result, list):
            return [
                MudrexResponse(item) if isinstance(item, dict) else item
                for item in result
            ]
        return result

    # ── convenience verbs ───────────────────────────────────────────────

    def _get(self, path, params=None):
        return self._request("GET", path, params=params)

    def _post(self, path, params=None, body=None):
        return self._request("POST", path, params=params, body=body)

    def _patch(self, path, params=None, body=None):
        return self._request("PATCH", path, params=params, body=body)

    def _delete(self, path, params=None):
        return self._request("DELETE", path, params=params)
