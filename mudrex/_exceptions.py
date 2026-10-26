class MudrexError(Exception):
    """Base exception for the Mudrex SDK."""

    def __init__(self, message):
        self.message = message
        super().__init__(message)

    def __str__(self):
        return str(self.message)


class MudrexAPIError(MudrexError):
    """Raised when the Mudrex API returns an error response.

    Attributes:
        message: Human-readable error description.
        code: Error code from the API (int).
        response: Raw ``requests.Response`` object for inspection.
        retry_after: Seconds to wait before retrying, from the ``Retry-After``
            header on HTTP 429 responses. ``None`` when the header is absent
            or not an integer number of seconds.
    """

    def __init__(self, message, code=None, response=None, retry_after=None):
        super().__init__(message)
        self.code = code
        self.response = response
        self.retry_after = retry_after

    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return super().__str__()


class MudrexRequestError(MudrexError):
    """Raised on network or connection errors.

    Attributes:
        message: Human-readable error description.
        original_error: The underlying ``requests`` exception.
    """

    def __init__(self, message, original_error=None):
        super().__init__(message)
        self.original_error = original_error
