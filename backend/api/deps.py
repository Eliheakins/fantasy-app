from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from openai import AsyncOpenAI

from core.config import AppSettings, get_settings
from core.state import AppState, app_state


def get_app_state() -> AppState:
    return app_state


def get_settings_dep() -> AppSettings:
    return get_settings()


def get_llm_client(state: Annotated[AppState, Depends(get_app_state)]) -> AsyncOpenAI:
    if state.llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client is not initialized.")
    return state.llm_client
