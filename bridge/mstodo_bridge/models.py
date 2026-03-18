"""Data models for ESP32 bridge."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class TaskItem:
    """A single task suitable for ESP32 display."""

    task_id: str
    list_id: str
    title: str
    status: str  # "notStarted" | "completed"
    due: Optional[str] = None  # formatted date string
    reminder: Optional[str] = None  # formatted datetime string
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class TaskSnapshot:
    """A snapshot of tasks for a device."""

    device_id: str
    tasks: List[TaskItem] = field(default_factory=list)
    timestamp: str = ""  # ISO 8601

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "tasks": [t.to_dict() for t in self.tasks],
            "timestamp": self.timestamp,
        }
