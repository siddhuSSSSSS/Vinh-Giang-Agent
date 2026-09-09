"""Transport-agnostic conversation engine + the LLM-facing tool registry.

Phase 3 deliverable. Structure per Planning.md:
- handle_incoming(platform, platform_user_id, text) -> one full turn: classify
  input, assemble input_items from (summary chunks, recent window, new message),
  route model tier via get_active_synthesis_trigger, run the tool loop, persist.
- LLM-facing tools ONLY (genuine judgment calls): get_user_state,
  update_user_state, log_journal_entry, advance_stage. Mechanical facts
  (media received, days missed) are backend-only - never exposed to the model.
- advance_stage enforces the hardcoded STAGE_TRANSITIONS graph; illegal moves
  return a tool-error to the model (never applied, never a crash). The 24h gate
  is NOT model-bypassable.
- Tool-loop cap 7; on any hard failure the user gets one graceful line.
- Transcript-like text NEVER enters the rolling window (context-bloat guard).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from bot import config
from bot.db.repo import Repo, User, local_midnight_iso
from bot.gates import get_effective_day, is_24h_gate_cleared
from bot.llm.client import run_tool_loop
from bot.llm.persona import UserState, build_system_prompt

logger = logging.getLogger(__name__)

TOOL_LOOP_CAP = 7

STAGE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "onboarding": ("initial_recording",),
    "initial_recording": ("waiting_24h",),
    "waiting_24h": ("audit_day1",),
    "audit_day1": ("audit_day2",),
    "audit_day2": ("audit_day3",),
    "audit_day3": ("habit_selection",),
    "habit_selection": ("weekly_cycle",),
    "weekly_cycle": ("weekly_cycle",),
}

STAGES = tuple(STAGE_TRANSITIONS)

MAX_TEXT_FOR_WINDOW = 4000  # ordinary chat only; longer input is transcript-like
MIN_TRANSCRIPT_HINTS = 2

_TS_LINE = re.compile(r"^\s*(\d{1,2}:\d{2}|\[\d{1,2}:\d{2}\]|\d{1,2}:\d{2}:\d{2})\s")
LOOM_RE = re.compile(r"https?://(?:www\.)?loom\.com/(?:share|embed)/[A-Za-z0-9]+/?")


@dataclass
class TurnOutcome:
    """What one turn produced - the Telegram adapter sends `.reply`."""

    reply: str
    model_used: str
    reasoning_effort: str
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False  # tool loop hit the cap this turn
    error_reply: bool = False  # graceful fallback line was sent


# ---------------------------------------------------------------------------
# Input classification (context-bloat guardrail)
# ---------------------------------------------------------------------------
def classify_text(text: str) -> str:
    """'transcript' | 'summary' | 'chat'. Transcripts skip the window entirely.

    Length is one input among signals (long AND structural); a short-but-clearly
    timestamped paste is still a transcript, and a long multi-paragraph paste
    without timestamps is transcript-like too - err toward filing it rather than
    letting a big paste into the window.
    """
    stripped = text.strip()
    if not stripped:
        return "chat"
    hints = sum(1 for line in stripped.splitlines() if _TS_LINE.match(line))
    if hints >= MIN_TRANSCRIPT_HINTS:
        return "transcript"
    if len(stripped) <= MAX_TEXT_FOR_WINDOW:
        if _looks_like_summary(stripped):
            return "summary"
        return "chat"
    paras = sum(1 for line in stripped.splitlines() if line.strip())
    if paras >= 5:
        return "transcript"
    if _looks_like_summary(stripped):
        return "summary"
    return "transcript"  # over the chat ceiling and structurally neither: file it


def _looks_like_summary(text: str) -> bool:
    head = text.lower()[:300]
    markers = ("in this video", "the speaker", "summary:", "key points", "talking about")
    return any(m in head for m in markers)


# ---------------------------------------------------------------------------
# Model routing (single shared helper: Chat.md's unification decision)
# ---------------------------------------------------------------------------
def get_active_synthesis_trigger(
    stage: str,
    week_in_habit: int,
    effective_day: int,
    weekly_started_day: int | None,
    last_checkin_at: str | None,
    unresolved_missed_days: int,
) -> str | None:
    """One result drives BOTH the model tier and suggestion-mechanics emphasis."""
    from bot.gates import is_weekly_reeval_due

    if stage in ("audit_day3", "habit_selection"):
        return "habit_decision_synthesis"
    if stage == "weekly_cycle" and unresolved_missed_days >= 2:
        return "adaptive_replanning"
    if is_weekly_reeval_due(
        stage, weekly_started_day, effective_day, last_checkin_at
    ):
        return "weekly_reeval"
    return None


# ---------------------------------------------------------------------------
# Tool schema (LLM-facing, flat Responses shape)
# ---------------------------------------------------------------------------
def _tool(name: str, description: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": params,
        "strict": False,
    }


def build_tool_schemas() -> list[dict[str, Any]]:
    stage_enum = {"type": "string", "enum": list(STAGES)}
    nullable_str = {"type": ["string", "null"]}
    return [
        _tool(
            "get_user_state",
            "Read the user's current journey state (stage, habit, day).",
            {"type": "object", "properties": {}},
        ),
        _tool(
            "update_user_state",
            "Persist journey fields. Pass null for anything not set this call; "
            "only non-null fields are written.",
            {
                "type": "object",
                "properties": {
                    "current_habit": nullable_str,
                    "week_in_habit": {"type": ["integer", "null"]},
                    "motivation_summary": nullable_str,
                    "kaizen_reveal_shown": {"type": ["boolean", "null"]},
                    "timezone": nullable_str,
                },
                "required": [
                    "current_habit", "week_in_habit", "motivation_summary",
                    "kaizen_reveal_shown", "timezone",
                ],
            },
        ),
        _tool(
            "log_journal_entry",
            "Persist a meaningful moment NOW (struggles, reasons, wins, audit "
            "notes). Journal as phenomena occur, never from scrollback.",
            {
                "type": "object",
                "properties": {
                    "journal_type": {"type": "string", "enum": [
                        "exercise", "audit_note", "reflection", "transcript"
                    ]},
                    "content": {"type": "string"},
                    "completed": {"type": ["boolean", "null"]},
                    "reason": nullable_str,
                },
                "required": ["journal_type", "content", "completed", "reason"],
            },
        ),
        _tool(
            "advance_stage",
            "Move to the next journey stage only when the user genuinely "
            "completed the current one. Only adjacent forward moves are legal; "
            "the 24-hour gate cannot be bypassed.",
            {
                "type": "object",
                "properties": {"new_stage": stage_enum},
                "required": ["new_stage"],
            },
        ),
    ]


def _utc_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------
class AgentCore:
    def __init__(self, repo: Repo, llm_client: Any) -> None:
        self.repo = repo
        self.client = llm_client
        self.tools = build_tool_schemas()

    # -- prompt state assembly (all async) -----------------------------------
    async def _persona_state(self, user: User) -> UserState:
        st = await self.repo.get_user_state(user.id)
        unresolved = await self.repo.count_unresolved_missed_days(user.id)
        rec = await self.repo._fetchone(
            "SELECT 1 AS x FROM media_refs WHERE user_id=? LIMIT 1", (user.id,)
        )
        five_rows = await self.repo._fetchall(
            "SELECT content FROM journal_entries WHERE user_id=? AND epoch=? AND"
            " type='reflection' AND content LIKE 'five words: %'",
            (user.id, user.epoch),
        )
        words = [
            r["content"].split(":", 1)[1].strip()[:24]
            for r in five_rows
            if ":" in r["content"]
        ]
        return UserState(
            name=user.name,
            current_stage=st.current_stage,
            effective_day=get_effective_day(user),
            current_habit=st.current_habit,
            week_in_habit=st.week_in_habit,
            timezone=user.timezone,
            five_words=words[:5],
            motivation_summary=st.motivation_summary,
            recent_missed_days=unresolved,
            kaizen_reveal_shown=st.kaizen_reveal_shown,
            has_recording=rec is not None,
        )

    # -- transcript/summary submission path ----------------------------------
    async def _attach_media_text(
        self, user: User, eff_day: int, kind: str, text: str
    ) -> TurnOutcome:
        mid = await self.repo.record_media_ref(
            user.id, "loom", "pending",
            transcript_text=text if kind == "transcript" else None,
            summary_text=text if kind == "summary" else None,
        )
        await self.repo.log_journal_entry(
            user.id, eff_day, "transcript", f"[{kind} attached - {len(text)} chars]"
        )

        # If link + transcript are both present, compute metrics (Phase 5).
        row = await self.repo._fetchone(
            "SELECT * FROM media_refs WHERE id=?", (mid,)
        )
        metrics_line = ""
        if (
            row is not None
            and row["kind"] == "loom"
            and row["transcript_text"]
            and not row["processed"]
        ):
            from bot.analysis.loom import analyze_loom_submission

            result = await analyze_loom_submission(
                row["transcript_text"], oembed_duration=row["loom_duration_seconds"]
            )
            eid = await self.repo.log_journal_entry(
                user.id, eff_day, "transcript",
                f"[metrics computed by code - {len(result.metrics)} metrics]",
            )
            await self.repo.record_entry_metrics(eid, result.metrics)
            await self.repo.mark_media_processed(mid)
            parts = [
                f"{name.replace('_', ' ')}: {value:g}"
                for name, value in result.metrics.items()
            ]
            metrics_line = " Here's what came out of it - " + ", ".join(parts) + "."
            for note in result.notes:
                metrics_line += f" ({note})"

        st = await self.repo.get_user_state(user.id)
        base_reply = (
            "Transcript received and attached to your recording - thank you. "
            "I'll dig into the words with you once we're past the 24-hour hold."
            if st.current_stage in ("initial_recording", "waiting_24h")
            else "Transcript received and filed for this week's numbers."
        )
        return TurnOutcome(
            reply=base_reply + metrics_line,
            model_used=config.OPENAI_MODEL,
            reasoning_effort="none",
            tool_calls_made=[],
        )

    # -- the turn ------------------------------------------------------------
    async def handle_incoming(
        self, platform: str, platform_user_id: str, text: str
    ) -> TurnOutcome:
        user = await self.repo.get_or_create_user(platform, platform_user_id)
        user = await self.repo.get_user(user.id)
        assert user is not None
        state = await self.repo.get_user_state(user.id)
        eff_day = get_effective_day(user)

        kind = classify_text(text)
        if kind in ("transcript", "summary"):
            return await self._attach_media_text(user, eff_day, kind, text)

        # defensive: a bare Loom link arriving through the core (the adapter
        # normally catches it) is still third-submission data, never chat
        m = LOOM_RE.search(text)
        if m and kind == "chat" and len(text.strip()) < 200:
            loom_url = m.group(0)
            try:
                import httpx

                duration = None
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.get(
                        "https://www.loom.com/v1/oembed?url=" + quote(loom_url, safe="")
                    )
                if resp.status_code == 200:
                    duration = float(resp.json().get("duration", 0.0)) or None
            except Exception:  # noqa: BLE001
                duration = None
            await self.repo.record_media_ref(
                user.id, "loom", "pending", loom_url=loom_url,
                loom_duration_seconds=duration,
            )
            return TurnOutcome(
                reply="Link received - your transcript still needs to arrive.",
                model_used=config.OPENAI_MODEL,
                reasoning_effort="none",
                tool_calls_made=[],
            )

        # ordinary chat: mechanical bookkeeping first (engagement + seen)
        await self.repo.record_daily_engagement(user.id, eff_day)
        await self.repo.mark_message_seen(user.id, _utc_iso())
        await self.repo.append_conversation_message(user.id, "user", text)

        # context: append-only summary chunks + recent window (transcripts never here)
        chunks = await self.repo.get_summary_chunks(user.id)
        recent = await self.repo.get_recent_messages(user.id, limit=40)
        input_items: list[dict[str, Any]] = [
            {"role": "assistant", "content": f"(earlier, summarized) {c}"} for c in chunks
        ]
        input_items.extend({"role": m["role"], "content": m["content"]} for m in recent)

        # routing via the single shared helper
        unresolved = await self.repo.count_unresolved_missed_days(user.id)
        trigger = get_active_synthesis_trigger(
            state.current_stage,
            state.week_in_habit,
            eff_day,
            state.weekly_cycle_started_effective_day,
            state.last_checkin_at,
            unresolved,
        )
        model = config.OPENAI_MODEL_ANALYSIS if trigger else config.OPENAI_MODEL
        effort = "none"

        # ephemeral metric-trend note on synthesis turns only (never persisted)
        if trigger:
            trend = await self.repo.get_metric_trend(user.id, "filler_word_count")
            if trend:
                input_items.append({
                    "role": "assistant",
                    "content": "(system note, this turn only) filler_word_count "
                    "trend: " + ", ".join(f"day {d}: {v:g}" for d, v in trend),
                })

        instructions = build_system_prompt(await self._persona_state(user))

        executors = self._build_executors(user, eff_day)
        tool_trace: list[dict[str, Any]] = []
        try:
            final_text, ephemeral = await run_tool_loop(
                self.client,
                input_items=input_items,
                tools=self.tools,
                instructions=instructions,
                executors=executors,
                reasoning_effort=effort,
                model=model,
                prompt_cache_key=f"{platform}:{platform_user_id}",
                max_iterations=TOOL_LOOP_CAP,
            )
            tool_trace = [
                {"call_id": it.get("call_id")}
                for it in ephemeral or []
                if it.get("type") == "function_call_output"
            ]
        except Exception:
            logger.exception("turn failed for user %s", user.id)
            return TurnOutcome(
                reply="Hit a snag there - let's try that again.",
                model_used=model,
                reasoning_effort=effort,
                tool_calls_made=tool_trace,
                error_reply=True,
            )

        reply = (final_text or "").strip() or "I'm here - say that again?"
        await self.repo.append_conversation_message(user.id, "assistant", reply)
        return TurnOutcome(
            reply=reply,
            model_used=model,
            reasoning_effort=effort,
            tool_calls_made=tool_trace,
        )

    # -- executor registry (closures over one user/turn) -----------------------
    def _build_executors(self, user: User, eff_day: int) -> dict[str, Any]:
        repo = self.repo

        async def get_user_state() -> str:
            st = await repo.get_user_state(user.id)
            u = await repo.get_user(user.id)
            five = await repo._fetchall(
                "SELECT content FROM journal_entries WHERE user_id=? AND epoch=? AND"
                " type='reflection' AND content LIKE 'five words: %'",
                (user.id, u.epoch if u else 0),
            )
            words = [
                r["content"].split(":", 1)[1].strip()[:24] for r in five if ":" in r["content"]
            ]
            return json.dumps({
                "stage": st.current_stage,
                "habit": st.current_habit,
                "week_in_habit": st.week_in_habit,
                "effective_day": get_effective_day(u) if u else eff_day,
                "five_words": words[:5],
                "motivation_summary": st.motivation_summary,
            })

        async def update_user_state(
            current_habit=None,
            week_in_habit=None,
            motivation_summary=None,
            kaizen_reveal_shown=None,
            timezone=None,
        ) -> str:
            # empty strings = 'not provided this call' (same as null in the
            # nullable-but-required schema contract); they never overwrite data
            fields = {
                k: v
                for k, v in {
                    "current_habit": current_habit,
                    "week_in_habit": week_in_habit,
                    "motivation_summary": motivation_summary,
                    "kaizen_reveal_shown": kaizen_reveal_shown,
                    "timezone": timezone,
                }.items()
                if v is not None and v != ""
            }
            before_tz = (await repo.get_user(user.id)).timezone
            await repo.update_user_state(user.id, **fields)
            if timezone is not None and before_tz is None:
                await _realign_day_zero_once(repo, user.id, timezone)
            return "saved"

        async def log_journal_entry(
            journal_type: str, content: str, completed=None, reason=None
        ) -> str:
            fresh = await repo.get_user(user.id)
            await repo.log_journal_entry(
                user.id, get_effective_day(fresh), journal_type, content, completed, reason
            )
            return "logged"

        async def advance_stage(new_stage: str) -> str:
            st_now = await repo.get_user_state(user.id)
            current = st_now.current_stage
            allowed = STAGE_TRANSITIONS.get(current, ())
            if new_stage not in allowed:
                return json.dumps({
                    "error": (
                        f"illegal transition {current!r} -> {new_stage!r}. "
                        f"Allowed next: {list(allowed)}."
                    )
                })
            if current == "waiting_24h" and new_stage == "audit_day1":
                fresh_user = await repo.get_user(user.id)
                if not is_24h_gate_cleared(
                    st_now.recording_submitted_at,
                    st_now.recording_submitted_effective_day,
                    get_effective_day(fresh_user),
                ):
                    return json.dumps({
                        "error": (
                            "the 24-hour hold is still on - the user cannot move "
                            "to the audit yet. Warmly explain WHY the wait "
                            "protects their objectivity instead."
                        )
                    })
            if current == "habit_selection" and new_stage == "weekly_cycle":
                await repo.update_user_state(
                    user.id, weekly_cycle_started_effective_day=eff_day
                )
            await repo.update_user_state(user.id, current_stage=new_stage)
            return f"stage is now {new_stage}"

        return {
            "get_user_state": get_user_state,
            "update_user_state": update_user_state,
            "log_journal_entry": log_journal_entry,
            "advance_stage": advance_stage,
        }


async def _realign_day_zero_once(repo: Repo, user_id: int, tz_name: str) -> None:
    """One-time day-boundary realignment: the FIRST time a timezone is set,
    day_zero_at moves to that user's most recent local midnight (Planning.md).
    Later timezone changes must NOT shift existing day-numbered history."""
    user = await repo.get_user(user_id)
    if user is None:
        return
    target = local_midnight_iso(tz_name)
    # only when the anchor hasn't already been realigned to a local midnight
    # (heuristic: current anchor carries the same hour-check). Realigned
    # anchors are UTC midnights of tz midnight; comparing iso prefixes is exact.
    if user.day_zero_at and _is_tz_midnight(user.day_zero_at, tz_name):
        return
    await repo._execute(
        "UPDATE users SET day_zero_at=? WHERE id=?", (target, user_id)
    )


def _is_tz_midnight(day_zero_at: str, tz_name: str) -> bool:
    """True if day_zero_at IS a local midnight of tz_name (already realigned)."""
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    try:
        base = datetime.fromisoformat(day_zero_at)
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        local = base.astimezone(ZoneInfo(tz_name))
        return local.hour == 0 and local.minute == 0 and local.second == 0
    except Exception:  # noqa: BLE001 - unknown tz: treat as not realigned
        return False
