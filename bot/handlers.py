"""Thin Telegram adapter: everything Telegram-specific lives here.

Phase 3 deliverable. Routing per Planning.md:
- /start -> passcode gate (5 fails -> 15-min lockout), then onboarding
- /advance [N] -> bumps the canonical-day offset, runs per-day checks inline
- /reset, /wipe -> inline Yes/No confirmation -> CallbackQueryHandler
- text -> rate limit -> Loom-link detection -> transcript/summary classification
  -> agent_core.handle_incoming (only ordinary chat hits the LLM)
- typing indicator while the engine composes; one complete message back

agent_core is transport-agnostic: this module never touches journey logic.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot import config
from bot.agent_core import AgentCore
from bot.gates import get_effective_day

logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 2.0
PASSCODE_MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

LOOM_RE = re.compile(r"https?://(?:www\.)?loom\.com/(?:share|embed)/[A-Za-z0-9]+/?")

CONFIRM_WIPE = "confirm_wipe"
CONFIRM_RESET = "confirm_reset"


# ---------------------------------------------------------------------------
# App wiring
# ---------------------------------------------------------------------------
def build_agent(app: Application) -> AgentCore:
    from bot.llm.client import OpenAIClient

    repo = app.bot_data["repo"]
    return AgentCore(repo, OpenAIClient())


def register_handlers(app: Application, agent: AgentCore) -> None:
    app.bot_data["agent"] = agent
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("advance", cmd_advance))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("wipe", cmd_wipe))
    app.add_handler(CallbackQueryHandler(cb_confirm, pattern=f"^({CONFIRM_WIPE}|{CONFIRM_RESET})$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.Document.TXT, on_doc_txt))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_error_handler(on_error)


# ---------------------------------------------------------------------------
# Helpers (mechanical only)
# ---------------------------------------------------------------------------
def _chat_key(update: Update) -> tuple[str, str] | None:
    if update.effective_user is None:
        return None
    return "telegram", str(update.effective_user.id)


async def _within_rate_limit(
    repo: Any, user_id: int, min_gap: float = RATE_LIMIT_SECONDS
) -> bool:
    """Per-user rate limiting on last_message_at (bursts dropped, not queued)."""
    from datetime import UTC, datetime

    user = await repo.get_user(user_id)
    if user is None or not user.last_message_at:
        return True
    try:
        last = datetime.fromisoformat(user.last_message_at)
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return (datetime.now(UTC) - last).total_seconds() >= min_gap
    except ValueError:
        return True


async def _check_passcode(update: Update, ctx: ContextTypes.DEFAULT_TYPE, repo: Any) -> bool:
    user = await repo.get_or_create_user("telegram", str(update.effective_user.id))
    from datetime import UTC, datetime, timedelta

    if user.passcode_verified:
        return True
    # lockout check
    if user.locked_until:
        locked = datetime.fromisoformat(user.locked_until)
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=UTC)
        if datetime.now(UTC) < locked:
            await update.effective_message.reply_text(
                "Too many failed tries - give it a few minutes and come back."
            )
            return False
        # lockout expired
        await repo.update_passcode_state(
            user.id, failed_attempts=0, locked_until=None
        )
        user = await repo.get_user(user.id)

    text = (update.effective_message.text or "").strip()
    # accept the passcode straight from /start or as a follow-up message
    candidate = text.replace("/start", "", 1).strip()
    if not candidate and ctx.user_data is not None:
        candidate = ""
    if candidate == config.DEMO_PASSCODE:
        await repo.update_passcode_state(user.id, verified_delta=1)
        # fresh verification resets the attempt counter
        await repo.update_passcode_state(user.id, failed_attempts=0, locked_until=None)
        await update.effective_message.reply_text(
            "You're in. Lovely to meet you - let's get started."
        )
        return True

    attempts = (user.failed_attempts or 0) + 1
    if attempts >= PASSCODE_MAX_ATTEMPTS:
        lock_until = (datetime.now(UTC) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
        await repo.update_passcode_state(
            user.id, failed_attempts=attempts, locked_until=lock_until
        )
        await update.effective_message.reply_text(
            "That's five misses - I'm sitting out for 15 minutes. Come back then."
        )
    else:
        await repo.update_passcode_state(user.id, failed_attempts=attempts)
        await update.effective_message.reply_text(
            "Hmm, that's not the access code I have. Want to try again?"
        )
    return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None or update.effective_user is None:
        return
    repo = ctx.application.bot_data["repo"]
    if not await _check_passcode(update, ctx, repo):
        return
    agent: AgentCore = ctx.application.bot_data["agent"]
    outcome = await agent.handle_incoming(
        "telegram", str(update.effective_user.id),
        "hey, I'm here to start - I have my access code.",
    )
    await _send_with_typing(update, ctx, outcome.reply)


async def cmd_advance(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message:
        return
    repo = ctx.application.bot_data["repo"]
    user = await repo.get_or_create_user("telegram", str(update.effective_user.id))
    # /advance is a demo/admin command: no rate limit, no engagement bookkeeping
    arg = ctx.args[0] if ctx.args else ""
    if not arg or not (arg.isdigit() and 1 <= int(arg) <= 400):
        await update.effective_message.reply_text("usage: /advance [number of days, 1-400]")
        return
    n = int(arg)
    from bot.scheduler import dedupe_reasons, initiate_conversation, run_daily_checks_for_user

    reasons: list[str] = []
    user = await repo.get_user(user.id)
    for _ in range(n):
        await repo.bump_simulated_day(user.id, 1)
        user = await repo.get_user(user.id)
        day = get_effective_day(user)
        # no user message arrived: the sweep for this "day" never saw organic
        # engagement - exactly how real days flow; admin commands never touch
        # last_message_at / daily_engagement (Planning.md guard)
        reason = await run_daily_checks_for_user(repo, user, day)
        if reason:
            reasons.append(reason)
    eff = get_effective_day(user)

    # ONE consolidated message instead of a burst (batching per Planning.md)
    consolidated_sent = False
    if reasons:
        agent: AgentCore = ctx.application.bot_data["agent"]
        persona_state = await agent._persona_state(user)
        try:
            text = await initiate_conversation(
                _make_send_fn(update, ctx), agent.client, persona_state,
                reasons=dedupe_reasons(reasons),  # type: ignore[arg-type]
                platform="telegram",
                platform_user_id=str(update.effective_user.id),
            )
            consolidated_sent = bool(text)
        except Exception:  # noqa: BLE001 - demo must not die on composition failure
            logger.exception("consolidated proactive composition failed")

    summary_line = f"fast-forwarded {n} day(s) - you're on day {eff}."
    if reasons:
        note = "one consolidated check-in sent" if consolidated_sent else (
            "check-ins triggered: " + ", ".join(sorted(set(reasons)))
        )
        summary_line += f" ({note})."
    await update.effective_message.reply_text(summary_line)


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    await _ask_confirm(
        update, CONFIRM_RESET, "Restart the whole journey? History stays for reference."
    )


async def cmd_wipe(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    await _ask_confirm(update, CONFIRM_WIPE, "Delete ALL of your data here? This cannot be undone.")


async def _ask_confirm(update: Update, action: str, question: str) -> None:
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Yes", callback_data=action),
            InlineKeyboardButton("No", callback_data="cancel_" + action),
        ]]
    )
    await update.effective_message.reply_text(question, reply_markup=kb)


async def cb_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    data = query.data
    if data.startswith("cancel_"):
        await query.edit_message_text("Cancelled - nothing changed.")
        return
    repo = ctx.application.bot_data["repo"]
    user = await repo.get_or_create_user("telegram", str(update.effective_user.id))
    if data == CONFIRM_WIPE:
        await repo.wipe_user(user.id)
        await query.edit_message_text("Your data is deleted. See you soon - /start whenever.")
    elif data == CONFIRM_RESET:
        await repo.reset_user_progress(user.id)
        await query.edit_message_text("Fresh journey started - your history is kept for reference.")


# ---------------------------------------------------------------------------
# Message routing
# ---------------------------------------------------------------------------
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message:
        return
    repo = ctx.application.bot_data["repo"]
    user = await repo.get_or_create_user("telegram", str(update.effective_user.id))
    if not user.passcode_verified:
        await _check_passcode(update, ctx, repo)
        return
    if not await _within_rate_limit(repo, user.id):
        return  # drop the burst silently (Planning.md: bursts not queued)

    text = update.effective_message.text or ""
    m = LOOM_RE.search(text)
    if m:
        await _handle_loom_link(update, ctx, repo, user.id, m.group(0))
        return

    agent: AgentCore = ctx.application.bot_data["agent"]
    outcome = await agent.handle_incoming("telegram", str(user.platform_user_id), text)
    await _send_with_typing(update, ctx, outcome.reply)


async def on_doc_txt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message:
        return
    repo = ctx.application.bot_data["repo"]
    user = await repo.get_or_create_user("telegram", str(update.effective_user.id))
    if not user.passcode_verified:
        await update.effective_message.reply_text("Send /start with your access code first.")
        return
    text = (update.effective_message.document and
            await _read_txt(update, ctx)) or ""
    if not text:
        await update.effective_message.reply_text("Couldn't read that .txt - try again?")
        return
    agent: AgentCore = ctx.application.bot_data["agent"]
    outcome = await agent.handle_incoming("telegram", str(user.platform_user_id), text)
    await _send_with_typing(update, ctx, outcome.reply)


async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    await update.effective_message.reply_text(
        "Got a voice note. Two ways to use it:\n"
        "1. self-report - we just talk about how practice went, no numbers\n"
        "2. full metrics - I transcribe it and compute your filler/WPM numbers\n"
        "Which one do you want? (I'll remember your pick for THIS recording only - "
        "every fallback asks fresh.)"
    )


def _app_send_fn(app: Application, chat_id: int):
    async def send(text: str) -> None:
        await app.bot.send_message(chat_id=chat_id, text=text)
    return send


def _make_send_fn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async def send(text: str) -> None:
        if update.effective_message:
            await update.effective_message.reply_text(text)
    return send


async def _read_txt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> str | None:
    async def send(text: str) -> None:
        if update.effective_message:
            await update.effective_message.reply_text(text)
    return send


async def _handle_loom_link(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, repo: Any, user_id: int, url: str
) -> None:
    from urllib.parse import quote

    import httpx

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://www.loom.com/v1/oembed?url=" + quote(url, safe="")
            )
        duration = None
        if resp.status_code == 200:
            duration = float(resp.json().get("duration", 0.0)) or None
    except Exception:  # noqa: BLE001 - oEmbed failure must never kill the turn
        duration = None
    await repo.record_media_ref(
        user_id, "loom", "pending", loom_url=url, loom_duration_seconds=duration
    )
    await update.effective_message.reply_text(
        "Link received - your transcript still needs to arrive. "
        "Copy it from the Loom transcript panel and send it here (or upload as .txt)."
    )


async def _read_txt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> str | None:
    doc = update.effective_message.document
    tg_file = await doc.get_file()
    import io

    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)
    buf.seek(0)
    try:
        return buf.read().decode("utf-8", "replace")
    finally:
        buf.close()


# ---------------------------------------------------------------------------
# Typing + complete-message bridge (no streaming, Planning.md non-negotiable)
# ---------------------------------------------------------------------------
async def _send_with_typing(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, reply: str
) -> None:
    chat_id = update.effective_chat.id
    stop = asyncio.Event()

    async def pulse() -> None:
        while not stop.is_set():
            try:
                await ctx.bot.send_chat_action(chat_id, "typing")
            except Exception:  # noqa: BLE001 - cosmetic only
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=4.0)
            except TimeoutError:
                pass

    task = asyncio.create_task(pulse())
    try:
        # compose/execute already done by caller - short breathing room keeps
        # the typing indicator honest for the databases/API latency of the turn
        await asyncio.sleep(0.8)
        if "\n\n" in reply and len(reply) > 320:
            head, tail = reply.split("\n\n", 1)
            await update.effective_message.reply_text(head.strip())
            await asyncio.sleep(0.6)
            await update.effective_message.reply_text(tail.strip())
        else:
            await update.effective_message.reply_text(reply)
    finally:
        stop.set()
        task.cancel()


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("unhandled error in update handling", exc_info=ctx.error)


# ---------------------------------------------------------------------------
# Application bootstrap (used by main.py Phase 3)
# ---------------------------------------------------------------------------
async def post_init(app: Application) -> None:
    from bot.db.repo import open_repo

    repo = await open_repo(str(config.DATABASE_PATH))
    app.bot_data["repo"] = repo
    me = await app.bot.get_me()          # pre-flight 1: Telegram token
    logger.info("pre-flight ok: connected as @%s", me.username)

    # Phase 4 wiring: hourly sweep + re-scan waiting_24h users for their gate jobs
    from bot import scheduler
    app.bot_data.setdefault("send_fn", _app_send_fn(app))
    scheduler.schedule_hourly_sweep(app)
    waiting = await repo.get_users_in_stage("waiting_24h")
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta
    for wu in waiting:
        wst = await repo.get_user_state(wu.id)
        if wst.recording_submitted_at:
            base = _dt.fromisoformat(wst.recording_submitted_at)
            if base.tzinfo is None:
                base = base.replace(tzinfo=_UTC)
            fire = base + timedelta(hours=24)
            if fire > _dt.now(_UTC):
                scheduler.schedule_24h_gate_job(app, wu.id, fire)


async def post_shutdown(app: Application) -> None:
    repo: Any = app.bot_data.get("repo")
    if repo is not None:
        await repo.close()


def run() -> None:
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # NOTE: OpenAI pre-flight (client.models.list) happens at first LLM call in
    # POC scope; Telegram-side check is post_init's get_me.

    def _wire(app: Application) -> None:
        agent = build_agent(app)
        register_handlers(app, agent)

    # PTB permits handler registration after build; wire then run.
    _wire(app)
    app.run_polling(allowed_updates=Update.ALL_TYPES)
