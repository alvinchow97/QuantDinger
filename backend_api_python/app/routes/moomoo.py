"""
moomoo (Futu OpenD) API Routes

Standalone API endpoints for US/HK/CN stock trading via a local OpenD gateway.

Multi-tenancy: connections are isolated per authenticated user via
:class:`BrokerSessionRegistry` so users cannot accidentally place orders
through someone else's moomoo/OpenD account.
"""

from flask import jsonify, request
from app.openapi.blueprint import HumanBlueprint as Blueprint
from app.utils.auth import login_required

from app.utils.logger import get_logger
from app.utils.broker_session import BrokerSessionRegistry
from app.services.moomoo_trading import MoomooClient, MoomooConfig

logger = get_logger(__name__)

moomoo_blp = Blueprint('moomoo', __name__)

# Per-user client cache keyed by (user_id, 'moomoo')
_sessions = BrokerSessionRegistry('moomoo')


def _placeholder_status():
    """Return a stable 'not connected' status when no client exists yet."""
    return {
        "connected": False,
        "host": "",
        "port": 0,
        "tradeEnv": "",
        "market": "",
        "account": "",
    }


def _require_connected_client():
    client = _sessions.get()
    if client is None or not client.connected:
        return None, (jsonify({"success": False, "error": "Not connected to moomoo"}), 400)
    return client, None


# ==================== Connection Management ====================

@moomoo_blp.route('/status', methods=['GET'])
@login_required
def get_status():
    """Get moomoo connection status."""
    try:
        client = _sessions.get()
        if client is None:
            return jsonify({"success": True, "data": _placeholder_status()})
        return jsonify({
            "success": True,
            "data": client.get_connection_status()
        })
    except Exception as e:
        logger.error(f"Get status failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@moomoo_blp.route('/connect', methods=['POST'])
@login_required
def connect():
    """
    Connect to OpenD.

    Request body:
        host (optional, default 127.0.0.1): OpenD host
        port (optional, default 11111): OpenD port
        tradeEnv (optional, default SIMULATE): SIMULATE or REAL
        market (optional, default US): US, HK, or CN
        securityFirm (optional, default FUTUSECURITIES)
        unlockPassword (optional): trade unlock PIN, required for REAL env
    """
    try:
        data = request.get_json() or {}

        config = MoomooConfig(
            host=data.get('host', '127.0.0.1'),
            port=int(data.get('port', 11111)),
            trd_env=data.get('tradeEnv', 'SIMULATE'),
            market=data.get('market', 'US'),
            security_firm=data.get('securityFirm', 'FUTUSECURITIES'),
            unlock_password=data.get('unlockPassword', ''),
        )

        client = MoomooClient(config)
        success = client.connect()

        if success:
            _sessions.set(client)
            return jsonify({
                "success": True,
                "message": "Connected successfully",
                "data": client.get_connection_status()
            })
        else:
            return jsonify({
                "success": False,
                "error": "Connection failed. Please check if OpenD is running and logged in."
            }), 400

    except ImportError:
        return jsonify({
            "success": False,
            "error": "futu-api not installed. Run: pip install futu-api"
        }), 500
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@moomoo_blp.route('/disconnect', methods=['POST'])
@login_required
def disconnect():
    """Disconnect from OpenD."""
    try:
        _sessions.disconnect_current()
        return jsonify({
            "success": True,
            "message": "Disconnected"
        })
    except Exception as e:
        logger.error(f"Disconnect failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Account Queries ====================

@moomoo_blp.route('/account', methods=['GET'])
@login_required
def get_account():
    """Get moomoo account information."""
    try:
        client, err = _require_connected_client()
        if err is not None:
            return err

        return jsonify({
            "success": True,
            "data": client.get_account_summary()
        })
    except Exception as e:
        logger.error(f"Get account info failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@moomoo_blp.route('/positions', methods=['GET'])
@login_required
def get_positions():
    """Get moomoo positions."""
    try:
        client, err = _require_connected_client()
        if err is not None:
            return err

        positions = client.get_positions()
        return jsonify({
            "success": True,
            "data": positions
        })
    except Exception as e:
        logger.error(f"Get positions failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@moomoo_blp.route('/orders', methods=['GET'])
@login_required
def get_orders():
    """Get open moomoo orders."""
    try:
        client, err = _require_connected_client()
        if err is not None:
            return err

        orders = client.get_open_orders()
        return jsonify({
            "success": True,
            "data": orders
        })
    except Exception as e:
        logger.error(f"Get orders failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Trading ====================

@moomoo_blp.route('/order', methods=['POST'])
@login_required
def place_order():
    """
    Place a moomoo order.

    Request body:
        symbol (required): Ticker, e.g. AAPL
        side (required): buy or sell
        quantity (required): Number of shares
        marketType (optional, default USStock): Market type
        orderType (optional, default market): market or limit
        price (required for limit orders): Limit price
    """
    try:
        client, err = _require_connected_client()
        if err is not None:
            return err

        data = request.get_json() or {}

        symbol = data.get('symbol')
        side = data.get('side')
        quantity = data.get('quantity')

        if not symbol:
            return jsonify({"success": False, "error": "Missing symbol"}), 400
        if not side or side.lower() not in ('buy', 'sell'):
            return jsonify({"success": False, "error": "side must be buy or sell"}), 400
        if not quantity or float(quantity) <= 0:
            return jsonify({"success": False, "error": "quantity must be > 0"}), 400

        market_type = data.get('marketType', 'USStock')
        order_type = data.get('orderType', 'market').lower()

        if order_type == 'limit':
            price = data.get('price')
            if not price or float(price) <= 0:
                return jsonify({"success": False, "error": "Limit order requires price"}), 400

            result = client.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                price=float(price),
                market_type=market_type
            )
        else:
            result = client.place_market_order(
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                market_type=market_type
            )

        if result.success:
            return jsonify({
                "success": True,
                "message": result.message,
                "data": {
                    "orderId": result.order_id,
                    "filled": result.filled,
                    "avgPrice": result.avg_price,
                    "status": result.status,
                    "raw": result.raw
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": result.message
            }), 400

    except Exception as e:
        logger.error(f"Place order failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@moomoo_blp.route('/order/<string:order_id>', methods=['DELETE'])
@login_required
def cancel_order(order_id: str):
    """Cancel a moomoo order by ID."""
    try:
        client, err = _require_connected_client()
        if err is not None:
            return err

        success = client.cancel_order(order_id)

        if success:
            return jsonify({
                "success": True,
                "message": f"Order {order_id} cancelled"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Order {order_id} not found"
            }), 404

    except Exception as e:
        logger.error(f"Cancel order failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Market Data ====================

@moomoo_blp.route('/quote', methods=['GET'])
@login_required
def get_quote():
    """Get real-time moomoo quote (query: symbol, marketType)."""
    try:
        client, err = _require_connected_client()
        if err is not None:
            return err

        symbol = request.args.get('symbol')
        market_type = request.args.get('marketType', 'USStock')

        if not symbol:
            return jsonify({"success": False, "error": "Missing symbol"}), 400

        quote = client.get_quote(symbol, market_type)
        return jsonify(quote)

    except Exception as e:
        logger.error(f"Get quote failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
