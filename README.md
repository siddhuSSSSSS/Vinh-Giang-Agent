# Vin's Sidekick — A Communication Coaching Agent on Telegram

A Telegram agent that turns Vinh Giang's "30-Day Communication Mirror" video from a
one-time watch into a coaching relationship that actually runs the plan with you.

**Status:** design complete; implementation in progress — Phases 0.5–3 done
(95 tests passing), Phase 4 next. See [Status & Timeline](#status--timeline).

---

## 1. The problem

The source video contains a genuinely good method — record yourself, wait 24 hours,
audit the recording across three days, pick one habit, work it for a week, re-evaluate.
But it's a 10-minute video containing a 30-day plan. You watch it, you nod, you close
the tab. Nothing happens.

The gap isn't information. It's that:

- there's no action wrapped around the plan
- nothing brings you back to the reference on day 4, day 11, day 23
- nobody notices when you miss two days in a row, and nothing adapts when you do

So the goal isn't a video summariser or a generic "video → plan" converter. It's a
single agent that **knows this one video the way an assistant to the creator would**,
and carries a specific user through it over 30+ days — proactively, adaptively, and
without sounding like a machine.

**Success criterion:** after 30 days, a measurable and self-recognised improvement in
how the user communicates.

---

## 2. What the agent actually does

The agent hard-codes Vinh's method as a state machine. The user never supplies the
video or the framework — the agent already knows it.

```
onboarding  →  initial_recording  →  waiting_24h  →  audit_day1
     →  audit_day2  →  audit_day3  →  habit_selection  →  weekly_cycle ⟲
```

| Stage | What happens |
|---|---|
| **Onboarding** | An extended, one-question-at-a-time conversation. Name, what they want to improve, a *specific story* of a time communication went wrong, the workbook's "five words you want people to say about you," and their timezone. Not a form — the agent keeps going until it has a real pattern, not a generic goal. |
| **Initial recording** | The agent generates **five personalised prompt questions** based on what surfaced in onboarding — deliberately shaped to provoke a mild version of whatever the user described. The user records one improvised 5–20 minute video and sends it. |
| **24-hour wait** | Enforced server-side. Watching yourself immediately makes you hypercritical; a day's distance makes you objective. If the user tries to skip ahead, the agent explains *why* the wait matters rather than reporting an error. |
| **Day 1 — Auditory** | Screen turned away, listen only. Rate of speech, volume, pitch, melody, tonality, pauses. The agent keeps the conversation strictly on sound; if the user drifts to appearance, it gently defers that to tomorrow. |
| **Day 2 — Visual** | Sound off, watch only. Facial expressions, gestures, eye contact. The agent reply-quotes their original video so it's one tap away. |
| **Day 3 — Transcription** | The synthesis day. The agent has the real transcript with filler words preserved, plus computed metrics, and ties auditory + visual + textual signals together into 2–3 candidate habits. |
| **Habit selection** | The user picks exactly one thing. |
| **Weekly cycle** | A behavioural trigger is designed together (Vinh's phone-wallpaper hack, or an alternative). Daily light-touch presence. At week's end, a fresh 5-minute video and a re-evaluation. If no improvement, **the default is to repeat the same habit** — 90% of people need three to four weeks per behaviour. Switching early is available but never the agent's suggestion. |
| **Lifelong Kaizen** | At the first habit transition, the agent reveals — warmly, as good news — that the "30-day plan" framing was a container. Real mastery is continuous. Delivered alongside a **measured before/after comparison** of the user's own numbers. |

### Adaptive behaviour

- **Missed days are detected on engagement**, not task completion — Vinh's weekly method
  is a passive trigger, not a daily chore, so "did they show up at all" is the honest signal.
- **Two missed days trigger a replanning conversation** that asks *why* before offering
  anything smaller.
- **Early-stage silence** (onboarding through habit selection — the highest drop-off window)
  gets a shorter one-day fuse, capped at three nudges so it never becomes nagging.
- **All proactive messages are composed by the model in context**, never templated, and
  batched into one coherent message rather than a burst of texts.

---

## 3. How it's designed to feel

This is the part I consider the actual product. The method is Vinh's; the behaviour is
the engineering.

The persona is built on nine principles, grounded where possible in Motivational
Interviewing and habit-formation research rather than invented:

1. **The agent's job is for the user to succeed** — the plan bends, always.
2. **Never assume dishonesty.** If they say they've improved, that's taken as sincere.
   But the data is still always shown — trust governs how their *interpretation* is
   treated, never whether they get to see the numbers.
3. **One habit at a time.** No parallel workstreams.
4. **The agent leads, the user decides.** It proposes 2–3 grounded options at every
   decision point; it never proceeds without an explicit choice.
5. **Warm, non-judgmental, "Vin's sidekick"** — borrowing his tone, not impersonating him.
6. **Everything meaningful gets journalled** as it's said, not left in chat scrollback.
7. **Why before shrink.** If someone misses a session, the agent asks what happened with
   real curiosity *before* offering an easier version. Never a shortcut past the question.
8. **Observer, not diagnostician.** It reflects what it notices ("I noticed you used 'and'
   a lot") and asks whether that lands, rather than asserting ("you have a filler-word
   problem"). If the user disagrees, it drops it. The system prompt explicitly names MI's
   **"righting reflex"** — the urge to jump in and fix — as a behaviour to avoid.
9. **Affirmation before gaps, and never generic.** No "Great job!" Instead: effort praise,
   or reflecting a past success the user themselves described, or tying progress back to
   their own five words — always grounded in something specific to this person.

Every decision point runs **Elicit → Provide → Elicit**: ask what they think first, ask
permission before offering the agent's own read, then ask how it lands.

Two smaller choices in service of the same goal: **no token streaming** (people texting
you don't stream — typing indicator, then a complete message), and replies occasionally
split into two short bubbles for natural pacing.

---

## 4. Architecture

Python 3.12, `python-telegram-bot` (async), OpenAI Responses API, SQLite via `aiosqlite`.
No framework beyond that — the tool-calling loop is written by hand so the state model
stays fully visible.

```
bot/
├── main.py          # entry: fail-fast config, then polling (post_init pre-flight)
├── config.py        # env schema, fail-fast validation, placeholder detection
├── handlers.py      # thin Telegram adapter: passcode gate, /advance, /reset, /wipe,
│                    #   Loom-link + .txt routing, typing + complete-message bridge
├── agent_core.py    # transport-agnostic engine: STAGE_TRANSITIONS enforcement,
│                    #   LLM-facing tool registry (4 tools), transcript-vs-chat
│                    #   classification, synthesis-trigger routing, 7-cap tool loop
├── gates.py         # get_effective_day (canonical clock), 24h gate, weekly re-eval
├── scheduler.py     # Phase 4: hourly sweep + one-shot 24h-gate jobs (stub now)
├── llm/             # client.py (Responses API client + tool loop, SDK-shape
│                    #   verified), persona.py (knowledge base + 9 principles + stage
│                    #   scoping + bounded state summary, <2500 static tokens)
├── db/              # schema.sql (9 tables, epoch-stamped), repo.py (aiosqlite,
│                    #   WAL + foreign_keys + busy_timeout, pending-merge media refs)
├── analysis/        # Phase 5: loom.py (oEmbed + parser, spike-proven),
│                    #   voice_fallback.py (rare ASR branch), base.py (interface)
└── adapters/        # placeholder for a future non-Telegram channel

tests/               # 95 tests: unit, scripted scenarios, Gherkin feature files
└── gherkin/         # regressions.feature, nfr.feature, scenarios.feature, phase3.feature
```

**Notable design decisions:**

- **Least-agency tool surface.** The model only gets tools representing genuine judgment
  calls (`advance_stage`, `update_user_state`, `log_journal_entry`, `get_user_state`).
  Mechanical facts — was a file received, was a day missed — are decided by code, never
  inferred by the model. `advance_stage` validates against a hard-coded transition graph,
  so neither a model mistake nor a prompt-injection attempt can skip a stage.
- **One canonical clock.** `get_effective_day()` = real elapsed days since a per-user
  anchor, plus a manual offset that `/advance` bumps. Real time advances a user's day
  automatically; demo time uses the same formula. There is no second definition of "day"
  anywhere in the codebase.
- **Three-tier memory.** A bounded static system prompt, a short structured state summary,
  and a rolling conversation window backed by an append-only summary buffer — so context
  doesn't grow unbounded over a 30-day relationship. Facts live in structured storage,
  extracted as they're said, not in raw scrollback.
- **Metrics are computed in code, never asked of the model.** Filler counts, words per
  minute, pause detection and repetitions are deterministic arithmetic. Models are bad at
  counting; SQL and regex are not.
- **Two-tier model routing.** Routine turns run on a fast, cheap model. The rare
  high-stakes synthesis moments — Day-3 audit, habit decisions, weekly re-evaluation,
  adaptive replanning — run on a stronger one. This is a quality decision; the cost
  difference is a rounding error.

**Cost:** roughly **$1–1.50 per user per month**, transcription being the largest line
item. Total spend across the entire POC will be under $10.

---

## 5. Judgment calls — the reasoning, not just the outcome

You said you were more interested in the calls than the code, so these are written down
explicitly rather than left implicit.

**Memory: SQLite + rolling summary, not Obsidian/Mem0/Supermemory.**
Those are built for semantic retrieval over unstructured notes. This project's actual
need is structured per-user state, deterministic metrics, and a bounded conversation
window — a relational shape, not a search shape. Adding a vector layer would be
solving a problem I don't have.

**Agent leads vs. user leads — resolved in favour of your brief.**
My original notes argued the agent should never suggest anything upfront and should give
the user complete autonomy. Your brief asks for adaptive planning and proactive
messaging. These genuinely conflict, and I went with yours: an agent that never suggests
puts all the cognitive load on someone who came here *because* they don't know how to
structure this. The compromise is Principle 4 — the agent always leads with grounded
options, the user always decides.

**Scope honesty.** "Full user autonomy over the plan" is false by construction. Vinh's
framework is hard-coded. What the user genuinely chooses is *which* habit and *what*
exercise. The agent says this plainly rather than pretending otherwise.

**Trust vs. the mirror.** My notes said the user's self-assessment should be conclusive.
Taken literally, a user could self-report improvement forever and never improve — which
defeats the entire "communication mirror" premise. Resolved: the numbers are *always*
shown; what those numbers *mean* is the user's call.

**Responses API over Chat Completions** (reversed mid-planning). Chat Completions can't
do tool calling with `reasoning_effort` above `"none"`, and our tools fire every turn —
so staying there would have permanently blocked the documented quality-escalation path.

**Loom link + transcript, not video uploads.** Day 2's visual review needs real footage,
but Telegram round video notes cap at 60 seconds and the Bot API caps downloads at 20MB.
The Loom pivot (see Planning.md) removed the whole local-server/ffmpeg/Whisper pipeline:
the user records on Loom and sends a share link + pasted transcript - no video ever
reaches the bot, no local server, no per-minute ASR cost. One recording covers all three
audit days.

---

## 6. Deliberately out of scope

- **Full audio/visual analysis** — pitch, pace, volume, eye contact, gestures. Stubbed
  behind a `MediaAnalyzer` interface, with every raw file reference persisted so old
  recordings can be reprocessed later without re-collecting data.
- **Clinical language.** Prolongations and blocks (true stuttering markers) need audio
  signal analysis and aren't reliably detectable from a transcript. The agent measures
  ordinary disfluencies and never uses the word "stutter" or asserts any fluency-disorder
  label — it isn't qualified to, and mislabelling would be harmful.
- **Multi-channel.** Telegram only, but `agent_core` is transport-agnostic and users are
  keyed on `(platform, platform_user_id)`, so a second adapter is additive.
- **Production hardening.** Single-process, local polling, no migration framework.

---

## 7. Status & timeline

**Design: complete.** The plan has been through four review passes; the remaining
unknowns are empirical rather than analytical.

**Next, in order:**

| | Work | Est. | Status |
|---|---|---|---|
| 0.5 | Loom transcript-parsing spike | ~½ day | ✅ DONE — all gates passed, real recording, see `Phase-0.5-Spike-Results.md` |
| 0 | Scaffolding, config, CI hygiene | ~½ day | ✅ DONE — pushed, 8/8 tests, ruff clean, Python 3.12 venv |
| 1 | LLM client + persona (Responses API) | ~1 day | ✅ DONE — 22/22 tests, shapes verified vs SDK 3.11.0 |
| 2 | Schema + repo (parallel with 1) | ~½ day | ✅ DONE — 19 repo tests + 3 scripted scenarios, epoch semantics verified |
| 3 | Conversation engine, state machine, tool registry, handlers | ~1.5 days | ✅ DONE — 22 engine tests incl. gherkin suite; graph + 24h gate enforced server-side |
| 4 | Proactive scheduling, hourly sweep, `/advance` checks | ~1 day | ✅ DONE — 26 rule-engine + gherkin tests; consolidated proactive messages |
| 5 | Loom parsing + metrics + voice fallback | ~½ day | ✅ DONE — spike numbers reproduced exactly; 18 tests; fail-soft verified |
| 6 | Demo polish, runbook, error handling | ~½ day | ✅ DONE — OpenAI pre-flight wired, loggers pinned, runbook + judgment calls in README, 7 tests |
| 7 | Research-backed coaching upgrades (see §7 note) | ~1 day | queued — Planning.md Phase 7 |

**Test count: 159 passing** (unit + scripted scenarios + Gherkin regression/NFR
suites), ruff clean throughout. **All planned phases (0.5–6) complete.**
Only external dependency for a live demo: the OpenAI + Telegram credentials.

The Phase 0.5 spike ran against a real Loom recording: oEmbed resolves `duration` even
at the account's default sharing visibility, desktop copy-paste preserves `M:SS`
paragraph timestamps, the corrected articulation-rate pause estimator produced no
cancelling residuals, and the fail-soft path degrades exactly as designed. Every
downstream assumption is now confirmed - nothing below is blocked.

**One risk worth naming up front:** `whisper-1` is the only OpenAI model supporting
word-level timestamps, and it was deprecated on 26 Aug 2026 (shutdown Feb 2027). After
the Loom pivot it's scoped to the rare voice-fallback "full metrics" branch only, so
it's fine for this POC. The transcription module returns a provider-neutral shape so
Deepgram or AssemblyAI can be dropped in by changing one file.

**Research round (Sept 2026, completed):** compared our prompts and code against recent
evidence — Bloom (CHI 2026, N=54 RCT), a motivation-aware MI coaching framework (CHI
2026, N=140), an N=543 goal-setting chatbot RCT (arXiv), and a standalone primary-care
MI-chatbot RCT. Immediate changes adopted: **self-compassion on misses** and a
"what made the good days work" follow-up baked into Principle 9; **readiness-gated
coaching** (reflection questions for uncertain users, planning for action-ready ones) in
the weekly-cycle instructions; the weekly re-eval trend framed as **where-you-were vs
where-you-wanted-to-be**; `ChatAction.TYPING` constant; a **config-level reasoning-effort
dial** (`ANALYSIS_REASONING_EFFORT`) so the documented quality-escalation chain is
reachable without code changes; and missed-day replanning messages routed through the
**elevated model tier** (they're trust-critical synthesis moments). Deliberately rejected
on the same evidence: more metrics (the lever is mindset, not data), safety-benchmark
work, and self-correction frameworks. The data-backed behavioral capabilities that
remain — implementation-intention capture (when/where), persisted readiness states, and
the companion on-device filler counter — are queued as **Phase 7** in Planning.md.

**Ongoing deliverables:** dropped per client decision - the daily 5-minute Loom updates
and the Excalidraw architecture diagram are no longer required.

---

## 8. Running it

**Prerequisites**

- Python 3.12 (`uv` provisions it automatically if only 3.11 is installed)
- A Telegram bot token (@BotFather)
- An OpenAI API key *(still needed — see below)* — with a spend cap set on the dashboard
- A Loom account (free Starter tier is fine for the 5-minute path; Business for unlimited length)
- `ffmpeg` on PATH — *optional now*, only for the rare voice-fallback ASR branch

**Setup**

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate   # or python -m venv
uv pip install -r requirements-dev.txt                      # or pip install
cp .env.example .env      # then fill in

# start the bot (standard cloud Telegram endpoint, no local server needed)
python -m bot.main
```

Startup validates configuration first and refuses to start with one clear message
listing every problem — never a raw traceback. Once a Telegram token and OpenAI key
are in `.env`, it runs two live pre-flight checks (Telegram token via `get_me`, OpenAI
key via a zero-cost `models.list`, both failing before polling starts) — the old
local-server reachability check is gone because the local server is gone.

**Demo commands**

| Command | Effect |
|---|---|
| `/start` | Passcode gate, then onboarding |
| `/advance [N]` | Fast-forward N simulated days, running every real per-day check |
| `/reset` | Restart the journey, keeping prior history for reference |
| `/wipe` | Delete all of this user's data |

`/advance` is what makes a 30-day arc demonstrable in one sitting: it steps day by day
internally, so missed-day flags, re-evaluation triggers and the 24-hour gate all fire
exactly as they would in real time — then batches everything the agent wants to say into
a single coherent message rather than a burst.

**Access control:** anyone who has the bot's link/username **and** the shared passcode
has full access — the passcode is the only gate, entered on `/start`. Everyone else
(including anyone who merely finds the bot) is stopped at the gate. Backed by a
15-minute lockout after 5 failed attempts, per-user rate limiting, and secrets confined
to a gitignored `.env`. A hard spend cap should be set on the OpenAI key from the
dashboard as the real backstop.

---

## 8b. Demo Day Runbook

**Pre-demo checklist**

1. `.env` filled in (all three required vars).
2. `python -m bot.main` → both pre-flight messages appear ("pre-flight 1 ok",
   "pre-flight 2 ok: OpenAI key accepted") *before* polling starts.
3. Spend cap confirmed on the OpenAI dashboard.
4. `/wipe` your own test account for a clean slate.
5. A Loom account ready (free Starter tier is fine for the 5-minute path).

**Suggested talking-point script** (mapped to the stage graph)

| Stage beat | What to show |
|---|---|
| `/start` + passcode | warm onboarding conversation — one question at a time, not a form |
| Onboarding end | the 5 recording questions, tailored to what was shared |
| Submission | Loom link + pasted transcript; oEmbed duration fetch; metrics computed in code |
| `/advance 2` | 24h hold, then the audit days: Day 1 auditory-only, Day 2 shares the Loom link back |
| Day 3 | cross-signal synthesis into 2-3 grounded habit choices; user picks |
| Weekly cycle | daily check-ins, trigger design; `/advance 9` with 2 missed days → why-before-shrink nudge |
| Habit transition | the Kaizen reveal + measured before/after on the user's own numbers |

**`/advance [N]` cheat-sheet**

`/advance N` bumps the day-offset; it never sets an absolute day. Effective day =
real elapsed days since the per-user anchor + offset. So `/advance 5` on day 3
lands on day 8. Each simulated day runs the same checks a real day would.

**If something breaks**

- Loom link/transcript submission fails → offer the voice-message fallback; the
  user picks self-report or full-metrics fresh each time.
- oEmbed can't resolve (restricted video) → metrics fall back to Plan-B duration
  and the agent says so transparently.
- Transcript won't parse for pauses → five metrics still compute; the agent says
  so instead of writing misleading zeros.
- An LLM call fails mid-turn → the user's message is durable and they get one
  graceful "hit a snag" line; the bot keeps polling.

**Judgment calls to be ready to defend** (fuller rationale in Planning.md)

1. Raw `python-telegram-bot` + a hand-written tool loop, not Hermes — full visibility
   of the state model for learning purposes.
2. SQLite + rolling-summary buffer, not Obsidian/Mem0/Supermemory — our need is
   structured per-user state, not semantic retrieval.
3. The agent leads with grounded options; the user always decides (Principle 4) —
   Samyak's brief wins over siddhu's original full-autonomy notes, documented.
4. Scope honesty — the framework is hard-coded; what the user genuinely chooses
   is which habit and what exercise. We say so rather than pretend.
5. The Loom pivot — removing the local-server/ffmpeg/Whisper pipeline before it
   was ever built: less infra, no deprecation risk, zero per-submission ASR cost

---

## 9. What I need from you

1. **An OpenAI API key** — this is the one hard blocker on end-to-end testing. With
   a spend cap set dashboard-side as the real cost backstop.
2. **A Telegram bot token** from @BotFather, and a decision on whether the demo runs
   on your bot or mine (no `logOut`/local-server step is involved either way now).

---

## 10. Reference

| File | Contents |
|---|---|
| `Planning.md` | Full technical specification — schema, phases, verification |
| `Video.md` | Source method analysis (video vs. PDF workbook) |
| `Plan.md` | Original brief transcript + first-pass design notes |
| `Chat.md` | Complete planning decision log with rationale |
| `Phase-0.5-Spike-Results.md` | The executed Loom spike — outputs, formats found, gate verdicts |
