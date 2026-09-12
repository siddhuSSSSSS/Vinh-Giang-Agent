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
import signal

from bot import config, handlers

_NOISY_LOGGERS = ("httpx", "httpcore", "apscheduler", "telegram", "telegram.ext")


def _setup_logging() -> None:
    logging.basicConfig(level=config.LOG_LEVEL)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _install_sigterm() -> None:
    """SIGTERM (systemd stop / docker stop) -> graceful stop, same as Ctrl+C.

    PTB's run_polling handles KeyboardInterrupt as a normal stop path (updater
    stop, job queue drain, post_shutdown hooks). A raw terminal signal would
    otherwise yank the loop, leaving the aiosqlite connection and apscheduler
    threads to die in the awkward "Exception ignored in threading" way. The
    handler simply raises KeyboardInterrupt in the main thread at the next
    convenient moment - exactly what a Ctrl+C does.
    """

    def _handler(signum: int, _frame: object) -> None:
        # raising inside signal_slot threads is unsafe; only raise on the
        # signal-handling thread == main thread (signal handlers run there)
        raise KeyboardInterrupt  # noqa: TRY002 - that IS the graceful path

    try:
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        # not the main thread (e.g. tests importing this module) - skip trap
        pass


def main() -> None:
    _setup_logging()
    try:
        config.validate()
    except config.ConfigError as exc:
        raise SystemExit(str(exc)) from None
    _install_sigterm()
    # SIGINT already behaves as KeyboardInterrupt natively - both signals now
    # take the SAME graceful path through PTB's stop lifecycle.
    handlers.run()


if __name__ == "__main__":
    main()
