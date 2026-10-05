from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Base of all user-facing config models: unknown options are an error."""

    model_config = ConfigDict(extra="forbid")
