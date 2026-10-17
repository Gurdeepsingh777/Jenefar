from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from config import ConfigurationError, Settings
from agent.core import AgentCore
from agent.llm import LLMError, LLMRateLimitError

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("jenefar.telegram")


def _agent(context: ContextTypes.DEFAULT_TYPE) -> AgentCore:
    return context.application.bot_data["agent_core"]


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


async def enforce_allowlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    user = update.effective_user
    user_id = user.id if user is not None else None
    if settings.is_authorized(user_id):
        return

    message = update.effective_message
    if message is not None:
        try:
            await message.reply_text(
                "Access denied. This private agent accepts commands only from its configured Telegram user IDs."
            )
        except TelegramError:
            logger.warning("Could not reply to an unauthorized Telegram update.")
    # Stop every other handler for an unauthorized update.
    raise ApplicationHandlerStop


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "Jenefar Telegram Agent online.\n\n"
        "Send a normal text message to ask a task. I can use the configured LLM, "
        "read public pages, manage GitHub repositories/issues/PRs, and keep a short "
        "conversation memory for your Telegram user ID.\n\n"
        "Commands:\n"
        "/status — show runtime and tool status\n"
        "/clear — clear this user's short-term conversation memory\n\n"
        "Only IDs in ALLOWED_TELEGRAM_USER_IDS are authorized."
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    removed = _agent(context).clear_memory(user.id)
    await message.reply_text(
        "Short-term conversation memory cleared." if removed
        else "There was no stored conversation memory to clear."
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    settings = _settings(context)
    status = _agent(context).status(user.id)
    github_text = "configured" if status["github_configured"] else "not configured (set GITHUB_PAT)"
    await message.reply_text(
        "Jenefar Telegram Agent status\n"
        f"LLM model: {status['model']}\n"
        f"API base URL: {status['provider_base_url']}\n"
        f"GitHub: {github_text}\n"
        f"Registered tools: {status['registered_tools']}\n"
        f"Persistent skills: {status['learned_skills']}\n"
        f"Remembered messages: {status['remembered_messages']}/{status['max_history_messages']}\n"
        f"Maximum tool rounds: {status['max_tool_rounds']}\n"
        f"Allowlisted Telegram users: {len(settings.allowed_telegram_user_ids)}"
    )


def _split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    remaining = str(text or "").strip() or "I received an empty response."
    chunks: list[str] = []
    while len(remaining) > limit:
        boundary = remaining.rfind("\n", 0, limit)
        if boundary < limit // 2:
            boundary = remaining.rfind(" ", 0, limit)
        if boundary < limit // 2:
            boundary = limit
        chunks.append(remaining[:boundary].rstrip())
        remaining = remaining[boundary:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def text_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or user is None or chat is None or not message.text:
        return

    prompt = message.text.strip()
    settings = _settings(context)
    if not prompt:
        await message.reply_text("Please send a non-empty task.")
        return
    if len(prompt) > settings.max_input_chars:
        await message.reply_text(
            f"Message is too long. Send no more than {settings.max_input_chars} characters."
        )
        return

    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
        answer = await asyncio.wait_for(
            _agent(context).respond(user.id, prompt),
            timeout=settings.agent_timeout_seconds,
        )
        chunks = _split_telegram_text(answer)
        for index, chunk in enumerate(chunks):
            if index == 0:
                await message.reply_text(chunk)
            else:
                await context.bot.send_message(chat_id=chat.id, text=chunk)
    except LLMRateLimitError:
        await message.reply_text(
            "The model API rate limit is reached. Wait a little, or configure a provider with available free quota."
        )
    except LLMError as exc:
        logger.warning("LLM request failed for authorized user %s: %s", user.id, exc)
        await message.reply_text(f"LLM provider error: {exc}")
    except asyncio.TimeoutError:
        await message.reply_text(
            "This task exceeded the configured time limit. Check the latest GitHub/scratchpad state, then retry with a smaller task."
        )
    except TelegramError as exc:
        logger.warning("Telegram delivery failed: %s", type(exc).__name__)
    except Exception:
        logger.exception("Unhandled Telegram task error")
        try:
            await message.reply_text(
                "The task failed because of an internal error. Check the service logs; your bot token and API keys are not shown here."
            )
        except TelegramError:
            pass


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.error("Telegram update handler failed: %r", error, exc_info=error)


async def close_agent(application: Application) -> None:
    core = application.bot_data.get("agent_core")
    if core is not None:
        await core.aclose()


def build_application(settings: Settings, core: AgentCore | None = None) -> Application:
    agent_core = core or AgentCore(settings)
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(8)
        .post_shutdown(close_agent)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["agent_core"] = agent_core

    # Group -1 guarantees the allowlist is checked before any command/text handler.
    application.add_handler(TypeHandler(Update, enforce_allowlist), group=-1)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_task))
    application.add_error_handler(on_error)
    return application


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    application = build_application(settings)
    logger.info(
        "Starting Telegram-only agent with model=%s, allowed_users=%d, github=%s, tools=%d",
        settings.llm_model_name,
        len(settings.allowed_telegram_user_ids),
        bool(settings.github_pat),
        len(application.bot_data["agent_core"].tools.names()),
    )
    # All handlers and API clients are asynchronous; python-telegram-bot manages
    # the polling lifecycle and graceful shutdown in its own event loop.
    # Avoid replaying stale queued owner commands after a deployment/restart.
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
