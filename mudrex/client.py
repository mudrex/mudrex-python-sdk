import warnings
from typing import Optional, Union
from urllib.parse import quote

from ._http import _HTTPClient

Numeric = Union[str, int, float]

SUPPORTED_CURRENCIES = ("USDT", "INR")


class TradeClient(_HTTPClient):
    """Mudrex Futures Trading API client.

    All FAPI endpoints are exposed as flat methods on this class.
    Symbol-first: pass a trading symbol (e.g. ``"BTCUSDT"``) as the first
    argument wherever an asset identifier is needed.  For the rare case of
    using a raw asset UUID, pass ``asset_id=`` instead.

    Numeric parameters (quantity, leverage, prices, amount, margin, etc.) accept
    ``str``, ``int``, or ``float``. For precision, pass strings (e.g. ``"0.001"``,
    ``"10"``) — the API uses string values for numerics; the SDK does not convert.

    Args:
        api_secret: Your Mudrex API secret.             
            Falls back to the ``MUDREX_API_SECRET`` environment variable.
        trade_currency: Trade currency for this client: ``"USDT"`` (default)
            or ``"INR"``.
        timeout: Request timeout in seconds (default ``10``).
        max_retries: Retries on transient network errors (default ``3``).
            POST requests are retried only when the request never left
            (connect failures), never after a read timeout or reset.
        log_requests: Emit debug logs for every request/response (default ``False``).

    Example::

        from mudrex import TradeClient

        client = TradeClient(api_secret="your_secret")
        client.set_leverage("BTCUSDT", leverage="10")  # leverage is set first
        client.place_order(
            "BTCUSDT",
            quantity="0.001",   # use string for precision
            order_type="LONG",
            trigger_type="MARKET",
        )
    """

    def __init__(
        self,
        api_secret: Optional[str] = None,
        *,
        trade_currency: str = "USDT",
        timeout: int = 10,
        max_retries: int = 3,
        log_requests: bool = False,
    ):
        super().__init__(
            api_secret=api_secret,
            timeout=timeout,
            max_retries=max_retries,
            log_requests=log_requests,
        )
        self._trade_currency = self._validate_currency(
            trade_currency, "trade_currency"
        )
        self._ping()

    def ping(self):
        """Verify connectivity and authentication by calling the futures ping endpoint.

        Raises ``MudrexAPIError`` on bad credentials (401) and
        ``MudrexRequestError`` on network failure. Call this anytime to test
        that the API is reachable and the secret is valid.
        """
        self._ping()

    # ── internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _resolve_asset(symbol=None, asset_id=None):
        """Return ``(identifier, extra_params)`` for an asset path segment."""
        if symbol and asset_id:
            raise ValueError("Provide either 'symbol' or 'asset_id', not both")
        if not symbol and not asset_id:
            raise ValueError("Either 'symbol' or 'asset_id' is required")
        if symbol:
            return symbol, {"is_symbol": "true"}
        return asset_id, {}

    @staticmethod
    def _validate_currency(value, name):
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"Unsupported {name} {value!r}. Use one of: "
                + ", ".join(SUPPORTED_CURRENCIES)
                + "."
            )
        return value

    @staticmethod
    def _seg(value):
        """Percent-encode a value for use as one URL path segment."""
        return quote(str(value), safe="")

    @staticmethod
    def _require_id(value, name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"'{name}' is required")
        return value

    @staticmethod
    def _asset_query(symbol=None, asset_id=None):
        """Return the ``symbol`` / ``id`` query params used by v2 endpoints."""
        if symbol and asset_id:
            raise ValueError("Provide either 'symbol' or 'asset_id', not both")
        if not symbol and not asset_id:
            raise ValueError("Either 'symbol' or 'asset_id' is required")
        return {"symbol": symbol} if symbol else {"id": asset_id}

    # ════════════════════════════════════════════════════════════════════
    #  FUTURES / ASSETS
    # ════════════════════════════════════════════════════════════════════

    def list_futures(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
        sort: Optional[str] = None,
        order: Optional[str] = None,
    ):
        """List all available futures contracts.

        Args:
            limit: Number of results (default 10).
            offset: Pagination offset (default 0).
            sort: Sort field (e.g. ``"volume"``).
            order: Sort direction (``"asc"`` or ``"desc"``).
        """
        return self._get(
            "/futures",
            params={"limit": limit, "offset": offset, "sort": sort, "order": order},
        )

    def get_future(
        self,
        symbol: Optional[str] = None,
        *,
        asset_id: Optional[str] = None,
    ):
        """Get details for a single futures contract.

        Args:
            symbol: Trading symbol (e.g. ``"BTCUSDT"``).
            asset_id: Asset UUID (alternative to symbol).
        """
        identifier, params = self._resolve_asset(symbol, asset_id)
        return self._get(f"/futures/{self._seg(identifier)}", params=params)

    def get_available_funds(self, *, source: Optional[str] = None):
        """Get available funds for futures trading.

        Args:
            source: ``"transfer"`` for transfer-page context, omit otherwise.
        """
        return self._get(
            "/futures/funds",
            params={"source": source, "trade_currency": self._trade_currency},
        )

    # ════════════════════════════════════════════════════════════════════
    #  LEVERAGE
    # ════════════════════════════════════════════════════════════════════

    def get_leverage(
        self,
        symbol: Optional[str] = None,
        *,
        asset_id: Optional[str] = None,
    ):
        """Get current leverage and margin type for an asset.

        Args:
            symbol: Trading symbol (e.g. ``"BTCUSDT"``).
            asset_id: Asset UUID (alternative to symbol).
        """
        identifier, params = self._resolve_asset(symbol, asset_id)
        params["trade_currency"] = self._trade_currency
        return self._get(f"/futures/{self._seg(identifier)}/leverage", params=params)

    def set_leverage(
        self,
        symbol: Optional[str] = None,
        *,
        asset_id: Optional[str] = None,
        leverage: Numeric,
        margin_type: str = "ISOLATED",
    ):
        """Set leverage for an asset.

        Args:
            symbol: Trading symbol (e.g. ``"BTCUSDT"``).
            asset_id: Asset UUID (alternative to symbol).
            leverage: Leverage value (must be within the asset's permissible range).
            margin_type: Margin type (default ``"ISOLATED"``).
        """
        identifier, params = self._resolve_asset(symbol, asset_id)
        return self._post(
            f"/futures/{self._seg(identifier)}/leverage",
            params=params,
            body={
                "leverage": leverage,
                "margin_type": margin_type,
                "trade_currency": self._trade_currency,
            },
        )

    # ════════════════════════════════════════════════════════════════════
    #  ORDERS
    # ════════════════════════════════════════════════════════════════════

    def place_order(
        self,
        symbol: Optional[str] = None,
        *,
        asset_id: Optional[str] = None,
        quantity: Numeric,
        order_type: str,
        trigger_type: str,
        order_price: Optional[Numeric] = None,
        is_stoploss: bool = False,
        is_takeprofit: bool = False,
        stoploss_price: Optional[Numeric] = None,
        takeprofit_price: Optional[Numeric] = None,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
        leverage: Optional[Numeric] = None,
    ):
        """Place a new futures order (``POST /fapi/v2/futures/order``).

        Leverage is not part of the request. Call :meth:`set_leverage` for the
        asset first, otherwise the API returns ``400 leverage not found``.
        The ``leverage`` argument is deprecated: it is ignored (never sent)
        and emits a ``FutureWarning``. It will be removed in 0.3.0.

        Args:
            symbol: Trading symbol (e.g. ``"BTCUSDT"``).
            asset_id: Asset UUID (alternative to symbol).
            quantity: Order quantity.
            order_type: ``"LONG"`` or ``"SHORT"``.
            trigger_type: ``"MARKET"`` or ``"LIMIT"``.
            order_price: Limit price (required for ``LIMIT`` orders).
            is_stoploss: Attach a stop-loss to this order.
            is_takeprofit: Attach a take-profit to this order.
            stoploss_price: Stop-loss trigger price (required when ``is_stoploss=True``).
            takeprofit_price: Take-profit trigger price (required when ``is_takeprofit=True``).
            reduce_only: If ``True``, order can only reduce/close an existing position.
            client_order_id: Optional caller-chosen id (letters, digits, ``-``,
                ``_``; max 64 chars). Returned in the response. An invalid
                format raises ``MudrexAPIError`` (400); reusing an accepted id
                raises ``MudrexAPIError`` (409). A place is never resent once the
                request may have reached the API (e.g. a read timeout); only
                connect failures, where nothing was sent, are retried.
                If a response is lost, call :meth:`get_order_detail` with the
                ``client_order_id`` before deciding to place again.

        The asset's ``min_contract`` does not reflect the minimum order
        value. Orders below it fail with
        ``400 order value less than minimum required value``.

        Returns:
            Object with ``order_id``, ``position_id``, ``status``,
            ``client_order_id`` (when set), etc.
        """
        if leverage is not None:
            # Deprecated: ignored, never sent. Removed in 0.3.0.
            warnings.warn(
                "leverage is ignored by place_order and will be removed in 0.3.0; "
                "use set_leverage()",
                FutureWarning,
                stacklevel=2,
            )
        return self._post(
            "/futures/order",
            params=self._asset_query(symbol, asset_id),
            body={
                "quantity": quantity,
                "order_type": order_type,
                "trigger_type": trigger_type,
                "order_price": order_price,
                "is_stoploss": is_stoploss,
                "is_takeprofit": is_takeprofit,
                "stoploss_price": stoploss_price,
                "takeprofit_price": takeprofit_price,
                "reduce_only": reduce_only,
                "trade_currency": self._trade_currency,
                "client_order_id": client_order_id,
            },
            version="v2",
        )

    def get_orders(self, *, limit: int = 20, offset: Optional[int] = None):
        """Get open orders.

        Args:
            limit: Number of results (default 20).
            offset: Offset timestamp in milliseconds for pagination.
        """
        return self._get(
            "/futures/orders",
            params={
                "limit": limit,
                "offset": offset,
                "trade_currency": self._trade_currency,
            },
        )

    def get_order(self, order_id: str):
        """Get a single order by ID.

        .. deprecated::
            Use :meth:`get_order_detail`, the documented single-order read.

        Args:
            order_id: Order UUID.
        """
        warnings.warn(
            "get_order() is deprecated; use get_order_detail() instead.",
            FutureWarning,
            stacklevel=2,
        )
        return self._get(f"/futures/orders/{self._seg(order_id)}")

    def get_order_detail(
        self,
        order_id: Optional[str] = None,
        *,
        client_order_id: Optional[str] = None,
    ):
        """Get a single order by Mudrex UUID and/or ``client_order_id``.

        Provide at least one. If both are given they must refer to the same
        order, otherwise the API returns 404.

        Args:
            order_id: Order UUID.
            client_order_id: Caller-chosen id set at placement.
        """
        if not order_id and not client_order_id:
            raise ValueError("Either 'order_id' or 'client_order_id' is required")
        return self._get(
            "/futures/orders/detail",
            params={"order_id": order_id, "client_order_id": client_order_id},
        )

    def get_execution_report(self, order_id: str):
        """Get the execution report (per-fill detail) for an order.

        Args:
            order_id: Order UUID.

        Returns:
            Order-level fields plus an ``executions`` list of fills. Each fill
            has ``filled_price``, ``filled_qty``, ``filled_value``,
            ``filled_time``, ``is_maker``, ``trading_fee`` and ``trxn_id``.
        """
        self._require_id(order_id, "order_id")
        return self._get(f"/futures/orders/{self._seg(order_id)}/execution-report")

    def get_order_history(self, *, limit: int = 20, offset: Optional[int] = None):
        """Get order history (filled, partially filled, cancelled).

        Args:
            limit: Number of results (default 20).
            offset: Offset timestamp in milliseconds for pagination.
        """
        return self._get(
            "/futures/orders/history",
            params={
                "limit": limit,
                "offset": offset,
                "trade_currency": self._trade_currency,
            },
        )

    def amend_order(
        self,
        order_id: str,
        *,
        order_price: Optional[Numeric] = None,
        quantity: Optional[Numeric] = None,
        is_stoploss: Optional[bool] = None,
        is_takeprofit: Optional[bool] = None,
        stoploss_price: Optional[Numeric] = None,
        takeprofit_price: Optional[Numeric] = None,
        stoploss_order_id: Optional[str] = None,
        takeprofit_order_id: Optional[str] = None,
    ):
        """Amend an existing limit order.

        Per the API docs, ``order_price`` and ``quantity`` are both required
        when amending the order itself; a price-only amend is documented to
        return 400. The SDK sends exactly what you pass and surfaces the API
        response unchanged.

        Args:
            order_id: Order UUID.
            order_price: New limit price.
            quantity: New quantity (base asset).
            is_stoploss: Set/update stop-loss.
            is_takeprofit: Set/update take-profit.
            stoploss_price: New stop-loss price.
            takeprofit_price: New take-profit price.
            stoploss_order_id: Existing stop-loss order UUID to amend.
            takeprofit_order_id: Existing take-profit order UUID to amend.
        """
        return self._patch(
            f"/futures/orders/{self._seg(order_id)}",
            body={
                "order_price": order_price,
                "quantity": quantity,
                "is_stoploss": is_stoploss,
                "is_takeprofit": is_takeprofit,
                "stoploss_price": stoploss_price,
                "takeprofit_price": takeprofit_price,
                "stoploss_order_id": stoploss_order_id,
                "takeprofit_order_id": takeprofit_order_id,
            },
        )

    def cancel_order(
        self,
        order_id: Optional[str] = None,
        *,
        client_order_id: Optional[str] = None,
    ):
        """Cancel an open order by UUID or by ``client_order_id``.

        Pass exactly one. Cancel by UUID uses ``DELETE /futures/orders/{order_id}``;
        cancel by client id uses ``DELETE /futures/orders?client_order_id=...``.

        On success the API can return empty ``message``, ``order_id`` and
        ``status`` strings. Confirm the outcome with :meth:`get_order_detail`.

        Args:
            order_id: Order UUID.
            client_order_id: Caller-chosen id set at placement.
        """
        if bool(order_id) == bool(client_order_id):
            raise ValueError(
                "Provide exactly one of 'order_id' or 'client_order_id'"
            )
        if client_order_id:
            return self._delete(
                "/futures/orders", params={"client_order_id": client_order_id}
            )
        return self._delete(f"/futures/orders/{self._seg(order_id)}")

    # ════════════════════════════════════════════════════════════════════
    #  POSITIONS
    # ════════════════════════════════════════════════════════════════════

    def get_positions(self, *, limit: int = 20, offset: Optional[int] = None):
        """Get open positions.

        Each item has ``id`` and, as of API v1.0.12, ``position_id`` (same
        value). Returns an empty list when there are no open positions.

        Args:
            limit: Number of results (default 20).
            offset: Offset timestamp in milliseconds for pagination.
        """
        result = self._get(
            "/futures/positions",
            params={
                "limit": limit,
                "offset": offset,
                "trade_currency": self._trade_currency,
            },
        )
        # The API sends ``data: null`` when there are no open positions.
        return [] if result is None else result

    def get_position_history(self, *, limit: int = 20, offset: Optional[int] = None):
        """Get closed/liquidated position history.

        Each row's ``id`` is the history-row UUID, not the position UUID.
        Use the row's ``position_id`` for the position and ``order_id`` for
        the order that closed it (API v1.0.12).

        Args:
            limit: Number of results (default 20).
            offset: Offset timestamp in milliseconds for pagination.
        """
        return self._get(
            "/futures/positions/history",
            params={
                "limit": limit,
                "offset": offset,
                "trade_currency": self._trade_currency,
            },
        )

    def close_position(self, position_id: str):
        """Close an entire position (square off).

        Args:
            position_id: Position UUID.

        Returns:
            Object ``{order_id, position_id, status, message}``: ``order_id``
            is the close order UUID and ``position_id`` the position UUID.
            Before API v1.0.12 ``position_id`` held the close order UUID; read
            ``order_id`` for it now. ``status`` is ``"CREATED"`` because the
            close is asynchronous; check the final state with
            :meth:`get_order_detail`.
        """
        return self._post(f"/futures/positions/{self._seg(position_id)}/close")

    def close_position_partial(
        self,
        position_id: str,
        *,
        quantity: Numeric,
        order_type: str,
        limit_price: Optional[Numeric] = None,
        client_order_id: Optional[str] = None,
    ):
        """Partially close a position.

        Args:
            position_id: Position UUID.
            quantity: Quantity to close.
            order_type: ``"MARKET"`` or ``"LIMIT"`` (API v1.0.12). The close
                side is always the opposite of the position.
            limit_price: Limit price. Required when ``order_type="LIMIT"``.
            client_order_id: Optional id applied to the generated close order
                (not the original order or the position).

        Returns:
            Object ``{order_id, position_id, quantity}`` (API v1.0.12; this
            was ``True`` before). ``order_id`` is the close order UUID and
            ``quantity`` is a string.
        """
        return self._post(
            f"/futures/positions/{self._seg(position_id)}/close/partial",
            body={
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": limit_price,
                "client_order_id": client_order_id,
            },
        )

    def reverse_position(self, position_id: str):
        """Reverse a position (close current and open opposite).

        Args:
            position_id: Position UUID.
        """
        return self._post(f"/futures/positions/{self._seg(position_id)}/reverse")

    def place_risk_order(
        self,
        position_id: str,
        *,
        is_stoploss: bool = False,
        is_takeprofit: bool = False,
        stoploss_price: Optional[Numeric] = None,
        takeprofit_price: Optional[Numeric] = None,
        stoploss_client_order_id: Optional[str] = None,
        takeprofit_client_order_id: Optional[str] = None,
    ):
        """Place stop-loss and/or take-profit on a position.

        At least one of ``is_stoploss`` or ``is_takeprofit`` must be ``True``.

        Args:
            position_id: Position UUID.
            is_stoploss: Place a stop-loss order.
            is_takeprofit: Place a take-profit order.
            stoploss_price: Trigger price (required when ``is_stoploss=True``).
            takeprofit_price: Trigger price (required when ``is_takeprofit=True``).
            stoploss_client_order_id: Optional id to set on the new stop-loss order.
            takeprofit_client_order_id: Optional id to set on the new take-profit order.
        """
        return self._post(
            f"/futures/positions/{self._seg(position_id)}/riskorder",
            body={
                "is_stoploss": is_stoploss,
                "is_takeprofit": is_takeprofit,
                "stoploss_price": stoploss_price,
                "takeprofit_price": takeprofit_price,
                "stoploss_client_order_id": stoploss_client_order_id,
                "takeprofit_client_order_id": takeprofit_client_order_id,
            },
        )

    def amend_risk_order(
        self,
        position_id: str,
        *,
        is_stoploss: Optional[bool] = None,
        is_takeprofit: Optional[bool] = None,
        stoploss_order_id: Optional[str] = None,
        takeprofit_order_id: Optional[str] = None,
        stoploss_price: Optional[Numeric] = None,
        takeprofit_price: Optional[Numeric] = None,
        stoploss_client_order_id: Optional[str] = None,
        takeprofit_client_order_id: Optional[str] = None,
        trigger_type: Optional[str] = None,
    ):
        """Amend existing risk orders (stop-loss / take-profit) on a position.

        On edit, the ``*_client_order_id`` arguments only *locate* an existing
        risk order; they cannot set or change its id.

        Args:
            position_id: Position UUID.
            is_stoploss: Amend the stop-loss order.
            is_takeprofit: Amend the take-profit order.
            stoploss_order_id: Existing stop-loss order UUID.
            takeprofit_order_id: Existing take-profit order UUID.
            stoploss_price: New stop-loss trigger price.
            takeprofit_price: New take-profit trigger price.
            stoploss_client_order_id: Locate the stop-loss by client order id.
            takeprofit_client_order_id: Locate the take-profit by client order id.
            trigger_type: ``"MARKET"`` or ``"LIMIT"`` (optional).
        """
        return self._patch(
            f"/futures/positions/{self._seg(position_id)}/riskorder",
            body={
                "is_stoploss": is_stoploss,
                "is_takeprofit": is_takeprofit,
                "stoploss_order_id": stoploss_order_id,
                "takeprofit_order_id": takeprofit_order_id,
                "stoploss_price": stoploss_price,
                "takeprofit_price": takeprofit_price,
                "stoploss_client_order_id": stoploss_client_order_id,
                "takeprofit_client_order_id": takeprofit_client_order_id,
                "trigger_type": trigger_type,
            },
        )

    def add_margin(self, position_id: str, *, margin: Numeric):
        """Add margin to an open position.

        Args:
            position_id: Position UUID.
            margin: Amount of margin to add.
        """
        return self._post(
            f"/futures/positions/{self._seg(position_id)}/add-margin",
            body={"margin": margin},
        )

    def get_liquidation_price(
        self,
        position_id: str,
        *,
        ext_margin: Optional[Numeric] = None,
    ):
        """Get the liquidation price for a position.

        Args:
            position_id: Position UUID.
            ext_margin: Simulate additional margin to see the projected
                liquidation price (optional).
        """
        return self._get(
            f"/futures/positions/{self._seg(position_id)}/liq-price",
            params={
                "ext_margin": ext_margin,
                "trade_currency": self._trade_currency,
            },
        )

    # ════════════════════════════════════════════════════════════════════
    #  FEES
    # ════════════════════════════════════════════════════════════════════

    def get_fee_history(self, *, limit: int = 10, offset: Optional[int] = None):
        """Get trading fee history.

        ``order_id`` is not present on every row: non-trade fees such as
        funding have none. Read it with ``row.get("order_id")``.

        Args:
            limit: Number of results (default 10).
            offset: Offset timestamp in milliseconds for pagination.
        """
        return self._get(
            "/futures/fee/history",
            params={
                "limit": limit,
                "offset": offset,
                "trade_currency": self._trade_currency,
            },
        )

    def get_fee(self, fee_id: str):
        """Get a single fee record by id.

        Args:
            fee_id: Fee UUID, taken from an ``id`` in :meth:`get_fee_history`.

        Returns:
            Fee details including ``role`` (``MAKER``/``TAKER``) and ``fills``
            when returned.
        """
        self._require_id(fee_id, "fee_id")
        return self._get(f"/futures/fee/{self._seg(fee_id)}")

    # ════════════════════════════════════════════════════════════════════
    #  TRANSACTIONS
    # ════════════════════════════════════════════════════════════════════

    def get_transactions(
        self,
        *,
        limit: Optional[int] = None,
        trade_currency: Optional[str] = None,
        transaction_type: Optional[str] = None,
        status: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
    ):
        """Get futures wallet transfer records (deposits / withdrawals).

        Known backend issues: ``trade_currency`` is currently not applied by
        the API (it returns the same rows for USDT and INR), and
        ``status="Processing"`` currently returns no rows.

        Args:
            limit: Maximum number of records.
            trade_currency: ``"USDT"`` or ``"INR"``. Defaults to the client's
                trade currency.
            transaction_type: ``"DEPOSIT"`` or ``"WITHDRAW"``
                (case-insensitive); sent as the ``type`` query parameter.
            status: ``"Completed"``, ``"Processing"`` or ``"Failed"``
                (case-insensitive; sent title-cased).
            sort_by: ``"created_at"`` or ``"updated_at"`` (case-insensitive;
                sent lower-cased).
            sort_order: ``"asc"`` or ``"desc"`` (case-insensitive; sent
                lower-cased).
        """
        trade_currency = self._validate_currency(
            trade_currency or self._trade_currency, "trade_currency"
        )
        if transaction_type is not None:
            transaction_type = str(transaction_type).upper()
            if transaction_type not in ("DEPOSIT", "WITHDRAW"):
                raise ValueError(
                    "transaction_type must be 'DEPOSIT' or 'WITHDRAW'"
                )
        if status is not None:
            status = str(status).title()
            if status not in ("Completed", "Processing", "Failed"):
                raise ValueError(
                    "status must be 'Completed', 'Processing' or 'Failed'"
                )
        if sort_by is not None:
            sort_by = str(sort_by).lower()
            if sort_by not in ("created_at", "updated_at"):
                raise ValueError("sort_by must be 'created_at' or 'updated_at'")
        if sort_order is not None:
            sort_order = str(sort_order).lower()
            if sort_order not in ("asc", "desc"):
                raise ValueError("sort_order must be 'asc' or 'desc'")
        return self._get(
            "/futures/transactions",
            params={
                "limit": limit,
                "trade_currency": trade_currency,
                "type": transaction_type,
                "status": status,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        )

    # ════════════════════════════════════════════════════════════════════
    #  WALLET
    # ════════════════════════════════════════════════════════════════════

    def get_wallet_funds(self, *, currency: Optional[str] = None):
        """Get spot wallet balances (total, rewards, invested, withdrawable).

        Args:
            currency: ``"USDT"`` or ``"INR"``. Defaults to the client's
                ``trade_currency``. Sent as ``currency`` (not
                ``trade_currency``).
        """
        currency = self._validate_currency(
            currency or self._trade_currency, "currency"
        )
        return self._get("/wallet/funds", params={"currency": currency})

    def transfer(
        self,
        from_wallet: str,
        to_wallet: str,
        amount: Numeric,
    ):
        """Transfer funds between wallets.

        Args:
            from_wallet: Source wallet — ``"SPOT"``, ``"FUTURES"``, or ``"HEDGE"``.
            to_wallet: Destination wallet — ``"SPOT"``, ``"FUTURES"``, or ``"HEDGE"``.
            amount: Transfer amount. Use a string for precision (e.g. ``"10.5"``).

        Only available on USDT clients: raises ``ValueError`` without sending
        a request when the client's ``trade_currency`` is ``"INR"``.
        """
        # INR uses POST /futures/transfers/inr, not supported here; see
        # https://docs.trade.mudrex.com.
        if self._trade_currency == "INR":
            raise ValueError("transfer() supports USDT only")
        return self._post(
            "/wallet/futures/transfer",
            body={
                "from_wallet_type": from_wallet,
                "to_wallet_type": to_wallet,
                "amount": amount,
            },
        )
