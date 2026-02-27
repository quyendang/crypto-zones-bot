import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .datafeed import fetch_ohlcv
from .engine import analyze

app = FastAPI(title="Crypto Zones Bot")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

LATEST: dict[str, dict] = {}

@app.get("/")
def home():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/latest")
def api_latest():
    return LATEST

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

@app.on_event("startup")
async def startup():
    asyncio.create_task(updater())

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