"""Application wiring, pre-flight checks, polling.

Phase 0 scaffold: minimal run entry only - real wiring arrives in Phase 3.
Pre-flight checks (Telegram token / OpenAI key / passcode) are defined in config
and exercised by tests now; the Application construction itself is Phase 3 work.
"""

from __future__ import annotations

import logging

from bot import config


def main() -> None:
    """Entry point: validate config, then (Phase 3) start polling.

    Refuses to start with a clear, single message if configuration is broken -
    never a raw traceback.
    """
    logging.basicConfig(level=config.LOG_LEVEL)
    try:
        config.validate()
    except config.ConfigError as exc:
        raise SystemExit(str(exc)) from None
    # Phase 3 will construct the PTB Application, run pre-flight checks
    # (get_me / models.list) and start polling here.
    raise SystemExit("config OK - bot wiring arrives in Phase 3 (see Planning.md)")


if __name__ == "__main__":
    main()
