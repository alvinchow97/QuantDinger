# moomoo (Futu OpenD) Trading Module

Supports US/HK/CN stock trading via a locally running **OpenD** gateway.
This is a **scaffold**, structured after `app/services/ibkr_trading/` — the
route wiring and session handling are complete, but the `futu-api` call
signatures in `client.py` should be verified against a live OpenD instance
before relying on it for real paper/live trading.

## Installation

```bash
pip install futu-api
```

Add the dependency to `requirements.txt` if not already present.

## OpenD Setup

1. Download OpenD from the [Futu OpenAPI site](https://openapi.futunn.com/) —
   moomoo and Futu share the same OpenD gateway and API.
2. Log in to OpenD with your moomoo account credentials.
3. OpenD listens on `127.0.0.1:11111` by default.
4. For live trading, set a trade unlock PIN in the moomoo app and supply it
   via `MoomooConfig.unlock_password`. Paper trading (`trd_env=SIMULATE`)
   does not require unlocking.

## Port Reference

| Client | Default Port |
|--------|---------------|
| OpenD  | 11111 |

## Trade Environment

- `MoomooConfig.trd_env = "SIMULATE"` — paper trading
- `MoomooConfig.trd_env = "REAL"` — live trading (requires unlock password)

## Market Filter

`MoomooConfig.market` must match the market you intend to trade
(`"US"`, `"HK"`, or `"CN"`) — it is passed to `OpenSecTradeContext` as
`filter_trdmarket` and restricts which account the trade context binds to.

## Known Gaps / TODO

- Verify `place_order`, `position_list_query`, `order_list_query`, and
  `accinfo_query` field names against the current `futu-api` version pinned
  in `requirements.txt` — Futu has changed response schemas across major
  SDK versions.
- Add contract tests mirroring `tests/test_htx_v5.py` or the other
  offline exchange contract fixtures once the client is verified against a
  real OpenD instance.
- Wire credential storage into `app/services/quick_trade/credentials.py` and
  `app/utils/credential_crypto.py` if moomoo credentials need to be
  persisted (currently connection params are request-scoped only, like IBKR).
- Register moomoo in `app/services/broker_market_policy.py` if it should
  participate in strategy-runtime broker selection alongside IBKR/Alpaca.
