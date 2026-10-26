# Changelog

## 0.2.0 (breaking)

This release brings the SDK in line with the Futures API docs v1.0.12 and adds INR support. It changes some call forms and response shapes. Read "Changed signatures" and "Response shape changes" before upgrading. Code that reads `resp.result`, or that passes `leverage` to `place_order`, needs to change.

Tag this release as `v0.2.0`, not as a patch version.

Removed or invalid call forms raise `ValueError` and send no request. Two forms still work and emit a `FutureWarning`: `get_order` and the `leverage` argument of `place_order`.

### Changed signatures

| Area | Before | Now |
|---|---|---|
| Client currency | `TradeClient(trade_currency="INR")` raised `ValueError` (USDT only) | `trade_currency` accepts `"USDT"` or `"INR"`. Other values raise `ValueError` |
| Place order | `place_order("BTCUSDT", leverage="10", quantity=..., ...)` called `POST /fapi/v1/futures/{symbol}/order` | Call `set_leverage("BTCUSDT", leverage="10")` first, then `place_order("BTCUSDT", quantity=..., ...)`, which calls `POST /fapi/v2/futures/order`. Passing `leverage=` is ignored (not sent) and emits a `FutureWarning`. It will be removed in 0.3.0 |
| Client order id on place | Not supported | `place_order(..., client_order_id="...")` |
| Cancel | `cancel_order(order_id)` | `cancel_order(order_id)` or `cancel_order(client_order_id="...")`. Pass exactly one |
| Amend | `amend_order(order_id, order_price=...)` | `amend_order(order_id, order_price=..., quantity=...)`. The docs require both. The API response is returned unchanged |
| Spot funds | `get_wallet_funds()` | `get_wallet_funds(currency="USDT" \| "INR")`. Defaults to the client's `trade_currency` |
| Risk orders | No client ids | `place_risk_order(..., stoploss_client_order_id=, takeprofit_client_order_id=)` and `amend_risk_order(..., stoploss_client_order_id=, takeprofit_client_order_id=, trigger_type="MARKET" \| "LIMIT")`. On amend, the client ids only locate an existing order |
| Partial close | `close_position_partial(pid, quantity=, order_type=)`. The docstring said `LONG` or `SHORT` | Adds `client_order_id=`. `order_type` is `"MARKET"` or `"LIMIT"` |
| Transfer | `transfer()` accepted any client | `transfer()` raises `ValueError("transfer() supports USDT only")` on an INR client, before any request |

### Added

- `get_order_detail(order_id=None, client_order_id=None)` calls `GET /futures/orders/detail`.
- `get_execution_report(order_id)` calls `GET /futures/orders/{order_id}/execution-report`. Each fill has `filled_price`, `filled_qty`, `filled_value`, `filled_time`, `is_maker`, `trading_fee` and `trxn_id`.
- `get_fee(fee_id)` calls `GET /futures/fee/{fee_id}`.
- `get_transactions(limit=None, trade_currency=None, transaction_type=None, status=None, sort_by=None, sort_order=None)` calls `GET /futures/transactions`.
  - `transaction_type` is `DEPOSIT` or `WITHDRAW` and is sent as `type`.
  - `status` is `Completed`, `Processing` or `Failed`. It is checked case-insensitively and sent title-cased.
  - `sort_by` is `created_at` or `updated_at`. `sort_order` is `asc` or `desc`. Both are lower-cased before the check.
  - Invalid values raise `ValueError` before any request.
- `MudrexAPIError.retry_after` holds the `Retry-After` header in seconds on HTTP 429. It is `None` when the header is missing or is not made of ASCII digits. The value is reported as sent.

### Deprecated

- `get_order(order_id)` still works and emits `FutureWarning`. Use `get_order_detail`.
- `place_order(leverage=...)` is ignored, emits `FutureWarning` and will be removed in 0.3.0.

### Response shape changes

- `close_position` returns `order_id` (close order UUID) and `position_id` (position UUID). Before API v1.0.12, `position_id` held the close order UUID.
- `close_position_partial` returns an object with `order_id`, `position_id` and `quantity`. It used to return `{"result": True}`.
- `data: null` returns `None` instead of `MudrexResponse({"result": None})`. `get_positions()` returns `[]` when there are no open positions.
- Scalar `data` is returned as is instead of `MudrexResponse({"result": value})`. For example, `get_liquidation_price` returns the price string. Replace `resp.result` with the value.

### Other changes

- A 429 is retried when `Retry-After` is at most 30 seconds (`MAX_RETRY_AFTER`): the SDK sleeps that long and resends, up to `max_retries` (shared with network retries). If the header is above 30 seconds, missing or invalid, `MudrexAPIError` is raised right away with the real value in `retry_after`. A 429 means the request was rejected before processing, so POSTs are retried too.
- POST requests (`place_order`, `close_position`, `close_position_partial` and the other POST calls) are no longer retried after a read timeout or connection reset, because the exchange may already have accepted them. They are retried only on connect failures, where nothing was sent. GET, PATCH and DELETE still retry up to `max_retries`.
- All ids placed in URL paths (order, position, fee, asset) are percent-encoded, so a value like `abc/../x` cannot change the path.
- `get_transactions(status=...)` is sent title-cased (`Completed`, `Processing`, `Failed`).
- `get_execution_report` and `get_fee` raise `ValueError` on an empty or blank id.
- HTTP helpers `_get`, `_patch` and `_delete` accept `version=`, like `_post`.

### Documentation

- README rate limits match the Authentication and Rate Limits page: default 10/s, 500/min, 30000/hr; core trading adds 720000/day; wallet 2/s, 50/min, 3000/hr.
- README and docstrings describe the fields added in API v1.0.12: `position_id` on orders, open positions and position history, `order_id` on position history rows, and `previous_funding_interval` on asset endpoints.
