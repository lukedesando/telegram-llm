import io
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent import COMMANDS, run_agent, summarize_history
from config import settings
from conversation import ConversationReply, ConversationService
from delivery import UpdateDeduplicator
from storage import SQLiteConversationStore

logger = logging.getLogger(__name__)

conversation_store = SQLiteConversationStore(settings.database_path)
conversation_service = ConversationService(
    run_agent,
    COMMANDS,
    conversation_store,
    summarize_history,
    recent_context_items=settings.recent_context_items,
    compact_after_items=settings.compact_after_items,
)
update_deduplicator = UpdateDeduplicator(conversation_store)


def _conversation_id(update: Update) -> str:
    return f"telegram:{update.effective_chat.id}"


def _authorized(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == settings.telegram_allowed_user_id


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    async def process() -> None:
        chat_id = update.effective_chat.id
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        logger.info("USER: %s", text)
        try:
            reply = await conversation_service.respond(_conversation_id(update), text)
        except Exception as exc:
            logger.exception("Agent error")
            reply = ConversationReply(f"Error: {str(exc)[:120]}")

        logger.info("BOT [%s]: %s", reply.model, reply.text)
        await _send_reply(update, reply)

    processed = await update_deduplicator.run(update.update_id, process)
    if not processed:
        logger.info("Duplicate Telegram update ignored: %s", update.update_id)


async def _send_reply(update: Update, reply: ConversationReply) -> None:
    if reply.text:
        await update.message.reply_text(reply.text)
    await _send_attachments(update, reply.attachments)


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


async def _reset_context(update: Update, reply_text: str) -> None:
    async def process() -> None:
        conversation_service.clear(_conversation_id(update))
        await update.message.reply_text(reply_text)

    processed = await update_deduplicator.run(update.update_id, process)
    if not processed:
        logger.info("Duplicate Telegram reset ignored: %s", update.update_id)


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await _reset_context(update, "Context cleared.")


async def handle_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await _reset_context(update, "New conversation started. Previous context cleared.")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    async def process() -> None:
        stats = conversation_store.conversation_stats(_conversation_id(update))
        storage_status = "ok" if conversation_store.ping() else "error"
        await update.message.reply_text(
            f"Status: ready | model {settings.openai_model} | storage {storage_status} | "
            f"messages {stats.message_count} | summary {'yes' if stats.summary_present else 'no'} | "
            f"pending {stats.pending_message_count}"
        )

    processed = await update_deduplicator.run(update.update_id, process)
    if not processed:
        logger.info("Duplicate Telegram status ignored: %s", update.update_id)


async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    text = update.message.text or ""
    parts = text.lstrip("/").split(" ", 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    async def process() -> None:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        try:
            reply = await conversation_service.run_command(
                _conversation_id(update),
                text,
                cmd,
                args,
            )
            if reply is None:
                return
        except Exception as exc:
            logger.exception("Command error")
            reply = ConversationReply(f"Error: {str(exc)[:120]}")

        await _send_reply(update, reply)

    processed = await update_deduplicator.run(update.update_id, process)
    if not processed:
        logger.info("Duplicate Telegram command ignored: %s", update.update_id)


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    async def process() -> None:
        await update.message.reply_text(
            "/weather <city> — current weather\n"
            "/flight <UA123> — live flight status\n"
            "/news [topic] — current headlines\n"
            "/search <query> — web search\n"
            "/pdf <url> — fetch and summarize a PDF\n"
            "/status — local relay/storage status\n"
            "/new — start over and clear prior context\n"
            "/clear — clear prior context\n"
            "/help — this list"
        )

    processed = await update_deduplicator.run(update.update_id, process)
    if not processed:
        logger.info("Duplicate Telegram help ignored: %s", update.update_id)


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_token).updater(None).build()
    app.add_handler(CommandHandler("clear", handle_clear))
    app.add_handler(CommandHandler("new", handle_new))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("help", handle_help))
    for cmd in COMMANDS:
        app.add_handler(CommandHandler(cmd, handle_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
