from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from schemas.manifest import Manifest


@dataclass
class AppState:
    manifest: Manifest | None = None
    # Modification time of the manifest file that `manifest` was read from.
    manifest_mtime: int | None = None
    llm_client: AsyncOpenAI | None = None


app_state = AppState()
