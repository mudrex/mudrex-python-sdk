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

# Leverage is set per asset before placing (it is not part of place_order)
client.set_leverage("BTCUSDT", leverage="10")

# Place a market long order on BTCUSDT
resp = client.place_order(
    "BTCUSDT",
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
    trade_currency="USDT",  # "USDT" (default) or "INR"
    timeout=10,              # request timeout in seconds
    max_retries=3,           # retries on network errors; POSTs only when the request never left
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
| `place_order("BTCUSDT", quantity="0.001", order_type="LONG", trigger_type="MARKET", client_order_id=None)` | Place a new order (`POST /fapi/v2/futures/order`). Set leverage first with `set_leverage` |
| `get_orders(limit=20)` | Get open orders |
| `get_order_detail(order_id=None, client_order_id=None)` | Get a single order by UUID and/or client order id |
| `get_order(order_id)` | Deprecated. Use `get_order_detail` |
| `get_execution_report(order_id)` | Per-fill execution report for an order |
| `get_order_history(limit=20)` | Get order history |
| `amend_order(order_id, order_price="50000", quantity="0.002")` | Amend a limit order (docs require both `order_price` and `quantity`) |
| `cancel_order(order_id)` / `cancel_order(client_order_id="...")` | Cancel an open order by UUID or client order id |

### Positions

| Method | Description |
|---|---|
| `get_positions(limit=20)` | Get open positions |
| `get_position_history(limit=20)` | Get position history |
| `close_position(position_id)` | Close entire position; returns `order_id` (close order), `position_id`, `status` (`"CREATED"`: the close is asynchronous, so confirm with `get_order_detail`) and `message` |
| `close_position_partial(position_id, quantity="0.001", order_type="MARKET", client_order_id=None)` | Partially close; returns `order_id`, `position_id`, `quantity` |
| `reverse_position(position_id)` | Reverse a position |
| `place_risk_order(position_id, is_stoploss=True, stoploss_price="95000", stoploss_client_order_id=None)` | Add SL/TP |
| `amend_risk_order(position_id, is_stoploss=True, stoploss_order_id="...", stoploss_price="94000", trigger_type=None)` | Amend SL/TP (client id args only locate an existing leg) |
| `add_margin(position_id, margin="50")` | Add margin |
| `get_liquidation_price(position_id)` | Get liquidation price |

### Fees

| Method | Description |
|---|---|
| `get_fee_history(limit=10)` | Get trading fee history (`order_id` is absent on non-trade rows such as funding; use `.get("order_id")`) |
| `get_fee(fee_id)` | Get one fee record (`role`, `fills`) by id from fee history |

### Wallet

| Method | Description |
|---|---|
| `get_wallet_funds(currency=None)` | Get spot wallet balances (`"USDT"` or `"INR"`; defaults to the client's `trade_currency`) |
| `transfer("SPOT", "FUTURES", "100")` | Transfer between wallets (USDT clients only; raises `ValueError` on an INR client) |
| `get_transactions(limit=None, trade_currency=None, transaction_type=None, status=None, sort_by=None, sort_order=None)` | Futures wallet deposit/withdraw records (known backend issues: `trade_currency` is not currently applied; `status="Processing"` returns no rows) |

## Trade Currency

`USDT` and `INR` are supported. The client defaults to `trade_currency="USDT"`, so you can omit it:

```python
client = TradeClient(api_secret="...")  # uses USDT by default
client = TradeClient(api_secret="...", trade_currency="INR")
```

Any other value raises `ValueError` before a request is sent. `get_wallet_funds(currency=...)` defaults to the client's `trade_currency` and can be overridden per call. `transfer()` is USDT-only.

## Client Order IDs

`place_order` accepts an optional `client_order_id` (letters, digits, `-`, `_`; up to 64 characters). Use it to look up or cancel an order without storing the Mudrex UUID:

```python
client.set_leverage("BTCUSDT", leverage="10")
client.place_order("BTCUSDT", quantity="0.001", order_type="LONG",
                   trigger_type="MARKET", client_order_id="my-order-123")

client.get_order_detail(client_order_id="my-order-123")
client.cancel_order(client_order_id="my-order-123")
```

An invalid format raises `MudrexAPIError` (400 `invalid order identifier`); reusing an accepted id raises `MudrexAPIError` (409 `client order id already exists`). A place is never resent once it may have reached the API (e.g. after a read timeout); only connect failures are retried. If a response is lost, call `get_order_detail(client_order_id=...)` before placing again. `place_risk_order` takes `stoploss_client_order_id` / `takeprofit_client_order_id`, and `close_position_partial` takes `client_order_id` (applied to the generated close order).

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
- Scalar responses (e.g. `get_liquidation_price`, where `data` is a price string): the value itself, e.g. `"62888.3"`.
- Empty responses: when the API returns `data: null` the SDK returns `None`; `get_positions()` returns `[]` when there are no open positions.

Fields added in API v1.0.12: `close_position` returns `order_id` (the close order UUID) and `position_id` (the position UUID). `close_position_partial` returns `order_id`, `position_id` and `quantity`. Order responses, `get_positions()` and `get_position_history()` include `position_id`; position history rows also include `order_id`, and a history row's `id` is the row UUID, not the position UUID. `list_futures()` / `get_future()` include `previous_funding_interval` (Unix epoch seconds of the previous funding time).

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
    client.place_order("BTCUSDT", quantity="0.001",
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

The Mudrex API enforces tiered rate limits (see [Authentication and Rate Limits](https://docs.trade.mudrex.com/docs/authentication-rate-limits)):

| Tier | Limits |
|---|---|
| Default (trading) | 10 req/s, 500/min, 30000/hr |
| Core trading endpoints | Default limits plus 720000/day |
| Wallet | 2 req/s, 50/min, 3000/hr |

Limits use fixed clock windows. This SDK does **not** throttle requests. If you exceed a limit, the API returns HTTP 429. When `Retry-After` is 30 seconds or less, the SDK waits that long and retries, up to `max_retries`. Otherwise (longer, missing or invalid) it raises `MudrexAPIError` straight away; `e.retry_after` holds the header in seconds as sent (`None` if absent). You are responsible for pacing your requests.

## Troubleshooting

### Precision for quantities and prices

Numeric parameters accept `str`, `int`, or `float`; the SDK does not convert them. The API uses strings for precision. **Pass strings** for quantity, leverage, prices, amount, and margin (e.g. `quantity="0.001"`, `leverage="10"`) to avoid float serialization issues.

### "Order value less than minimum required value" (400)

Each contract has a minimum notional (order value). Use `get_future(symbol)` to read the contract’s `min_order_value` (or equivalent) and ensure `quantity * price` meets it. Increase quantity or use a limit price that satisfies the minimum.

### Rate limit (429) and backoff

When you hit a rate limit, the API returns 429 and the SDK waits and retries when `Retry-After` is 30 seconds or less (up to `max_retries`). If it is longer, missing or invalid, or retries run out, the SDK raises `MudrexAPIError` with message "API rate limit exceeded". The SDK does not throttle. To avoid repeated 429s:

- Stay within the tier limits above; wallet endpoints are much tighter than trading endpoints.
- If a 429 still reaches you, catch the exception, wait `e.retry_after` seconds (when set), then retry:

```python
try:
    client.get_wallet_funds()
except MudrexAPIError as e:
    if e.code == 429 and e.retry_after:
        time.sleep(e.retry_after)
```

- For bulk operations, add a small delay between calls.

### `id` vs `order_id` / `position_id`

- **`place_order`** returns a single object with **`order_id`**.
- **`get_orders()`** and **`get_order_history()`** return a **list** of orders; each item has **`id`** (not `order_id`).
- **`get_positions()`** returns a list of positions; each item has **`id`** and, as of API v1.0.12, **`position_id`** (same value).
- **`get_position_history()`** rows: **`id`** is the history-row UUID, not the position UUID. Use the row's **`position_id`** for the position and **`order_id`** for the order.

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

## Migrating

0.2.0 is a breaking release. Null and scalar API data is now returned unwrapped (no more `resp.result`), and `place_order` uses the v2 path without `leverage`.

See [CHANGELOG.md](CHANGELOG.md) for changed signatures (old and new forms), including the deprecation of `leverage` on `place_order` (ignored, `FutureWarning`, removed in 0.3.0) and the v1.0.12 close-response shapes.

## License

MIT
