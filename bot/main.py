"""Application wiring, pre-flight checks, polling.

Phase 3 deliverable. Startup order per Planning.md Phase 6:
1. config validation (fail-fast, one clear error, never a traceback)
2. handlers wired; post_init performs the Telegram-token pre-flight (get_me)
   and opens the database
3. the Phase 4 scheduler's jobs register here once that phase lands
4. polling starts on the standard cloud endpoint (no local server)
"""

from __future__ import annotations

import logging

from bot import config, handlers


def main() -> None:
    logging.basicConfig(level=config.LOG_LEVEL)
    try:
        config.validate()
    except config.ConfigError as exc:
        raise SystemExit(str(exc)) from None
    handlers.run()


if __name__ == "__main__":
    main()
