from __future__ import annotations

import os
import random
import time

from scrapers.common.logging_ptpt import info


def sleep_random(
    *,
    logger,
    label: str,
    msg_key: str,
    min_env: str = "REQUEST_DELAY_MIN",
    max_env: str = "REQUEST_DELAY_MAX",
    default_min: float = 60.0,
    default_max: float = 120.0,
) -> float:
    try:
        mn = float(os.getenv(min_env, str(default_min)))
        mx = float(os.getenv(max_env, str(default_max)))
    except ValueError:
        mn, mx = default_min, default_max

    if mx < mn:
        mn, mx = mx, mn

    seconds = random.uniform(mn, mx)
    info(logger, msg_key, label=label, segundos=seconds)
    time.sleep(seconds)
    return seconds