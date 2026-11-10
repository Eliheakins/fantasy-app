"""The row base class and the error."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(Row):
    code: Literal["no_data", "invalid", "busy", "server", "unauthorized", "forbidden"]
    message: str
