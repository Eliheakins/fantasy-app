"""Status and refresh-queue reads."""

from typing import Any

from fastapi import APIRouter, Request

from fantasy import data_api, refresh_queue
from fantasy.api_deps import DataDir
from fantasy.api_envelope import guarded, rows
from fantasy.api_models import (
    Envelope,
    RefreshStatus,
    StatusData,
)
from fantasy.data_api import data_version

router = APIRouter()


@router.get("/status", response_model=Envelope[StatusData])
def status(request: Request, data_dir: DataDir) -> Any:
    account = getattr(request.state, "account", None)
    hide_errors = account is not None and not account["is_admin"]  # raw stage text is the admin's

    def build() -> dict[str, Any]:
        runs = rows(data_api.refresh_runs(data_dir))
        live = request.app.state.live.status()
        return {
            "freshness": rows(data_api.freshness(data_dir=data_dir)),
            "missing_layers": data_api.missing_layers(data_dir),
            "simulation_behind_inputs": data_api.simulation_behind_inputs(data_dir),
            "refresh_runs": [{**r, "error": None} for r in runs] if hide_errors else runs,
            "data_version": data_version(data_dir),
            "live_refresh": {**live, "last_error": None} if hide_errors else live,
        }

    return guarded(build)


@router.get("/refresh/status", response_model=Envelope[RefreshStatus])
def refresh_status(data_dir: DataDir) -> Any:
    """Whether a refresh is queued or running, and how the last one went."""
    return guarded(lambda: refresh_queue.status(data_dir))
