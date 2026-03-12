from typing import Optional, Union

from ._http import _HTTPClient

Numeric = Union[str, int, float]


class TradeClient(_HTTPClient):
    """Mudrex Futures Trading API client.

    All FAPI endpoints are exposed as flat methods on this class.
    Symbol-first: pass a trading symbol (e.g. ``"BTCUSDT"``) as the first
    argument wherever an asset identifier is needed.  For the rare case of
    using a raw asset UUID, pass ``asset_id=`` instead.

    Args:
        api_secret: Your Mudrex API secret.
            Falls back to the ``MUDREX_API_SECRET`` environment variable.
        trade_currency: Trade currency locked for the lifetime of this client
            (default ``"USDT"``).  To trade in a different currency, create a
            new ``TradeClient`` instance with the desired currency.
        timeout: Request timeout in seconds (default ``10``).
        max_retries: Retries on transient network errors (default ``3``).
        log_requests: Emit debug logs for every request/response (default ``False``).

    Example::

        from mudrex import TradeClient

        client = TradeClient(api_secret="your_secret")
        client.place_order(
            "BTCUSDT",
            leverage=10,
            quantity="0.001",
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
        self._trade_currency = trade_currency
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
        return self._get(f"/futures/{identifier}", params=params)

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
        return self._get(f"/futures/{identifier}/leverage", params=params)

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
            f"/futures/{identifier}/leverage",
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
        leverage: Numeric,
        quantity: Numeric,
        order_type: str,
        trigger_type: str,
        order_price: Optional[Numeric] = None,
        is_stoploss: bool = False,
        is_takeprofit: bool = False,
        stoploss_price: Optional[Numeric] = None,
        takeprofit_price: Optional[Numeric] = None,
        reduce_only: bool = False,
    ):
        """Place a new futures order.

        Args:
            symbol: Trading symbol (e.g. ``"BTCUSDT"``).
            asset_id: Asset UUID (alternative to symbol).
            leverage: Leverage value.
            quantity: Order quantity.
            order_type: ``"LONG"`` or ``"SHORT"``.
            trigger_type: ``"MARKET"`` or ``"LIMIT"``.
            order_price: Limit price (required for ``LIMIT`` orders).
            is_stoploss: Attach a stop-loss to this order.
            is_takeprofit: Attach a take-profit to this order.
            stoploss_price: Stop-loss trigger price (required when ``is_stoploss=True``).
            takeprofit_price: Take-profit trigger price (required when ``is_takeprofit=True``).
            reduce_only: If ``True``, order can only reduce/close an existing position.
        """
        identifier, params = self._resolve_asset(symbol, asset_id)
        return self._post(
            f"/futures/{identifier}/order",
            params=params,
            body={
                "leverage": leverage,
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
            },
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

        Args:
            order_id: Order UUID.
        """
        return self._get(f"/futures/orders/{order_id}")

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
        is_stoploss: Optional[bool] = None,
        is_takeprofit: Optional[bool] = None,
        stoploss_price: Optional[Numeric] = None,
        takeprofit_price: Optional[Numeric] = None,
        stoploss_order_id: Optional[str] = None,
        takeprofit_order_id: Optional[str] = None,
    ):
        """Amend an existing limit order.

        Args:
            order_id: Order UUID.
            order_price: New limit price.
            is_stoploss: Set/update stop-loss.
            is_takeprofit: Set/update take-profit.
            stoploss_price: New stop-loss price.
            takeprofit_price: New take-profit price.
            stoploss_order_id: Existing stop-loss order UUID to amend.
            takeprofit_order_id: Existing take-profit order UUID to amend.
        """
        return self._patch(
            f"/futures/orders/{order_id}",
            body={
                "order_price": order_price,
                "is_stoploss": is_stoploss,
                "is_takeprofit": is_takeprofit,
                "stoploss_price": stoploss_price,
                "takeprofit_price": takeprofit_price,
                "stoploss_order_id": stoploss_order_id,
                "takeprofit_order_id": takeprofit_order_id,
            },
        )

    def cancel_order(self, order_id: str):
        """Cancel an open order.

        Args:
            order_id: Order UUID.
        """
        return self._delete(f"/futures/orders/{order_id}")

    # ════════════════════════════════════════════════════════════════════
    #  POSITIONS
    # ════════════════════════════════════════════════════════════════════

    def get_positions(self, *, limit: int = 20, offset: Optional[int] = None):
        """Get open positions.

        Args:
            limit: Number of results (default 20).
            offset: Offset timestamp in milliseconds for pagination.
        """
        return self._get(
            "/futures/positions",
            params={
                "limit": limit,
                "offset": offset,
                "trade_currency": self._trade_currency,
            },
        )

    def get_position_history(self, *, limit: int = 20, offset: Optional[int] = None):
        """Get closed/liquidated position history.

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
        """
        return self._post(f"/futures/positions/{position_id}/close")

    def close_position_partial(
        self,
        position_id: str,
        *,
        quantity: Numeric,
        order_type: str,
        limit_price: Optional[Numeric] = None,
    ):
        """Partially close a position.

        Args:
            position_id: Position UUID.
            quantity: Quantity to close.
            order_type: ``"LONG"`` or ``"SHORT"`` (opposite of position direction).
            limit_price: Limit price for a limit close (optional).
        """
        return self._post(
            f"/futures/positions/{position_id}/close/partial",
            body={
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": limit_price,
            },
        )

    def reverse_position(self, position_id: str):
        """Reverse a position (close current and open opposite).

        Args:
            position_id: Position UUID.
        """
        return self._post(f"/futures/positions/{position_id}/reverse")

    def place_risk_order(
        self,
        position_id: str,
        *,
        is_stoploss: bool = False,
        is_takeprofit: bool = False,
        stoploss_price: Optional[Numeric] = None,
        takeprofit_price: Optional[Numeric] = None,
    ):
        """Place stop-loss and/or take-profit on a position.

        At least one of ``is_stoploss`` or ``is_takeprofit`` must be ``True``.

        Args:
            position_id: Position UUID.
            is_stoploss: Place a stop-loss order.
            is_takeprofit: Place a take-profit order.
            stoploss_price: Trigger price (required when ``is_stoploss=True``).
            takeprofit_price: Trigger price (required when ``is_takeprofit=True``).
        """
        return self._post(
            f"/futures/positions/{position_id}/riskorder",
            body={
                "is_stoploss": is_stoploss,
                "is_takeprofit": is_takeprofit,
                "stoploss_price": stoploss_price,
                "takeprofit_price": takeprofit_price,
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
    ):
        """Amend existing risk orders (stop-loss / take-profit) on a position.

        Args:
            position_id: Position UUID.
            is_stoploss: Amend the stop-loss order.
            is_takeprofit: Amend the take-profit order.
            stoploss_order_id: Existing stop-loss order UUID.
            takeprofit_order_id: Existing take-profit order UUID.
            stoploss_price: New stop-loss trigger price.
            takeprofit_price: New take-profit trigger price.
        """
        return self._patch(
            f"/futures/positions/{position_id}/riskorder",
            body={
                "is_stoploss": is_stoploss,
                "is_takeprofit": is_takeprofit,
                "stoploss_order_id": stoploss_order_id,
                "takeprofit_order_id": takeprofit_order_id,
                "stoploss_price": stoploss_price,
                "takeprofit_price": takeprofit_price,
            },
        )

    def add_margin(self, position_id: str, *, margin: Numeric):
        """Add margin to an open position.

        Args:
            position_id: Position UUID.
            margin: Amount of margin to add.
        """
        return self._post(
            f"/futures/positions/{position_id}/add-margin",
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
            f"/futures/positions/{position_id}/liq-price",
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

    # ════════════════════════════════════════════════════════════════════
    #  WALLET
    # ════════════════════════════════════════════════════════════════════

    def get_wallet_funds(self):
        """Get spot wallet balances (total, rewards, invested, withdrawable)."""
        return self._get("/wallet/funds")

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
            amount: Transfer amount. Use a string for exact precision
                (e.g. ``"10.5"`` instead of ``10.5``).
        """
        return self._post(
            "/wallet/futures/transfer",
            body={
                "from_wallet_type": from_wallet,
                "to_wallet_type": to_wallet,
                "amount": amount,
            },
        )
