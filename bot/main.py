"""Application wiring, pre-flight checks, logging, polling.

Phase 6 deliverable. Startup order per Planning.md:
1. config validation (fail-fast, one clear error, never a traceback)
2. logging with third-party loggers pinned to WARNING (plan's 428 line)
3. handlers wired; post_init runs BOTH pre-flight checks:
   (1) telegram get_me  (2) openai models.list (zero-cost); on any failure one
   clear message names the failing check and polling never starts
4. polling starts on the standard cloud endpoint (no local server)
"""

from __future__ import annotations

import logging

from bot import config, handlers

_NOISY_LOGGERS = ("httpx", "httpcore", "apscheduler", "telegram", "telegram.ext")


def _setup_logging() -> None:
    logging.basicConfig(level=config.LOG_LEVEL)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def main() -> None:
    _setup_logging()
    try:
        config.validate()
    except config.ConfigError as exc:
        raise SystemExit(str(exc)) from None
    handlers.run()


if __name__ == "__main__":
    main()
