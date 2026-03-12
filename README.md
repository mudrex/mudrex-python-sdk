# Mudrex Python SDK

Official Python SDK for the [Mudrex Futures Trading API](https://docs.trade.mudrex.com).

## Installation

```bash
pip install mudrex
```

Or install from source:

```bash
git clone https://github.com/mudrex/mudrex-python-sdk.git
cd mudrex-python-sdk
pip install .
```

## Quick Start

```python
from mudrex import TradeClient

client = TradeClient(api_secret="your_api_secret")

# Place a market long order on BTCUSDT
resp = client.place_order(
    "BTCUSDT",
    leverage=10,
    quantity="0.001",
    order_type="LONG",
    trigger_type="MARKET",
)
print(resp.order_id)
```

The client pings the API on creation — a bad secret or unreachable server raises immediately:

```python
from mudrex import TradeClient, MudrexAPIError

try:
    client = TradeClient(api_secret="wrong_secret")
except MudrexAPIError as e:
    print(e)  # [401] Invalid Authentication
```

You can also set the API secret via environment variable:

```bash
export MUDREX_API_SECRET="your_api_secret"
```

```python
client = TradeClient()  # picks up MUDREX_API_SECRET automatically
```

## Configuration

```python
client = TradeClient(
    api_secret="...",
    trade_currency="USDT",  # locked for this client's lifetime
    timeout=15,              # request timeout in seconds
    max_retries=3,           # retries on network errors only
    log_requests=True,       # enable debug logging
)
```

## API Reference

### Futures / Assets

| Method | Description |
|---|---|
| `list_futures(limit=10, offset=0, sort=None, order=None)` | List available futures contracts |
| `get_future("BTCUSDT")` | Get a single futures contract |
| `get_available_funds(source=None)` | Get available trading funds |

### Leverage

| Method | Description |
|---|---|
| `get_leverage("BTCUSDT")` | Get current leverage and margin type |
| `set_leverage("BTCUSDT", leverage=10)` | Set leverage for an asset |

### Orders

| Method | Description |
|---|---|
| `place_order("BTCUSDT", leverage=10, quantity="0.001", order_type="LONG", trigger_type="MARKET")` | Place a new order |
| `get_orders(limit=20)` | Get open orders |
| `get_order(order_id)` | Get a single order |
| `get_order_history(limit=20)` | Get order history |
| `amend_order(order_id, order_price="50000", stoploss_order_id="...", stoploss_price="95000")` | Amend a limit order |
| `cancel_order(order_id)` | Cancel an open order |

### Positions

| Method | Description |
|---|---|
| `get_positions(limit=20)` | Get open positions |
| `get_position_history(limit=20)` | Get position history |
| `close_position(position_id)` | Close entire position |
| `close_position_partial(position_id, quantity="0.001", order_type="SHORT")` | Partially close |
| `reverse_position(position_id)` | Reverse a position |
| `place_risk_order(position_id, is_stoploss=True, stoploss_price="95000")` | Add SL/TP |
| `amend_risk_order(position_id, is_stoploss=True, stoploss_order_id="...", stoploss_price="94000")` | Amend SL/TP |
| `add_margin(position_id, margin="50")` | Add margin |
| `get_liquidation_price(position_id)` | Get liquidation price |

### Fees

| Method | Description |
|---|---|
| `get_fee_history(limit=10)` | Get trading fee history |

### Wallet

| Method | Description |
|---|---|
| `get_wallet_funds()` | Get wallet balances |
| `transfer("SPOT", "FUTURES", "100")` | Transfer between wallets |

## Using Symbols vs UUIDs

By default, all asset-related methods use trading symbols (e.g. `"BTCUSDT"`). If you need to use a raw asset UUID instead, pass `asset_id=`:

```python
client.get_leverage("BTCUSDT")                     # by symbol (recommended)
client.get_leverage(asset_id="550e8400-e29b-...")   # by UUID
```

## Trade Currency

Trade currency is locked at client creation — every request from that client uses the same currency. This prevents accidental currency mismatches between orders, positions, and fund queries.

```python
usdt_client = TradeClient(api_secret="...", trade_currency="USDT")
inr_client  = TradeClient(api_secret="...", trade_currency="INR")
```

## Error Handling

```python
from mudrex import TradeClient, MudrexAPIError, MudrexRequestError

client = TradeClient(api_secret="...")

try:
    client.place_order("BTCUSDT", leverage=10, quantity="0.001",
                       order_type="LONG", trigger_type="MARKET")
except MudrexAPIError as e:
    print(f"API error [{e.code}]: {e.message}")
    # Access the raw response if needed:
    # e.response.status_code, e.response.text
except MudrexRequestError as e:
    print(f"Network error: {e.message}")
    # e.original_error has the underlying requests exception
```

## Response Format

All methods return a `MudrexResponse` (a dict with attribute access):

```python
resp = client.get_leverage("BTCUSDT")
print(resp["leverage"])   # dict style
print(resp.leverage)      # attribute style
print(resp.margin_type)   # "ISOLATED"
```

List endpoints return a list of `MudrexResponse` objects:

```python
orders = client.get_orders()
for order in orders:
    print(order.order_id, order.order_type, order.quantity)
```

## Rate Limits

The Mudrex API enforces rate limits (2 req/s, 50/min, 1000/hr, 10000/day). This SDK does **not** throttle requests — it fires them immediately. If you exceed the limit, the API returns an error which is raised as `MudrexAPIError`. You are responsible for pacing your requests.

## License

MIT
