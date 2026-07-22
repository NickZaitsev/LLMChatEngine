"""Shared bot runtime configuration."""

import uuid
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class BotConfig:
    """Configuration for a single bot instance."""

    id: uuid.UUID
    token: str
    name: str
    personality: str
    is_active: bool
    feature_flags: dict[str, Any]
    llm_config: dict[str, Any]
