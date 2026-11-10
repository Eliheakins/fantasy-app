"""The Refresh scores button."""

import logging
from typing import Any

from fastapi import APIRouter

from fantasy import _live
from fantasy._lock import PipelineBusy, pipeline_lock
from fantasy.api_deps import DataDir
from fantasy.api_envelope import fail, ok
from fantasy.api_models import (
    Envelope,
    RefreshData,
)
from fantasy.api_routes.common import BUSY_MESSAGE, Runner
from fantasy.data_api import clear_league_cache
from fantasy.sources.sleeper import SleeperError

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/live/refresh", response_model=Envelope[RefreshData])
def refresh_live(runner: Runner, data_dir: DataDir) -> Any:
    """Pull this week's matchups from Sleeper, then drop every cache."""
    try:
        with pipeline_lock(data_dir, blocking=False):
            player_rows = _live.refresh_live(data_dir)
            _live.record_live_tick(data_dir=data_dir)  # the league cache follows data_version
    except PipelineBusy:
        return fail("busy", BUSY_MESSAGE)
    except (OSError, SleeperError):
        log.exception("live refresh failed")
        return fail("server", "Sleeper refresh failed. See the server log.")
    clear_league_cache()
    runner.clear()
    return ok({"player_rows": player_rows})
