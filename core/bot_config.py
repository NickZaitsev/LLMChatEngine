"""Shared bot runtime configuration."""

from dataclasses import dataclass
from typing import Any, Dict
import uuid


@dataclass
class BotConfig:
    """Configuration for a single bot instance."""

    id: uuid.UUID
    token: str
    name: str
    personality: str
    is_active: bool
    feature_flags: Dict[str, Any]
    llm_config: Dict[str, Any]
