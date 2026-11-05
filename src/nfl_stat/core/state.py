from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from nfl_stat.schemas.manifest import Manifest


@dataclass
class AppState:
    manifest: Manifest | None = None
    # Modification time of the manifest file that `manifest` was read from.
    manifest_mtime: int | None = None
    llm_client: AsyncOpenAI | None = None
