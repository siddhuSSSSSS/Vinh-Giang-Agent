"""Proactive scheduling: the hourly sweep + one-shot 24h-gate jobs.

Phase 4 deliverable per Planning.md. The full rule set, strictly ordered:

step 0  reengagement_nudge   - early stages, 1-day fuse, capped at 3, resets on
                               re-engagement (checked BEFORE the weekly-cycle
                               logic below; waiting_24h deliberately excluded)
step 1  missed-day flag      - weekly_cycle only, NOT on the transition day
                               (guard: day - 1 > weekly_cycle_started day),
                               keyed on daily_engagement rows
step 2  missed_day_nudge     - 2+ unresolved missed days and none sent yet;
                               resolve_missed_day later resets the flag
step 3  weekly_reeval_prompt - is_weekly_reeval_due (derived + same-day gate)
step 4  daily_checkin        - weekly_cycle, once/day, only if no organic
                               message that day
step 5  None

Dedup: users.last_sweep_day is written unconditionally after every real sweep
execution for that user (post_init re-creates jobs on restart; a restart within
the same local hour must not double-nudge).

All four proactive reasons funnel into initiate_conversation, which (a) dedups
reasons preserving order, (b) composes ONE message in the engine's voice via the
LLM - batched, never a burst - and (c) sends through the normal complete-message
bridge. /advance collects the same reasons day-by-day so simulated days fire
exactly what real days would, then one consolidated message.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from bot import config
from bot.gates import get_effective_day, is_weekly_reeval_due

logger = logging.getLogger(__name__)

SweepReason = Literal[
    "reengagement_nudge", "missed_day_nudge", "weekly_reeval_prompt", "daily_checkin"
]

EARLY_STAGES = frozenset({
    "onboarding", "initial_recording", "audit_day1", "audit_day2",
    "audit_day3", "habit_selection",
})  # waiting_24h is an intentional wait - excluded by design

REENGAGEMENT_CAP = 3


# ---------------------------------------------------------------------------
# The shared per-user daily checks (called by BOTH the sweep and /advance)
# ---------------------------------------------------------------------------
async def run_daily_checks_for_user(
    repo: Any, user: Any, day: int
) -> SweepReason | None:
    """One user's ordered daily checks at effective `day`. Exactly ONE reason
    max per call (at-most-one proactive nudge per sweep pass)."""
    state = await repo.get_user_state(user.id)

    # step 0 - early-stage re-engagement (short fuse, capped)
    if state.current_stage in EARLY_STAGES and day >= 1:
        engaged_yesterday = await repo.has_engagement_on_day(user.id, day - 1)
        if not engaged_yesterday and state.reengagement_nudge_count < REENGAGEMENT_CAP:
            await repo.update_user_state(
                user.id, reengagement_nudge_count=state.reengagement_nudge_count + 1
            )
            return "reengagement_nudge"

    # step 1 - missed-day flag (weekly_cycle only, never the transition day)
    if (
        state.current_stage == "weekly_cycle"
        and state.weekly_cycle_started_effective_day is not None
        and day - 1 > state.weekly_cycle_started_effective_day
        and not await repo.has_engagement_on_day(user.id, day - 1)
    ):
        await repo.flag_missed_day(user.id, day - 1)

    # step 2 - missed-day nudge (2+ unresolved, send once until resolved)
    unresolved = await repo.count_unresolved_missed_days(user.id)
    if unresolved >= 2 and not state.adaptive_nudge_sent:
        await repo.update_user_state(user.id, adaptive_nudge_sent=True)
        return "missed_day_nudge"

    # step 3 - weekly re-evaluation boundary (derived, once per boundary day)
    if is_weekly_reeval_due(
        state.current_stage,
        state.weekly_cycle_started_effective_day,
        day,
        state.last_checkin_at,
    ):
        await repo.update_user_state(
            user.id, last_checkin_at=_now_iso(),
            last_daily_checkin_sent_day=day,  # boundary handled: no plain checkin too
        )
        return "weekly_reeval_prompt"

    # step 4 - plain daily check-in (weekly_cycle, once per day, skip if organic
    # message already landed that day, and never on a re-eval boundary day)
    if state.current_stage == "weekly_cycle":
        last_checkin_day = state.last_daily_checkin_sent_day
        if last_checkin_day == day:
            return None
        if await repo.has_engagement_on_day(user.id, day):
            return None  # organic message today - don't also check in
        await repo.update_user_state(user.id, last_daily_checkin_sent_day=day)
        return "daily_checkin"

    return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Reason batching -> ONE consolidated proactive message
# ---------------------------------------------------------------------------
def dedupe_reasons(reasons: list[SweepReason]) -> list[SweepReason]:
    """Preserving first-seen order (Chat.md: /advance can collect the same reason
    on several simulated days; the composed message would read bizarre/repetitive)."""
    seen: set[str] = set()
    out: list[SweepReason] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


REASON_PROMPTS: dict[str, str] = {
    "reengagement_nudge": (
        "they went quiet during an early part of the journey - reach out warmly, "
        "no guilt, one light question"
    ),
    "missed_day_nudge": (
        "they've missed two or more days mid-week - WHY before anything smaller: "
        "ask what happened with genuine curiosity first"
    ),
    "weekly_reeval_prompt": (
        "this week closed - ask for a fresh short improvised video and their own "
        "read first, then surface the numbers"
    ),
    "daily_checkin": (
        "brief daily presence in the weekly cycle - a light, short check-in"
    ),
}


async def initiate_conversation(
    send_fn: Any,
    llm_client: Any,
    persona_state: Any,
    reasons: list[SweepReason],
    *,
    platform: str,
    platform_user_id: str,
) -> str:
    """Compose ONE proactive message covering all (deduped) reasons, then send.

    `send_fn(text)` is the adapter's complete-message sender; `persona_state`
    is the UserState-shaped prompt state. Never templates - the LLM composes.
    """
    unique = dedupe_reasons(reasons)
    if not unique:
        return ""
    context_block = "; ".join(
        f"{reason} ({REASON_PROMPTS[reason]})" for reason in unique
    )
    instructions = (
        "You are composing a PROACTIVE check-in message (no user message prompted "
        "this) as Vin's sidekick. Current reason(s), first is primary:\\n"
        f"{context_block}\\n\\n"
        "Rules: one short warm message, no bullet points, no guilt, never more "
        "than one question._today's date does not go in the text."
    )
    from bot.llm.persona import build_system_prompt

    full_instructions = build_system_prompt(persona_state)
    result = await llm_client.run_turn(
        input_items=[{
            "role": "assistant",
            "content": f"(internal note) proactive reasons this pass: {context_block}. "
            "Write the message now:",
        }],
        tools=[],
        instructions=full_instructions + "\n\n" + instructions,
        reasoning_effort="none",
        model=config.OPENAI_MODEL,
        prompt_cache_key=f"{platform}:{platform_user_id}",
    )
    text = (result.text or "").strip()
    if not text:
        logger.warning("proactive composition returned empty; skipping send")
        return ""
    await send_fn(text)
    return text


# ---------------------------------------------------------------------------
# Hourly sweep job + one-shot 24h-gate jobs (PTB wiring)
# ---------------------------------------------------------------------------
def schedule_hourly_sweep(app: Any) -> None:
    """Repeating hourly tick: iterate verified users, act only when it's their
    local-hour AND last_sweep_day != today's effective day."""
    app.job_queue.run_repeating(hourly_sweep, interval=3600, name="hourly_sweep")


async def hourly_sweep(context: Any) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    repo = context.application.bot_data["repo"]
    agent = context.application.bot_data["agent"]
    send_fn = context.application.bot_data["send_fn"]

    for user in await repo.get_verified_users():
        # timezone-aware: only proceed when the user's local hour matches
        tz_name = user.timezone
        try:
            now_local = (
                datetime.now(ZoneInfo(tz_name)) if tz_name else datetime.now()
            )
        except Exception:  # noqa: BLE001 - unknown tz falls back to server-local
            now_local = datetime.now()
        if now_local.hour != config.DAILY_TICK_HOUR:
            continue
        day = get_effective_day(user)
        if user.last_sweep_day == day:
            continue  # restart dedup - already processed this user-day

        reason = await run_daily_checks_for_user(repo, user, day)
        await repo.record_sweep_run(user.id, day)  # ALWAYS, reason or not
        if reason is not None:
            persona_state = await agent._persona_state(user)
            await initiate_conversation(
                send_fn,
                agent.client,
                persona_state,
                [reason],
                platform="telegram",
                platform_user_id=user.platform_user_id,
            )


def schedule_24h_gate_job(app: Any, user_id: int, fire_at: Any) -> None:
    """One-shot re-scan job for the waiting_24h -> audit_day1 boundary."""
    app.job_queue.run_once(
        check_24h_gate,
        when=fire_at,
        name=f"24h_gate_{user_id}",
        data={"user_id": user_id},
    )


async def check_24h_gate(context: Any) -> None:
    """When the 24h hold ends: nudge the user that day 1 of the audit is open.
    Re-scan on restart is Phase 4 wiring via post_init (job re-creation)."""
    repo = context.application.bot_data["repo"]
    user_id = context.job.data.get("user_id")
    user = await repo.get_user(user_id)
    if user is None:
        return
    state = await repo.get_user_state(user_id)
    if state.current_stage != "waiting_24h":
        return  # moved on already (or /advance ran)
    send_fn = context.application.bot_data["send_fn"]
    agent = context.application.bot_data["agent"]
    persona_state = await agent._persona_state(user)
    await initiate_conversation(
        send_fn,
        agent.client,
        persona_state,
        ["reengagement_nudge"],  # warm, light - 'day 1 is ready when you are'
        platform="telegram",
        platform_user_id=user.platform_user_id,
    )
