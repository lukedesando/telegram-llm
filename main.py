import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from telegram import Update

from bot import build_application, conversation_store
from config import settings
from ingress import public_surface_allows

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

application = build_application()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    webhook_url = f"{settings.webhook_base_url}/webhook"
    await application.bot.set_webhook(
        url=webhook_url,
        secret_token=settings.webhook_secret_token,
        allowed_updates=["message"],
    )
    logger.info("Webhook registered: %s", webhook_url)
    await application.start()
    yield
    await application.stop()
    await application.shutdown()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def public_webhook_surface_guard(request: Request, call_next):
    if not public_surface_allows(
        webhook_base_url=settings.webhook_base_url,
        request_host=request.headers.get("host", ""),
        method=request.method,
        path=request.url.path,
    ):
        return Response(status_code=404)
    return await call_next(request)


@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=None),
):
    supplied_secret = x_telegram_bot_api_secret_token or ""
    if not secrets.compare_digest(supplied_secret, settings.webhook_secret_token):
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    update = Update.de_json(body, application.bot)
    await application.update_queue.put(update)
    return Response(status_code=200)


@app.get("/health")
async def health():
    storage_ok = conversation_store.ping()
    return JSONResponse(
        status_code=200 if storage_ok else 503,
        content={
            "status": "ok" if storage_ok else "degraded",
            "storage": "ok" if storage_ok else "error",
            "revision": settings.app_revision,
        },
    )
