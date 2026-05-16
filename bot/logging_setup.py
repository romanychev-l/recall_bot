from __future__ import annotations

import logging
from typing import Any


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] #%(levelname)-8s %(filename)s:"
               "%(lineno)d - %(name)s - %(message)s",
    )


def log_user_action(
    logger: logging.Logger,
    user_id: int,
    action: str,
    **fields: Any,
) -> None:
    payload = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("user_action user_id=%s action=%s %s", user_id, action, payload)
