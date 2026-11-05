from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from openai import AsyncOpenAI

from nfl_stat.core.config import AppSettings
from nfl_stat.core.state import AppState


# Both live on `app.state`, set by `create_app`, so every app (and every test) has its own.
def get_app_state(request: Request) -> AppState:
    return request.app.state.stat_state


def get_settings_dep(request: Request) -> AppSettings:
    return request.app.state.stat_settings


def get_llm_client(state: Annotated[AppState, Depends(get_app_state)]) -> AsyncOpenAI:
    if state.llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client is not initialized.")
    return state.llm_client
