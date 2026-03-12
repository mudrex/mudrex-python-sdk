"""Tests for every TradeClient method — verifies HTTP method, path, params, and body."""

import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from mudrex import TradeClient
from mudrex._types import MudrexResponse


def _make_response(status_code=200, body=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = json.dumps(body) if body else ""
    resp.json.return_value = body
    return resp


SUCCESS_DICT = {"success": True, "data": {"result": "ok"}}
SUCCESS_LIST = {"success": True, "data": [{"id": "1"}, {"id": "2"}]}
SUCCESS_SCALAR = {"success": True, "data": "62888.3"}


class _ClientTestBase(unittest.TestCase):
    """Base class that creates a client and captures requests."""

    def setUp(self):
        with patch.object(TradeClient, "_ping"):
            self.client = TradeClient(api_secret="test_secret", trade_currency="USDT")
        self.mock_request = MagicMock(
            return_value=_make_response(200, SUCCESS_DICT)
        )
        self._patcher = patch.object(
            self.client._session, "request", self.mock_request
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def _set_response(self, body):
        self.mock_request.return_value = _make_response(200, body)

    def _assert_called_with(self, method, path_contains, params=None, body=None):
        self.mock_request.assert_called_once()
        kwargs = self.mock_request.call_args[1]
        self.assertEqual(kwargs["method"], method)
        self.assertIn(path_contains, kwargs["url"])
        if params is not None:
            self.assertEqual(kwargs["params"], params)
        if body is not None:
            self.assertEqual(kwargs["json"], body)


# ═══════════════════════════════════════════════════
#  CLIENT INIT & HELPERS
# ═══════════════════════════════════════════════════


class TestClientInit(unittest.TestCase):

    @patch.object(TradeClient, "_ping")
    def test_default_trade_currency(self, _):
        c = TradeClient(api_secret="s")
        self.assertEqual(c._trade_currency, "USDT")

    @patch.object(TradeClient, "_ping")
    def test_custom_trade_currency(self, _):
        c = TradeClient(api_secret="s", trade_currency="INR")
        self.assertEqual(c._trade_currency, "INR")

    @patch.object(TradeClient, "_ping")
    def test_ping_called_on_init(self, mock_ping):
        TradeClient(api_secret="s")
        mock_ping.assert_called_once()


class TestResolveAsset(unittest.TestCase):

    def test_symbol(self):
        ident, params = TradeClient._resolve_asset(symbol="BTCUSDT")
        self.assertEqual(ident, "BTCUSDT")
        self.assertEqual(params, {"is_symbol": "true"})

    def test_asset_id(self):
        ident, params = TradeClient._resolve_asset(asset_id="uuid-123")
        self.assertEqual(ident, "uuid-123")
        self.assertEqual(params, {})

    def test_both_raises(self):
        with self.assertRaises(ValueError):
            TradeClient._resolve_asset(symbol="BTC", asset_id="uuid")

    def test_neither_raises(self):
        with self.assertRaises(ValueError):
            TradeClient._resolve_asset()


# ═══════════════════════════════════════════════════
#  FUTURES / ASSETS
# ═══════════════════════════════════════════════════


class TestListFutures(_ClientTestBase):

    def test_default_params(self):
        self._set_response(SUCCESS_LIST)
        self.client.list_futures()
        self._assert_called_with(
            "GET", "/futures",
            params={"limit": 10, "offset": 0},
        )

    def test_custom_params(self):
        self._set_response(SUCCESS_LIST)
        self.client.list_futures(limit=5, offset=10, sort="volume", order="desc")
        self._assert_called_with(
            "GET", "/futures",
            params={"limit": 5, "offset": 10, "sort": "volume", "order": "desc"},
        )

    def test_returns_list(self):
        self._set_response(SUCCESS_LIST)
        result = self.client.list_futures()
        self.assertIsInstance(result, list)


class TestGetFuture(_ClientTestBase):

    def test_by_symbol(self):
        self.client.get_future("BTCUSDT")
        self._assert_called_with(
            "GET", "/futures/BTCUSDT",
            params={"is_symbol": "true"},
        )

    def test_by_asset_id(self):
        self.client.get_future(asset_id="uuid-abc")
        self._assert_called_with("GET", "/futures/uuid-abc", params=None)


class TestGetAvailableFunds(_ClientTestBase):

    def test_no_source(self):
        self.client.get_available_funds()
        self._assert_called_with(
            "GET", "/futures/funds",
            params={"trade_currency": "USDT"},
        )

    def test_with_source(self):
        self.client.get_available_funds(source="transfer")
        self._assert_called_with(
            "GET", "/futures/funds",
            params={"source": "transfer", "trade_currency": "USDT"},
        )


# ═══════════════════════════════════════════════════
#  LEVERAGE
# ═══════════════════════════════════════════════════


class TestGetLeverage(_ClientTestBase):

    def test_by_symbol(self):
        self.client.get_leverage("ETHUSDT")
        self._assert_called_with(
            "GET", "/futures/ETHUSDT/leverage",
            params={"is_symbol": "true", "trade_currency": "USDT"},
        )

    def test_by_asset_id(self):
        self.client.get_leverage(asset_id="uuid-eth")
        self._assert_called_with(
            "GET", "/futures/uuid-eth/leverage",
            params={"trade_currency": "USDT"},
        )


class TestSetLeverage(_ClientTestBase):

    def test_basic(self):
        self.client.set_leverage("BTCUSDT", leverage=20)
        self._assert_called_with(
            "POST", "/futures/BTCUSDT/leverage",
            params={"is_symbol": "true"},
            body={
                "leverage": 20,
                "margin_type": "ISOLATED",
                "trade_currency": "USDT",
            },
        )

    def test_custom_margin_type(self):
        self.client.set_leverage("BTCUSDT", leverage=5, margin_type="CROSS")
        kwargs = self.mock_request.call_args[1]
        self.assertEqual(kwargs["json"]["margin_type"], "CROSS")


# ═══════════════════════════════════════════════════
#  ORDERS
# ═══════════════════════════════════════════════════


class TestPlaceOrder(_ClientTestBase):

    def test_market_order(self):
        self.client.place_order(
            "BTCUSDT",
            leverage=10,
            quantity="0.001",
            order_type="LONG",
            trigger_type="MARKET",
        )
        self._assert_called_with(
            "POST", "/futures/BTCUSDT/order",
            params={"is_symbol": "true"},
            body={
                "leverage": 10,
                "quantity": "0.001",
                "order_type": "LONG",
                "trigger_type": "MARKET",
                "is_stoploss": False,
                "is_takeprofit": False,
                "reduce_only": False,
                "trade_currency": "USDT",
            },
        )

    def test_limit_order_with_sl_tp(self):
        self.client.place_order(
            "ETHUSDT",
            leverage=5,
            quantity="0.1",
            order_type="SHORT",
            trigger_type="LIMIT",
            order_price="3000",
            is_stoploss=True,
            stoploss_price="3100",
            is_takeprofit=True,
            takeprofit_price="2800",
        )
        kwargs = self.mock_request.call_args[1]
        body = kwargs["json"]
        self.assertEqual(body["order_price"], "3000")
        self.assertTrue(body["is_stoploss"])
        self.assertEqual(body["stoploss_price"], "3100")
        self.assertTrue(body["is_takeprofit"])
        self.assertEqual(body["takeprofit_price"], "2800")

    def test_by_asset_id(self):
        self.client.place_order(
            asset_id="uuid-btc",
            leverage=10,
            quantity="0.001",
            order_type="LONG",
            trigger_type="MARKET",
        )
        kwargs = self.mock_request.call_args[1]
        self.assertIn("/futures/uuid-btc/order", kwargs["url"])
        self.assertIsNone(kwargs["params"])

    def test_reduce_only(self):
        self.client.place_order(
            "BTCUSDT",
            leverage=10,
            quantity="0.001",
            order_type="SHORT",
            trigger_type="MARKET",
            reduce_only=True,
        )
        kwargs = self.mock_request.call_args[1]
        self.assertTrue(kwargs["json"]["reduce_only"])

    def test_inr_client(self):
        with patch.object(TradeClient, "_ping"):
            client = TradeClient(api_secret="s", trade_currency="INR")
        with patch.object(client._session, "request", self.mock_request):
            client.place_order(
                "BTCUSDT",
                leverage=10,
                quantity="0.001",
                order_type="LONG",
                trigger_type="MARKET",
            )
        kwargs = self.mock_request.call_args[1]
        self.assertEqual(kwargs["json"]["trade_currency"], "INR")


class TestGetOrders(_ClientTestBase):

    def test_defaults(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_orders()
        self._assert_called_with(
            "GET", "/futures/orders",
            params={"limit": 20, "trade_currency": "USDT"},
        )

    def test_with_offset(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_orders(limit=5, offset=1234567890)
        self._assert_called_with(
            "GET", "/futures/orders",
            params={"limit": 5, "offset": 1234567890, "trade_currency": "USDT"},
        )


class TestGetOrder(_ClientTestBase):

    def test_basic(self):
        self.client.get_order("order-uuid-123")
        self._assert_called_with("GET", "/futures/orders/order-uuid-123")


class TestGetOrderHistory(_ClientTestBase):

    def test_defaults(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_order_history()
        self._assert_called_with(
            "GET", "/futures/orders/history",
            params={"limit": 20, "trade_currency": "USDT"},
        )


class TestAmendOrder(_ClientTestBase):

    def test_amend_price(self):
        self.client.amend_order("oid-1", order_price="50000")
        self._assert_called_with(
            "PATCH", "/futures/orders/oid-1",
            body={"order_price": "50000"},
        )

    def test_amend_with_sl_tp_ids(self):
        self.client.amend_order(
            "oid-1",
            order_price="50000",
            is_stoploss=True,
            stoploss_price="48000",
            stoploss_order_id="sl-uuid",
            is_takeprofit=True,
            takeprofit_price="55000",
            takeprofit_order_id="tp-uuid",
        )
        kwargs = self.mock_request.call_args[1]
        body = kwargs["json"]
        self.assertEqual(body["stoploss_order_id"], "sl-uuid")
        self.assertEqual(body["takeprofit_order_id"], "tp-uuid")
        self.assertTrue(body["is_stoploss"])
        self.assertTrue(body["is_takeprofit"])

    def test_none_fields_stripped(self):
        self.client.amend_order("oid-1", order_price="50000")
        kwargs = self.mock_request.call_args[1]
        body = kwargs["json"]
        self.assertNotIn("stoploss_price", body)
        self.assertNotIn("takeprofit_price", body)
        self.assertNotIn("stoploss_order_id", body)


class TestCancelOrder(_ClientTestBase):

    def test_basic(self):
        self.client.cancel_order("oid-1")
        self._assert_called_with("DELETE", "/futures/orders/oid-1")


# ═══════════════════════════════════════════════════
#  POSITIONS
# ═══════════════════════════════════════════════════


class TestGetPositions(_ClientTestBase):

    def test_defaults(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_positions()
        self._assert_called_with(
            "GET", "/futures/positions",
            params={"limit": 20, "trade_currency": "USDT"},
        )

    def test_with_offset(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_positions(limit=5, offset=9999)
        self._assert_called_with(
            "GET", "/futures/positions",
            params={"limit": 5, "offset": 9999, "trade_currency": "USDT"},
        )


class TestGetPositionHistory(_ClientTestBase):

    def test_defaults(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_position_history()
        self._assert_called_with(
            "GET", "/futures/positions/history",
            params={"limit": 20, "trade_currency": "USDT"},
        )


class TestClosePosition(_ClientTestBase):

    def test_basic(self):
        self.client.close_position("pid-1")
        self._assert_called_with("POST", "/futures/positions/pid-1/close")


class TestClosePositionPartial(_ClientTestBase):

    def test_market_close(self):
        self.client.close_position_partial(
            "pid-1", quantity="0.001", order_type="SHORT"
        )
        self._assert_called_with(
            "POST", "/futures/positions/pid-1/close/partial",
            body={"quantity": "0.001", "order_type": "SHORT"},
        )

    def test_limit_close(self):
        self.client.close_position_partial(
            "pid-1", quantity="0.001", order_type="SHORT", limit_price="70000"
        )
        kwargs = self.mock_request.call_args[1]
        self.assertEqual(kwargs["json"]["limit_price"], "70000")


class TestReversePosition(_ClientTestBase):

    def test_basic(self):
        self.client.reverse_position("pid-1")
        self._assert_called_with("POST", "/futures/positions/pid-1/reverse")


class TestPlaceRiskOrder(_ClientTestBase):

    def test_stoploss_only(self):
        self.client.place_risk_order(
            "pid-1", is_stoploss=True, stoploss_price="65000"
        )
        self._assert_called_with(
            "POST", "/futures/positions/pid-1/riskorder",
            body={
                "is_stoploss": True,
                "is_takeprofit": False,
                "stoploss_price": "65000",
            },
        )

    def test_both_sl_tp(self):
        self.client.place_risk_order(
            "pid-1",
            is_stoploss=True,
            stoploss_price="65000",
            is_takeprofit=True,
            takeprofit_price="75000",
        )
        kwargs = self.mock_request.call_args[1]
        body = kwargs["json"]
        self.assertTrue(body["is_stoploss"])
        self.assertTrue(body["is_takeprofit"])
        self.assertEqual(body["stoploss_price"], "65000")
        self.assertEqual(body["takeprofit_price"], "75000")


class TestAmendRiskOrder(_ClientTestBase):

    def test_amend_sl(self):
        self.client.amend_risk_order(
            "pid-1",
            is_stoploss=True,
            stoploss_order_id="sl-uuid",
            stoploss_price="64000",
        )
        kwargs = self.mock_request.call_args[1]
        body = kwargs["json"]
        self.assertTrue(body["is_stoploss"])
        self.assertEqual(body["stoploss_order_id"], "sl-uuid")
        self.assertEqual(body["stoploss_price"], "64000")

    def test_amend_both(self):
        self.client.amend_risk_order(
            "pid-1",
            is_stoploss=True,
            stoploss_order_id="sl-uuid",
            stoploss_price="64000",
            is_takeprofit=True,
            takeprofit_order_id="tp-uuid",
            takeprofit_price="76000",
        )
        kwargs = self.mock_request.call_args[1]
        body = kwargs["json"]
        self.assertEqual(body["takeprofit_order_id"], "tp-uuid")


class TestAddMargin(_ClientTestBase):

    def test_basic(self):
        self.client.add_margin("pid-1", margin="50")
        self._assert_called_with(
            "POST", "/futures/positions/pid-1/add-margin",
            body={"margin": "50"},
        )

    def test_numeric_margin(self):
        self.client.add_margin("pid-1", margin=100)
        kwargs = self.mock_request.call_args[1]
        self.assertEqual(kwargs["json"]["margin"], 100)


class TestGetLiquidationPrice(_ClientTestBase):

    def test_basic(self):
        self._set_response(SUCCESS_SCALAR)
        result = self.client.get_liquidation_price("pid-1")
        self._assert_called_with(
            "GET", "/futures/positions/pid-1/liq-price",
            params={"trade_currency": "USDT"},
        )
        self.assertEqual(result, "62888.3")

    def test_with_ext_margin(self):
        self._set_response(SUCCESS_SCALAR)
        self.client.get_liquidation_price("pid-1", ext_margin="10")
        self._assert_called_with(
            "GET", "/futures/positions/pid-1/liq-price",
            params={"ext_margin": "10", "trade_currency": "USDT"},
        )


# ═══════════════════════════════════════════════════
#  FEES
# ═══════════════════════════════════════════════════


class TestGetFeeHistory(_ClientTestBase):

    def test_defaults(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_fee_history()
        self._assert_called_with(
            "GET", "/futures/fee/history",
            params={"limit": 10, "trade_currency": "USDT"},
        )

    def test_custom_params(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_fee_history(limit=50, offset=1234)
        self._assert_called_with(
            "GET", "/futures/fee/history",
            params={"limit": 50, "offset": 1234, "trade_currency": "USDT"},
        )


# ═══════════════════════════════════════════════════
#  WALLET
# ═══════════════════════════════════════════════════


class TestGetWalletFunds(_ClientTestBase):

    def test_basic(self):
        self.client.get_wallet_funds()
        self._assert_called_with("GET", "/wallet/funds")


class TestTransfer(_ClientTestBase):

    def test_spot_to_futures(self):
        self.client.transfer("SPOT", "FUTURES", "100")
        self._assert_called_with(
            "POST", "/wallet/futures/transfer",
            body={
                "from_wallet_type": "SPOT",
                "to_wallet_type": "FUTURES",
                "amount": "100",
            },
        )

    def test_futures_to_hedge(self):
        self.client.transfer("FUTURES", "HEDGE", 50.5)
        kwargs = self.mock_request.call_args[1]
        body = kwargs["json"]
        self.assertEqual(body["from_wallet_type"], "FUTURES")
        self.assertEqual(body["to_wallet_type"], "HEDGE")
        self.assertEqual(body["amount"], 50.5)


# ═══════════════════════════════════════════════════
#  TRADE CURRENCY LOCK
# ═══════════════════════════════════════════════════


class TestTradeCurrencyLock(_ClientTestBase):

    def test_usdt_client_sends_usdt(self):
        self._set_response(SUCCESS_LIST)
        self.client.get_orders()
        kwargs = self.mock_request.call_args[1]
        self.assertEqual(kwargs["params"]["trade_currency"], "USDT")

    def test_inr_client_sends_inr(self):
        with patch.object(TradeClient, "_ping"):
            inr_client = TradeClient(api_secret="s", trade_currency="INR")
        with patch.object(inr_client._session, "request", self.mock_request):
            self._set_response(SUCCESS_LIST)
            inr_client.get_orders()
        kwargs = self.mock_request.call_args[1]
        self.assertEqual(kwargs["params"]["trade_currency"], "INR")

    def test_all_currency_endpoints_use_client_currency(self):
        """Every method that sends trade_currency should use the client's value."""
        with patch.object(TradeClient, "_ping"):
            inr_client = TradeClient(api_secret="s", trade_currency="INR")

        methods = [
            lambda c: c.get_available_funds(),
            lambda c: c.get_leverage("BTCUSDT"),
            lambda c: c.set_leverage("BTCUSDT", leverage=10),
            lambda c: c.place_order("BTCUSDT", leverage=10, quantity="0.001",
                                    order_type="LONG", trigger_type="MARKET"),
            lambda c: c.get_orders(),
            lambda c: c.get_order_history(),
            lambda c: c.get_positions(),
            lambda c: c.get_position_history(),
            lambda c: c.get_fee_history(),
            lambda c: c.get_liquidation_price("pid"),
        ]

        for method_fn in methods:
            self.mock_request.reset_mock()
            with patch.object(inr_client._session, "request", self.mock_request):
                method_fn(inr_client)
            kwargs = self.mock_request.call_args[1]
            sent_tc = (kwargs.get("params") or {}).get("trade_currency") or \
                      (kwargs.get("json") or {}).get("trade_currency")
            self.assertEqual(
                sent_tc, "INR",
                f"Expected INR but got {sent_tc} for {kwargs['url']}"
            )


if __name__ == "__main__":
    unittest.main()
