"""Models for Elgato Stream Deck V3 profile format.

Pure stdlib — no Pydantic. Round-trip JSON fidelity is achieved by storing
the original dict and only applying typed access on top.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any


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
# JSON model base — thin wrapper over dicts for round-trip fidelity
# ---------------------------------------------------------------------------

class JsonModel:
    """Base class that wraps a raw JSON dict.

    Provides typed property access via PascalCase keys while preserving
    the original dict (including unknown fields) for serialization.
    """

    def __init__(self, raw: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if raw is not None:
            self._raw = dict(raw)
        else:
            self._raw = {}
        # Apply kwargs using alias mapping
        alias_map = self._alias_map()
        for py_name, value in kwargs.items():
            alias = alias_map.get(py_name, py_name)
            self._raw[alias] = self._to_raw(value)

    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        """Override to define python_name -> JsonKey mapping."""
        return {}

    @classmethod
    def _reverse_alias_map(cls) -> dict[str, str]:
        return {v: k for k, v in cls._alias_map().items()}

    def _get(self, alias: str, default: Any = None) -> Any:
        return self._raw.get(alias, default)

    def _set(self, alias: str, value: Any) -> None:
        self._raw[alias] = self._to_raw(value)

    @staticmethod
    def _to_raw(value: Any) -> Any:
        if isinstance(value, JsonModel):
            return value.to_dict()
        if isinstance(value, list):
            return [JsonModel._to_raw(v) for v in value]
        if isinstance(value, dict):
            return {k: JsonModel._to_raw(v) for k, v in value.items()}
        return value

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a JSON-compatible dict, preserving all original keys."""
        return self._raw

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "JsonModel":
        return cls(raw=raw)


# ---------------------------------------------------------------------------
# Concrete models
# ---------------------------------------------------------------------------

class DeviceInfo(JsonModel):
    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        return {"model": "Model", "uuid": "UUID"}

    @property
    def model(self) -> str:
        return self._get("Model", "")

    @model.setter
    def model(self, v: str) -> None:
        self._set("Model", v)

    @property
    def uuid(self) -> str:
        return self._get("UUID", "")

    @uuid.setter
    def uuid(self, v: str) -> None:
        self._set("UUID", v)


class PageRef(JsonModel):
    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        return {"current": "Current", "default": "Default", "pages": "Pages"}

    @property
    def current(self) -> str:
        return self._get("Current", "")

    @current.setter
    def current(self, v: str) -> None:
        self._set("Current", v)

    @property
    def default(self) -> str:
        return self._get("Default", "")

    @default.setter
    def default(self, v: str) -> None:
        self._set("Default", v)

    @property
    def pages(self) -> list[str]:
        return self._get("Pages", [])

    @pages.setter
    def pages(self, v: list[str]) -> None:
        self._set("Pages", v)


class ProfileManifest(JsonModel):
    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        return {
            "name": "Name", "device": "Device", "pages": "Pages",
            "version": "Version", "app_identifier": "AppIdentifier",
            "backgrounds": "Backgrounds",
        }

    @property
    def name(self) -> str:
        return self._get("Name", "")

    @name.setter
    def name(self, v: str) -> None:
        self._set("Name", v)

    @property
    def device(self) -> DeviceInfo:
        return DeviceInfo(raw=self._get("Device", {}))

    @property
    def pages(self) -> PageRef:
        return PageRef(raw=self._get("Pages", {}))

    @pages.setter
    def pages(self, v: PageRef) -> None:
        self._set("Pages", v)

    @property
    def version(self) -> str:
        return self._get("Version", "3.0")

    @property
    def app_identifier(self) -> str | None:
        return self._get("AppIdentifier")


class ButtonState(JsonModel):
    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        return {
            "title": "Title", "title_alignment": "TitleAlignment",
            "title_color": "TitleColor", "font_family": "FontFamily",
            "font_size": "FontSize", "font_style": "FontStyle",
            "font_underline": "FontUnderline", "outline_thickness": "OutlineThickness",
            "show_title": "ShowTitle", "image": "Image",
        }

    @property
    def title(self) -> str | None:
        return self._get("Title")

    @property
    def image(self) -> str | None:
        return self._get("Image")

    @image.setter
    def image(self, v: str | None) -> None:
        self._set("Image", v)


class PluginInfo(JsonModel):
    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        return {"name": "Name", "uuid": "UUID", "version": "Version"}

    @property
    def name(self) -> str:
        return self._get("Name", "")

    @property
    def uuid(self) -> str:
        return self._get("UUID", "")

    @property
    def version(self) -> str:
        return self._get("Version", "")


class Action(JsonModel):
    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        return {
            "action_id": "ActionID", "uuid": "UUID", "name": "Name",
            "linked_title": "LinkedTitle", "plugin": "Plugin",
            "resources": "Resources", "settings": "Settings",
            "state": "State", "states": "States", "actions": "Actions",
        }

    @property
    def action_id(self) -> str:
        return self._get("ActionID", "")

    @property
    def uuid(self) -> str:
        return self._get("UUID", "")

    @property
    def name(self) -> str:
        return self._get("Name", "")

    @name.setter
    def name(self, v: str) -> None:
        self._set("Name", v)

    @property
    def plugin(self) -> PluginInfo | None:
        raw = self._get("Plugin")
        return PluginInfo(raw=raw) if raw else None

    @property
    def settings(self) -> dict[str, Any] | None:
        return self._get("Settings")

    @property
    def states(self) -> list[ButtonState]:
        return [ButtonState(raw=s) for s in self._get("States", [])]

    @property
    def actions(self) -> list[dict[str, Any]] | None:
        return self._get("Actions")

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())


class Controller(JsonModel):
    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        return {"type": "Type", "actions": "Actions"}

    @property
    def type(self) -> str:
        return self._get("Type", "")

    @property
    def actions(self) -> dict[str, Action] | None:
        raw = self._get("Actions")
        if raw is None:
            return None
        return {pos: Action(raw=a) for pos, a in raw.items()}

    @actions.setter
    def actions(self, v: dict[str, Action] | None) -> None:
        if v is None:
            self._raw["Actions"] = None
        else:
            self._raw["Actions"] = {
                pos: a.to_dict() if isinstance(a, Action) else a
                for pos, a in v.items()
            }


class PageManifest(JsonModel):
    @classmethod
    def _alias_map(cls) -> dict[str, str]:
        return {"controllers": "Controllers", "name": "Name", "icon": "Icon"}

    @property
    def controllers(self) -> list[Controller]:
        return [Controller(raw=c) for c in self._get("Controllers", [])]

    @property
    def name(self) -> str:
        return self._get("Name", "")

    @property
    def icon(self) -> str:
        return self._get("Icon", "")


# ---------------------------------------------------------------------------
# Lightweight summary types
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
