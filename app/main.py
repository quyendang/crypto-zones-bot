import asyncio
from typing import Any

import asyncpg
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .datafeed import fetch_ohlcv
from .engine import analyze

app = FastAPI(title="Crypto Zones Bot")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

LATEST: dict[str, dict] = {}
DB_POOL: asyncpg.Pool | None = None


@app.get("/")
def home():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/latest")
def api_latest():
    return LATEST


@app.get("/api/trades")
async def api_trades() -> dict[str, Any]:
    """
    Trả về danh sách lệnh và thống kê holdings/p&l (giả lập).
    """
    if DB_POOL is None:
        return {"enabled": False, "holdings": [], "trades": []}

    async with DB_POOL.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, ts, symbol, side, price, qty, notional_usd "
            "FROM trades ORDER BY ts ASC"
        )

    stats: dict[str, dict[str, float | str]] = {}
    trades: list[dict[str, Any]] = []

    for r in rows:
        sym = r["symbol"]
        side = r["side"]
        price = float(r["price"])
        qty = float(r["qty"])
        notional = float(r["notional_usd"])

        s = stats.setdefault(
            sym,
            {
                "symbol": sym,
                "position_qty": 0.0,
                "avg_price": 0.0,
                "realized_pnl": 0.0,
            },
        )

        pos_qty = float(s["position_qty"])  # type: ignore[arg-type]
        avg_price = float(s["avg_price"])  # type: ignore[arg-type]
        realized = float(s["realized_pnl"])  # type: ignore[arg-type]

        if side == "BUY":
            total_cost_before = avg_price * pos_qty
            total_cost_after = total_cost_before + notional
            new_qty = pos_qty + qty
            s["position_qty"] = new_qty
            s["avg_price"] = total_cost_after / new_qty if new_qty > 0 else 0.0
        else:  # SELL
            if pos_qty > 0:
                sell_qty = min(qty, pos_qty)
                trade_realized = (price - avg_price) * sell_qty
                realized += trade_realized
                pos_qty -= sell_qty
                s["position_qty"] = pos_qty
                s["realized_pnl"] = realized
                if pos_qty <= 0:
                    s["avg_price"] = 0.0

        trades.append(
            {
                "id": int(r["id"]),
                "ts": r["ts"].isoformat(),
                "symbol": sym,
                "side": side,
                "price": price,
                "qty": qty,
                "notional_usd": notional,
            }
        )

    holdings: list[dict[str, Any]] = []

    for sym, s in stats.items():
        pos_qty = float(s["position_qty"])  # type: ignore[arg-type]
        avg_price = float(s["avg_price"])  # type: ignore[arg-type]
        realized = float(s["realized_pnl"])  # type: ignore[arg-type]

        latest_price: float | None = None
        for k, v in LATEST.items():
            if k.startswith(f"{sym}-"):
                latest_price = float(v.get("price") or 0.0)
                break

        market_value = 0.0
        unrealized = 0.0
        if latest_price and pos_qty > 0:
            market_value = latest_price * pos_qty
            unrealized = (latest_price - avg_price) * pos_qty

        holdings.append(
            {
                "symbol": sym,
                "position_qty": pos_qty,
                "avg_price": avg_price,
                "market_price": latest_price,
                "market_value_usd": market_value,
                "unrealized_pnl_usd": unrealized,
                "realized_pnl_usd": realized,
            }
        )

    return {"enabled": True, "holdings": holdings, "trades": trades}


async def updater():
    while True:
        try:
            for sym in settings.SYMBOLS:
                for tf in settings.TIMEFRAMES:
                    df = fetch_ohlcv(sym, tf, limit=600)
                    report = analyze(df, sym, tf)
                    LATEST[f"{sym}-{tf}"] = report
        except Exception as e:
            LATEST["__error__"] = {"error": str(e)}
        await asyncio.sleep(settings.UPDATE_SECONDS)


async def ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id BIGSERIAL PRIMARY KEY,
                ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                qty DOUBLE PRECISION NOT NULL,
                notional_usd DOUBLE PRECISION NOT NULL
            );
            """
        )


async def trade_bot_loop():
    """
    Vòng lặp giả lập bot trading:
    - Mỗi TRADE_INTERVAL_SECONDS kiểm tra tín hiệu cho BTC/ETH.
    - Nếu có buy: vào lệnh 1000 USD, tránh trùng giá quá gần.
    - Nếu có sell: xả toàn bộ lượng coin đang giữ.
    """
    global DB_POOL
    # đợi updater chạy lần đầu
    await asyncio.sleep(5)

    symbols = [s.strip().upper() for s in settings.SYMBOLS]
    trade_symbols = [s for s in ("BTC", "ETH") if s in symbols]
    if not trade_symbols:
        return

    while True:
        try:
            if DB_POOL is None:
                return
            async with DB_POOL.acquire() as conn:
                for sym in trade_symbols:
                    # chọn timeframe đầu tiên làm khung tham chiếu
                    tf = settings.TIMEFRAMES[0]
                    df = fetch_ohlcv(sym, tf, limit=600)
                    report = analyze(df, sym, tf)
                    price = float(report["price"])
                    triggers = report.get("triggers", {})

                    # BUY logic
                    if triggers.get("buy"):
                        min_diff = (
                            settings.MIN_DIFF_ETH
                            if sym == "ETH"
                            else settings.MIN_DIFF_BTC
                        )
                        last_buy_price = await conn.fetchval(
                            "SELECT price FROM trades "
                            "WHERE symbol=$1 AND side='BUY' "
                            "ORDER BY ts DESC LIMIT 1",
                            sym,
                        )
                        should_buy = (
                            last_buy_price is None
                            or abs(price - float(last_buy_price)) >= float(min_diff)
                        )
                        if should_buy:
                            notional = 1000.0
                            qty = notional / price if price > 0 else 0.0
                            if qty > 0:
                                await conn.execute(
                                    "INSERT INTO trades(symbol, side, price, qty, notional_usd) "
                                    "VALUES($1,$2,$3,$4,$5)",
                                    sym,
                                    "BUY",
                                    price,
                                    qty,
                                    notional,
                                )

                    # SELL logic: xả toàn bộ
                    if triggers.get("sell"):
                        position_qty = await conn.fetchval(
                            "SELECT COALESCE(SUM(CASE WHEN side='BUY' THEN qty ELSE -qty END), 0) "
                            "FROM trades WHERE symbol=$1",
                            sym,
                        )
                        if position_qty and float(position_qty) > 0:
                            qty = float(position_qty)
                            notional = qty * price
                            await conn.execute(
                                "INSERT INTO trades(symbol, side, price, qty, notional_usd) "
                                "VALUES($1,$2,$3,$4,$5)",
                                sym,
                                "SELL",
                                price,
                                qty,
                                notional,
                            )
        except Exception as e:
            LATEST["__trade_error__"] = {"error": str(e)}

        await asyncio.sleep(settings.TRADE_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup():
    global DB_POOL
    if settings.DATABASE_URL:
        DB_POOL = await asyncpg.create_pool(dsn=settings.DATABASE_URL, min_size=1, max_size=5)
        await ensure_schema(DB_POOL)
        asyncio.create_task(trade_bot_loop())
    asyncio.create_task(updater())


@app.on_event("shutdown")
async def shutdown():
    global DB_POOL
    if DB_POOL is not None:
        await DB_POOL.close()


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    last_sent = None
    while True:
        payload = LATEST
        if payload != last_sent:
            await websocket.send_json(payload)
            last_sent = dict(payload)
        await asyncio.sleep(1)