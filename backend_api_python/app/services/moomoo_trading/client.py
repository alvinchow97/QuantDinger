"""
moomoo (Futu OpenD) Trading Client

Uses the `futu-api` SDK to connect to a locally running OpenD gateway for
paper and live trading, mirroring the IBKR/TWS integration shape.

OpenD is a standalone daemon (like TWS/IB Gateway) that this client connects
to over a local socket. It must be running and logged in before `connect()`
will succeed. See ../../../../docs or this package's README for setup.

NOTE: This is a scaffold. The `futu-api` call signatures below reflect the
documented SDK surface but have not been exercised against a live OpenD
instance in this repository. Verify against
https://openapi.futunn.com/futu-api-doc/ before relying on it for real
paper/live trading, and add tests under `tests/` alongside the IBKR ones.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.utils.logger import get_logger
from app.services.moomoo_trading.symbols import normalize_symbol, parse_symbol

logger = get_logger(__name__)

# Lazy import futu-api to allow other features to work without it installed
futu = None


def _ensure_futu():
    """Ensure the futu-api package is imported."""
    global futu
    if futu is None:
        try:
            import futu as _futu
            futu = _futu
        except ImportError:
            raise ImportError(
                "futu-api is not installed. Run: pip install futu-api"
            )
    return futu


@dataclass
class MoomooConfig:
    """moomoo/OpenD connection configuration."""
    host: str = "127.0.0.1"
    port: int = 11111  # OpenD default port
    trd_env: str = "SIMULATE"  # "SIMULATE" (paper) or "REAL" (live)
    market: str = "US"  # "US", "HK", or "CN" — must match filter_trdmarket
    security_firm: str = "FUTUSECURITIES"  # or "FUTUFUTURES", varies by account region
    unlock_password: str = ""  # trade unlock PIN, required before live orders
    rsa_key_path: str = ""  # required when OpenD encryption is enabled


@dataclass
class OrderResult:
    """Order execution result."""
    success: bool
    order_id: str = ""
    filled: float = 0.0
    avg_price: float = 0.0
    status: str = ""
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class MoomooClient:
    """
    moomoo (Futu OpenD) Trading Client

    Usage:
        config = MoomooConfig(port=11111, trd_env="SIMULATE")
        client = MoomooClient(config)

        if client.connect():
            result = client.place_market_order("AAPL", "buy", 10, "USStock")
            positions = client.get_positions()
            client.disconnect()
    """

    def __init__(self, config: Optional[MoomooConfig] = None):
        self.config = config or MoomooConfig()
        self._quote_ctx = None
        self._trd_ctx = None
        self._connected = False
        self._lock = threading.Lock()
        self._account_id = ""

    @property
    def connected(self) -> bool:
        return self._connected and self._trd_ctx is not None

    def connect(self) -> bool:
        """
        Connect to OpenD and unlock trading (if unlock_password is set).

        Returns:
            True if connected successfully
        """
        with self._lock:
            if self.connected:
                return True

            try:
                _ensure_futu()

                logger.info(
                    f"Connecting to moomoo OpenD: {self.config.host}:{self.config.port} "
                    f"(env={self.config.trd_env}, market={self.config.market})"
                )

                trd_market = getattr(futu.TrdMarket, self.config.market, futu.TrdMarket.US)
                security_firm = getattr(
                    futu.SecurityFirm, self.config.security_firm, futu.SecurityFirm.FUTUSECURITIES
                )

                self._quote_ctx = futu.OpenQuoteContext(
                    host=self.config.host, port=self.config.port
                )
                self._trd_ctx = futu.OpenSecTradeContext(
                    filter_trdmarket=trd_market,
                    host=self.config.host,
                    port=self.config.port,
                    security_firm=security_firm,
                )

                if self.config.unlock_password:
                    ret, data = self._trd_ctx.unlock_trade(self.config.unlock_password)
                    if ret != futu.RET_OK:
                        logger.error(f"moomoo trade unlock failed: {data}")
                        self.disconnect()
                        return False

                self._connected = True

                ret, accounts = self._trd_ctx.get_acc_list()
                if ret == futu.RET_OK and len(accounts) > 0:
                    self._account_id = str(accounts.iloc[0]["acc_id"])
                    logger.info(f"moomoo connected, account: {self._account_id}")
                else:
                    logger.warning("moomoo connected but no account info retrieved")

                return True

            except Exception as e:
                logger.error(f"moomoo connection failed: {e}")
                self._connected = False
                return False

    def disconnect(self):
        """Disconnect from OpenD."""
        with self._lock:
            for ctx in (self._trd_ctx, self._quote_ctx):
                if ctx is not None:
                    try:
                        ctx.close()
                    except Exception as e:
                        logger.warning(f"moomoo disconnect exception: {e}")
            self._trd_ctx = None
            self._quote_ctx = None
            self._connected = False
            logger.info("moomoo disconnected")

    def _ensure_connected(self):
        if not self.connected:
            if not self.connect():
                raise ConnectionError("Cannot connect to moomoo OpenD")

    def _trd_env(self):
        _ensure_futu()
        return futu.TrdEnv.SIMULATE if self.config.trd_env == "SIMULATE" else futu.TrdEnv.REAL

    # ==================== Order Methods ====================

    def _place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        market_type: str,
        order_type: str,
        price: float = 0.0,
    ) -> OrderResult:
        try:
            self._ensure_connected()
            _ensure_futu()

            code = normalize_symbol(symbol, market_type)
            trd_side = futu.TrdSide.BUY if side.lower() == "buy" else futu.TrdSide.SELL
            futu_order_type = futu.OrderType.MARKET if order_type == "market" else futu.OrderType.NORMAL

            ret, data = self._trd_ctx.place_order(
                price=price,
                qty=quantity,
                code=code,
                trd_side=trd_side,
                order_type=futu_order_type,
                trd_env=self._trd_env(),
                acc_id=int(self._account_id) if self._account_id else 0,
            )

            if ret != futu.RET_OK:
                return OrderResult(success=False, message=str(data))

            row = data.iloc[0]
            return OrderResult(
                success=True,
                order_id=str(row.get("order_id", "")),
                status=str(row.get("order_status", "")),
                message="Order submitted",
                raw=row.to_dict(),
            )

        except Exception as e:
            logger.error(f"moomoo order failed: {e}")
            return OrderResult(success=False, message=str(e))

    def place_market_order(
        self, symbol: str, side: str, quantity: float, market_type: str = "USStock"
    ) -> OrderResult:
        """Place a market order."""
        return self._place_order(symbol, side, quantity, market_type, order_type="market")

    def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float, market_type: str = "USStock"
    ) -> OrderResult:
        """Place a limit order."""
        return self._place_order(symbol, side, quantity, market_type, order_type="limit", price=price)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by moomoo order ID."""
        try:
            self._ensure_connected()
            _ensure_futu()
            ret, _ = self._trd_ctx.modify_order(
                futu.ModifyOrderOp.CANCEL, order_id, 0, 0, trd_env=self._trd_env()
            )
            return ret == futu.RET_OK
        except Exception as e:
            logger.error(f"moomoo cancel order failed: {e}")
            return False

    # ==================== Account Queries ====================

    def get_account_summary(self) -> Dict[str, Any]:
        """Get account funds summary."""
        try:
            self._ensure_connected()
            ret, data = self._trd_ctx.accinfo_query(trd_env=self._trd_env())
            if ret != futu.RET_OK or len(data) == 0:
                return {}
            return data.iloc[0].to_dict()
        except Exception as e:
            logger.error(f"moomoo get account summary failed: {e}")
            return {}

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        try:
            self._ensure_connected()
            ret, data = self._trd_ctx.position_list_query(trd_env=self._trd_env())
            if ret != futu.RET_OK:
                return []
            return data.to_dict("records")
        except Exception as e:
            logger.error(f"moomoo get positions failed: {e}")
            return []

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get open orders."""
        try:
            self._ensure_connected()
            ret, data = self._trd_ctx.order_list_query(trd_env=self._trd_env())
            if ret != futu.RET_OK:
                return []
            return data.to_dict("records")
        except Exception as e:
            logger.error(f"moomoo get open orders failed: {e}")
            return []

    # ==================== Market Data ====================

    def get_quote(self, symbol: str, market_type: str = "USStock") -> Dict[str, Any]:
        """Get a real-time snapshot quote."""
        try:
            self._ensure_connected()
            code = normalize_symbol(symbol, market_type)
            ret, data = self._quote_ctx.get_market_snapshot([code])
            if ret != futu.RET_OK or len(data) == 0:
                return {"success": False, "error": str(data)}
            row = data.iloc[0]
            return {
                "success": True,
                "symbol": symbol,
                "last": row.get("last_price"),
                "high": row.get("high_price"),
                "low": row.get("low_price"),
                "volume": row.get("volume"),
                "close": row.get("prev_close_price"),
            }
        except Exception as e:
            logger.error(f"moomoo get quote failed: {e}")
            return {"success": False, "error": str(e)}

    def get_connection_status(self) -> Dict[str, Any]:
        """Get connection status."""
        return {
            "connected": self.connected,
            "host": self.config.host,
            "port": self.config.port,
            "tradeEnv": self.config.trd_env,
            "market": self.config.market,
            "account": self._account_id,
        }
