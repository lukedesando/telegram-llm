import io
import logging
from collections import deque

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent import COMMANDS, run_agent
from config import settings

logger = logging.getLogger(__name__)

_history: dict[int, deque] = {}
MAX_HISTORY = 12


def _get_history(chat_id: int) -> deque:
    if chat_id not in _history:
        _history[chat_id] = deque(maxlen=MAX_HISTORY)
    return _history[chat_id]


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.id != settings.telegram_allowed_user_id:
        await update.message.reply_text("Unauthorized.")
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    chat_id = update.effective_chat.id
    history = _get_history(chat_id)
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    logger.info("USER: %s", text)
    try:
        answer, used_model, attachments = await run_agent(text, list(history))
    except Exception as exc:
        logger.exception("Agent error")
        answer = f"Error: {str(exc)[:120]}"
        used_model = None
        attachments = []

    logger.info("BOT [%s]: %s", used_model, answer)
    history.append(("user", text))
    history.append(("assistant", answer))

    if answer:
        await update.message.reply_text(answer)
    await _send_attachments(update, attachments)


async def _send_attachments(update: Update, attachments: list) -> None:
    for att in attachments:
        try:
            if att["type"] == "document":
                doc = io.BytesIO(att["data"])
                doc.name = att.get("filename", "file")
                await update.message.reply_document(
                    doc,
                    filename=att.get("filename", "file"),
                )
        except Exception as exc:
            logger.warning("Failed to send attachment: %s", exc)


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.id != settings.telegram_allowed_user_id:
        return
    _history.pop(update.effective_chat.id, None)
    await update.message.reply_text("Context cleared.")


async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.id != settings.telegram_allowed_user_id:
        return

    text = update.message.text or ""
    parts = text.lstrip("/").split(" ", 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    fn = COMMANDS.get(cmd)
    if not fn:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        result = await fn(args)
        if isinstance(result, tuple):
            answer, attachments = result
        else:
            answer, attachments = result, []
    except Exception as exc:
        logger.exception("Command error")
        answer = f"Error: {str(exc)[:120]}"
        attachments = []

    chat_id = update.effective_chat.id
    history = _get_history(chat_id)
    history.append(("user", text))
    if answer:
        history.append(("assistant", answer))
        await update.message.reply_text(answer)
    await _send_attachments(update, attachments)


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.id != settings.telegram_allowed_user_id:
        return
    await update.message.reply_text(
        "/weather <city> — current weather\n"
        "/flight <UA123> — live flight status\n"
        "/news [topic] — current headlines\n"
        "/search <query> — web search\n"
        "/pdf <url> — fetch and summarize a PDF\n"
        "/clear — reset conversation\n"
        "/help — this list"
    )


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_token).updater(None).build()
    app.add_handler(CommandHandler("clear", handle_clear))
    app.add_handler(CommandHandler("help", handle_help))
    for cmd in COMMANDS:
        app.add_handler(CommandHandler(cmd, handle_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
