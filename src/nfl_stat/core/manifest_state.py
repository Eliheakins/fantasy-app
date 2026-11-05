"""Keeps the app's copy of the manifest in step with the file on disk."""

from __future__ import annotations

import logging
from pathlib import Path

from nfl_stat.core.state import AppState
from nfl_stat.schemas.manifest import MANIFEST_FILENAME, read_manifest

logger = logging.getLogger(__name__)


def refresh_manifest(state: AppState, data_dir: Path) -> None:
    """Re-read the manifest if its file changed, so a rebuild shows up without restarting the API.

    A missing file means no data yet; an unreadable or invalid one is logged and treated the same,
    so `/health` reports it instead of the API failing.
    """
    path = data_dir / MANIFEST_FILENAME
    try:
        modified = path.stat().st_mtime_ns
    except FileNotFoundError:
        state.manifest, state.manifest_mtime = None, None
        return
    except OSError:
        logger.exception("Cannot stat the manifest in %s", data_dir)
        return

    if modified == state.manifest_mtime:
        return
    try:
        state.manifest = read_manifest(data_dir)
    except (ValueError, OSError):
        logger.exception("Ignoring unreadable manifest in %s", data_dir)
        state.manifest = None
    state.manifest_mtime = modified
