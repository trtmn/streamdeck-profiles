"""Pydantic models for Elgato Stream Deck V3 profile format.

These models faithfully represent the on-disk JSON structure so that
load → serialize round-trips produce identical output.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Position:
    """A button position on the Stream Deck grid."""

    col: int
    row: int

    @classmethod
    def from_key(cls, key: str) -> Position:
        """Parse a 'col,row' string like '3,1'."""
        col, row = key.split(",")
        return cls(int(col), int(row))

    def to_key(self) -> str:
        return f"{self.col},{self.row}"

    def __str__(self) -> str:
        return self.to_key()


class DeviceLayout(Enum):
    """Known Stream Deck hardware layouts."""

    XL = ("20GAT9901", 8, 4)
    MK1 = ("20GAA9902", 5, 3)

    def __init__(self, model: str, cols: int, rows: int) -> None:
        self.model = model
        self.cols = cols
        self.rows = rows

    @classmethod
    def from_model(cls, model: str) -> DeviceLayout | None:
        for layout in cls:
            if layout.model == model:
                return layout
        return None

    def validate_position(self, pos: Position) -> bool:
        return 0 <= pos.col < self.cols and 0 <= pos.row < self.rows

    def all_positions(self) -> list[Position]:
        return [Position(c, r) for r in range(self.rows) for c in range(self.cols)]


# ---------------------------------------------------------------------------
# JSON models — use PascalCase aliases to match Elgato's format
# ---------------------------------------------------------------------------

class _BaseModel(BaseModel):
    """Base with PascalCase alias support and extra-field passthrough."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )


class DeviceInfo(_BaseModel):
    model: str = Field(alias="Model")
    uuid: str = Field(alias="UUID")


class PageRef(_BaseModel):
    current: str = Field(alias="Current")
    default: str = Field(alias="Default")
    pages: list[str] = Field(alias="Pages")


class ProfileManifest(_BaseModel):
    """Top-level profile manifest (the .sdProfile/manifest.json)."""

    name: str = Field(alias="Name")
    device: DeviceInfo = Field(alias="Device")
    pages: PageRef = Field(alias="Pages")
    version: str = Field(default="3.0", alias="Version")
    app_identifier: str | None = Field(default=None, alias="AppIdentifier")
    backgrounds: dict[str, str] | None = Field(default=None, alias="Backgrounds")


class ButtonState(_BaseModel):
    """Visual state of a button (title, icon, font, etc.)."""

    title: str | None = Field(default=None, alias="Title")
    title_alignment: str | None = Field(default=None, alias="TitleAlignment")
    title_color: str | None = Field(default=None, alias="TitleColor")
    font_family: str | None = Field(default=None, alias="FontFamily")
    font_size: int | None = Field(default=None, alias="FontSize")
    font_style: str | None = Field(default=None, alias="FontStyle")
    font_underline: bool | None = Field(default=None, alias="FontUnderline")
    outline_thickness: int | None = Field(default=None, alias="OutlineThickness")
    show_title: bool | None = Field(default=None, alias="ShowTitle")
    image: str | None = Field(default=None, alias="Image")


class PluginInfo(_BaseModel):
    """Plugin that provides an action."""

    name: str = Field(alias="Name")
    uuid: str = Field(alias="UUID")
    version: str = Field(alias="Version")


class ActionGroup(_BaseModel):
    """A group of actions within a Multi Action."""

    actions: list[Action] = Field(alias="Actions")


class Action(_BaseModel):
    """A single button action on the Stream Deck grid."""

    action_id: str = Field(alias="ActionID")
    uuid: str = Field(alias="UUID")
    name: str = Field(alias="Name")
    linked_title: bool = Field(default=True, alias="LinkedTitle")
    plugin: PluginInfo | None = Field(default=None, alias="Plugin")
    resources: Any | None = Field(default=None, alias="Resources")
    settings: dict[str, Any] | None = Field(default=None, alias="Settings")
    state: int = Field(default=0, alias="State")
    states: list[ButtonState] = Field(default_factory=list, alias="States")
    # Multi Action nesting — can contain ActionGroups or bare Actions
    actions: list[ActionGroup | Action] | None = Field(default=None, alias="Actions")

    @staticmethod
    def new_id() -> str:
        """Generate a new unique ActionID."""
        return str(uuid.uuid4())


class Controller(_BaseModel):
    """A controller (always 'Keypad' in practice)."""

    type: str = Field(alias="Type")
    actions: dict[str, Action] | None = Field(default=None, alias="Actions")


class PageManifest(_BaseModel):
    """Page manifest — the button grid layout."""

    controllers: list[Controller] = Field(alias="Controllers")
    name: str = Field(default="", alias="Name")
    icon: str = Field(default="", alias="Icon")


# ---------------------------------------------------------------------------
# Lightweight summary types (not Pydantic — just for listing)
# ---------------------------------------------------------------------------

@dataclass
class ProfileSummary:
    profile_id: str
    name: str
    device_model: str
    app_identifier: str | None
    page_count: int


@dataclass
class PageSummary:
    page_id: str
    name: str
    button_count: int
    is_current: bool


# Fix forward reference for ActionGroup -> Action
ActionGroup.model_rebuild()
