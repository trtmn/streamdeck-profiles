"""Filesystem I/O for Stream Deck V3 profiles.

Each method reads from or writes to disk — no in-memory cache.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from deck.models import (
    Action,
    Controller,
    DeviceInfo,
    PageManifest,
    PageRef,
    PageSummary,
    ProfileManifest,
    ProfileSummary,
)

_DEFAULT_PROFILES_DIR = Path.home() / "Library/Application Support/com.elgato.StreamDeck/ProfilesV3"


class ProfileStore:
    """Read and write Stream Deck V3 profile data on disk."""

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self.profiles_dir = profiles_dir or _DEFAULT_PROFILES_DIR

    # ------------------------------------------------------------------
    # Internal path helpers
    # ------------------------------------------------------------------

    def _profile_path(self, profile_id: str) -> Path:
        return self.profiles_dir / f"{profile_id}.sdProfile"

    def _page_path(self, profile_id: str, page_id: str) -> Path:
        return self._profile_path(profile_id) / "Profiles" / page_id.upper()

    def _page_images_path(self, profile_id: str, page_id: str) -> Path:
        return self._page_path(profile_id, page_id) / "Images"

    def _profile_images_path(self, profile_id: str) -> Path:
        return self._profile_path(profile_id) / "Images"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_profiles(self) -> list[ProfileSummary]:
        """List all profiles with basic metadata."""
        results: list[ProfileSummary] = []
        for profile_dir in sorted(self.profiles_dir.glob("*.sdProfile")):
            manifest_path = profile_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            raw = self._read_json(manifest_path)
            profile_id = profile_dir.stem  # UUID without .sdProfile
            pages = raw.get("Pages", {})
            page_list = pages.get("Pages", [])
            results.append(ProfileSummary(
                profile_id=profile_id,
                name=raw.get("Name", ""),
                device_model=raw.get("Device", {}).get("Model", "?"),
                app_identifier=raw.get("AppIdentifier"),
                page_count=len(page_list),
            ))
        return results

    def load_profile(self, profile_id: str) -> ProfileManifest:
        """Load and parse a profile manifest."""
        path = self._profile_path(profile_id) / "manifest.json"
        raw = self._read_json(path)
        return ProfileManifest.model_validate(raw)

    def load_page(self, profile_id: str, page_id: str) -> PageManifest:
        """Load and parse a page manifest (the button grid)."""
        path = self._page_path(profile_id, page_id) / "manifest.json"
        raw = self._read_json(path)
        return PageManifest.model_validate(raw)

    def get_button(self, profile_id: str, page_id: str, position: str) -> Action | None:
        """Get a single button action at the given 'col,row' position."""
        page = self.load_page(profile_id, page_id)
        actions = page.controllers[0].actions
        if actions is None:
            return None
        return actions.get(position)

    def list_pages(self, profile_id: str) -> list[PageSummary]:
        """List pages in a profile with button counts."""
        profile = self.load_profile(profile_id)
        results: list[PageSummary] = []
        # Walk all page directories, not just the Pages list (includes folders)
        profiles_dir = self._profile_path(profile_id) / "Profiles"
        if not profiles_dir.exists():
            return results
        for page_dir in sorted(profiles_dir.iterdir()):
            if not page_dir.is_dir() or page_dir.name.startswith("."):
                continue
            manifest_path = page_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            raw = self._read_json(manifest_path)
            page_id = page_dir.name
            controllers = raw.get("Controllers", [{}])
            actions = controllers[0].get("Actions") if controllers else None
            button_count = len(actions) if actions else 0
            is_current = page_id.lower() == profile.pages.current.lower()
            results.append(PageSummary(
                page_id=page_id,
                name=raw.get("Name", ""),
                button_count=button_count,
                is_current=is_current,
            ))
        return results

    def find_profile_by_name(self, name: str) -> ProfileSummary | None:
        """Find a profile by name (case-insensitive)."""
        for p in self.list_profiles():
            if p.name.lower() == name.lower():
                return p
        return None

    def find_all_pages(self, profile_id: str) -> list[str]:
        """Return all page UUIDs in a profile (top-level + folders)."""
        profiles_dir = self._profile_path(profile_id) / "Profiles"
        if not profiles_dir.exists():
            return []
        return [
            d.name
            for d in sorted(profiles_dir.iterdir())
            if d.is_dir() and not d.name.startswith(".")
        ]

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_profile(self, profile_id: str, manifest: ProfileManifest) -> None:
        """Write a profile manifest to disk."""
        path = self._profile_path(profile_id) / "manifest.json"
        raw = manifest.model_dump(by_alias=True, exclude_unset=True)
        self._write_json(path, raw)

    def save_page(self, profile_id: str, page_id: str, manifest: PageManifest) -> None:
        """Write a page manifest to disk."""
        path = self._page_path(profile_id, page_id) / "manifest.json"
        raw = manifest.model_dump(by_alias=True, exclude_unset=True)
        self._write_json(path, raw)

    def set_button(self, profile_id: str, page_id: str, position: str, action: Action) -> None:
        """Set or replace a button at the given position."""
        page = self.load_page(profile_id, page_id)
        ctrl = page.controllers[0]
        if ctrl.actions is None:
            ctrl.actions = {}
        ctrl.actions[position] = action
        self.save_page(profile_id, page_id, page)

    def remove_button(self, profile_id: str, page_id: str, position: str) -> Action | None:
        """Remove a button at the given position. Returns the removed action."""
        page = self.load_page(profile_id, page_id)
        ctrl = page.controllers[0]
        if ctrl.actions is None:
            return None
        removed = ctrl.actions.pop(position, None)
        if removed is not None:
            self.save_page(profile_id, page_id, page)
        return removed

    def move_button(
        self, profile_id: str, page_id: str, from_pos: str, to_pos: str
    ) -> None:
        """Move a button from one position to another on the same page."""
        page = self.load_page(profile_id, page_id)
        ctrl = page.controllers[0]
        if ctrl.actions is None or from_pos not in ctrl.actions:
            raise KeyError(f"No button at position {from_pos}")
        action = ctrl.actions.pop(from_pos)
        ctrl.actions[to_pos] = action
        self.save_page(profile_id, page_id, page)

    def create_page(self, profile_id: str, page_id: str | None = None) -> str:
        """Create a new empty page. Returns the page UUID."""
        page_id = page_id or str(uuid.uuid4()).upper()
        page_dir = self._page_path(profile_id, page_id)
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "Images").mkdir(exist_ok=True)
        empty_page = PageManifest(
            controllers=[Controller(type="Keypad", actions=None)],
            name="",
            icon="",
        )
        raw = empty_page.model_dump(by_alias=True, exclude_none=True)
        self._write_json(page_dir / "manifest.json", raw)
        return page_id

    def add_page_to_profile(
        self, profile_id: str, page_id: str, index: int | None = None
    ) -> None:
        """Add a page UUID to the profile's page list."""
        profile = self.load_profile(profile_id)
        page_uuid_lower = page_id.lower()
        # Avoid duplicates
        existing = [p.lower() for p in profile.pages.pages]
        if page_uuid_lower in existing:
            return
        if index is None:
            profile.pages.pages.append(page_id.lower())
        else:
            profile.pages.pages.insert(index, page_id.lower())
        self.save_profile(profile_id, profile)

    def delete_page(self, profile_id: str, page_id: str) -> None:
        """Delete a page and remove it from the profile's page list."""
        # Remove from profile pages list
        profile = self.load_profile(profile_id)
        page_uuid_lower = page_id.lower()
        profile.pages.pages = [p for p in profile.pages.pages if p.lower() != page_uuid_lower]
        # If the deleted page was current, reset to the first page
        if profile.pages.current.lower() == page_uuid_lower and profile.pages.pages:
            profile.pages.current = profile.pages.pages[0]
        self.save_profile(profile_id, profile)
        # Remove the page directory
        page_dir = self._page_path(profile_id, page_id)
        if page_dir.exists():
            shutil.rmtree(page_dir)

    def create_profile(
        self,
        name: str,
        device: DeviceInfo,
        app_identifier: str | None = None,
    ) -> str:
        """Create a new profile with one empty page. Returns the profile UUID."""
        profile_id = str(uuid.uuid4()).upper()
        profile_dir = self._profile_path(profile_id)
        profile_dir.mkdir(parents=True)
        (profile_dir / "Images").mkdir()
        (profile_dir / "Profiles").mkdir()

        # Create one empty default page
        page_id = self.create_page(profile_id)

        manifest = ProfileManifest(
            name=name,
            device=device,
            pages=PageRef(
                current=page_id.lower(),
                default=page_id.lower(),
                pages=[page_id.lower()],
            ),
            version="3.0",
            app_identifier=app_identifier,
        )
        self.save_profile(profile_id, manifest)
        return profile_id

    def delete_profile(self, profile_id: str) -> None:
        """Delete an entire profile directory."""
        profile_dir = self._profile_path(profile_id)
        if profile_dir.exists():
            shutil.rmtree(profile_dir)

    def duplicate_profile(self, profile_id: str, new_name: str) -> str:
        """Duplicate a profile with a new name and fresh UUIDs. Returns the new profile UUID."""
        new_id = str(uuid.uuid4()).upper()
        src = self._profile_path(profile_id)
        dst = self._profile_path(new_id)
        shutil.copytree(src, dst)
        # Update the name in the new profile
        profile = self.load_profile(new_id)
        profile.name = new_name
        self.save_profile(new_id, profile)
        return new_id
