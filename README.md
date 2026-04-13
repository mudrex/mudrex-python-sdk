# Mudrex Python SDK

Official Python SDK for the [Mudrex HTTP APIs](https://docs.trade.mudrex.com). It currently supports only the **Trading API** (futures orders, positions, leverage, wallet, etc.) via the `TradeClient`.

## Installation

**mudrex-sdk** requires Python 3.9 or higher. Install from PyPI with pip:

```bash
pip install mudrex-sdk
```

Import the `mudrex` package in your code (the PyPI distribution name and the Python module name differ).

## Development

mudrex-python-sdk is actively developed, and new Mudrex API changes are reflected in the SDK as they are released. The SDK uses `requests` for HTTP calls. Anyone is welcome to fork the repository and contribute. If you have made substantial improvements, open a pull request and we will review it.

## Quick Start

```python
from mudrex import TradeClient

client = TradeClient(api_secret="your_api_secret")

# Place a market long order on BTCUSDT
resp = client.place_order(
    "BTCUSDT",
    leverage="10",
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

You can also ping anytime to verify connectivity and credentials:

```python
client.ping()  # no return value; raises on failure
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
    trade_currency="USDT",  # only USDT supported; this is the default
    timeout=10,              # request timeout in seconds
    max_retries=3,           # retries on network errors only
    log_requests=True,       # enable debug logging
)
```

**Numeric parameters** (quantity, leverage, prices, amount, margin, etc.) accept `str`, `int`, or `float`. The SDK does not convert types. The API expects string values for precision — **pass strings** (e.g. `quantity="0.001"`, `leverage="10"`) to avoid precision issues.

## API Reference

### Client

| Method | Description |
|---|---|
| `ping()` | Verify connectivity and API secret; raises on failure |

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
| `set_leverage("BTCUSDT", leverage="10")` | Set leverage for an asset |

### Orders

| Method | Description |
|---|---|
| `place_order("BTCUSDT", leverage="10", quantity="0.001", order_type="LONG", trigger_type="MARKET")` | Place a new order |
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

## Trade Currency

Only **USDT** is supported as trade currency. The client defaults to `trade_currency="USDT"`, so you can omit it:

```python
client = TradeClient(api_secret="...")  # uses USDT by default
# or explicitly:
client = TradeClient(api_secret="...", trade_currency="USDT")
```

## Using Symbols vs UUIDs

By default, all asset-related methods use trading symbols (e.g. `"BTCUSDT"`). If you need to use a raw asset UUID instead, pass `asset_id=`:

```python
client.get_leverage("BTCUSDT")                     # by symbol (recommended)
client.get_leverage(asset_id="550e8400-e29b-...")   # by UUID
```

## Response Format

All methods return a `MudrexResponse` (a dict with attribute access) or a list of them. The API returns **numeric fields as strings** (e.g. `quantity`, `leverage`, `entry_price`, `pnl`) to preserve precision; the SDK passes these through unchanged.

- **Object responses** (e.g. `place_order`, `get_leverage`): one `MudrexResponse` with the API fields.
- **List responses** (e.g. `get_orders`, `get_positions`, `get_position_history`): a list of `MudrexResponse` objects.
- **Scalar responses** (e.g. `close_position_partial` when the API returns `{"success": true, "data": true}`): a single `MudrexResponse` with a `result` field holding the value (e.g. `resp.result` is `True`).

```python
resp = client.get_leverage("BTCUSDT")
print(resp["leverage"])   # dict style
print(resp.leverage)     # attribute style (string, e.g. "10")
print(resp.margin_type)  # "ISOLATED"
```

```python
orders = client.get_orders()
for order in orders:
    print(order.id, order.order_type, order.quantity)  # list items use .id
```

**Pagination:** List endpoints (e.g. `get_orders`, `get_order_history`, `get_positions`) return the data array as sent by the API. Some endpoints may not include pagination metadata (e.g. `total_count`, `has_more`). When metadata is not available, paginate by using the **`limit`** and **`offset`** parameters yourself (e.g. `get_order_history(limit=20, offset=0)`, then `offset=20` for the next page).

## Error Handling

```python
from mudrex import TradeClient, MudrexAPIError, MudrexRequestError

client = TradeClient(api_secret="...")

try:
    client.place_order("BTCUSDT", leverage="10", quantity="0.001",
                       order_type="LONG", trigger_type="MARKET")
except MudrexAPIError as e:
    print(f"API error [{e.code}]: {e.message}")
    # Access the raw response if needed:
    # e.response.status_code, e.response.text
except MudrexRequestError as e:
    print(f"Network error: {e.message}")
    # e.original_error has the underlying requests exception
```

## Rate Limits

The Mudrex API enforces rate limits (2 req/s, 50/min, 1000/hr, 10000/day). This SDK does **not** throttle requests — it fires them immediately. If you exceed the limit, the API returns an error which is raised as `MudrexAPIError`. You are responsible for pacing your requests.

## Troubleshooting

### Precision for quantities and prices

Numeric parameters accept `str`, `int`, or `float`; the SDK does not convert them. The API uses strings for precision. **Pass strings** for quantity, leverage, prices, amount, and margin (e.g. `quantity="0.001"`, `leverage="10"`) to avoid float serialization issues.

### "Order value less than minimum required value" (400)

Each contract has a minimum notional (order value). Use `get_future(symbol)` to read the contract’s `min_order_value` (or equivalent) and ensure `quantity * price` meets it. Increase quantity or use a limit price that satisfies the minimum.

### Rate limit (429) and backoff

When you hit a rate limit, the API returns 429 and the SDK raises `MudrexAPIError` with message "API rate limit exceeded". The SDK does not retry or throttle. To avoid repeated 429s:

- Stay under **2 requests per second** when possible.
- On 429, catch the exception, wait a few seconds (or use a `Retry-After` header if the API sends one), then retry.
- For bulk operations, add a small delay between calls (e.g. `time.sleep(0.5)`).

### `id` vs `order_id` / `position_id`

- **`place_order`** returns a single object with **`order_id`**.
- **`get_orders()`** and **`get_order_history()`** return a **list** of orders; each item has **`id`** (not `order_id`).
- **`get_positions()`** returns a list of positions; each item has **`id`** (not `position_id`).

Use the same id for follow-up calls:

```python
resp = client.place_order(...)
oid = resp.order_id
client.cancel_order(oid)

orders = client.get_orders()
for o in orders:
    client.cancel_order(o.id)   # use .id on list items

positions = client.get_positions()
for p in positions:
    client.close_position(p.id)  # use .id on list items
```

So: **single-object responses** use `order_id` / similar; **list responses** use `id`. Use `order.id` and `position.id` when iterating.

## License

MIT
