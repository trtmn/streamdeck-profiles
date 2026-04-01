"""Image management for Stream Deck profile button icons."""

from __future__ import annotations

import random
import shutil
import string
from pathlib import Path

from deck.store import ProfileStore

# Elgato uses 27-char uppercase alphanumeric names ending in Z
_HASH_CHARS = string.ascii_uppercase + string.digits
_HASH_LENGTH = 26  # + trailing "Z" = 27 total


def generate_hash_name(ext: str = ".png") -> str:
    """Generate a random image filename matching Elgato's naming convention."""
    chars = "".join(random.choices(_HASH_CHARS, k=_HASH_LENGTH))
    return f"{chars}Z{ext}"


class ImageManager:
    """Manage button icon images within profile directories."""

    def __init__(self, store: ProfileStore) -> None:
        self.store = store

    def import_image(
        self,
        source_path: Path,
        profile_id: str,
        page_id: str,
    ) -> str:
        """Copy an image into a page's Images/ directory.

        Returns the relative reference path (e.g., 'Images/HASH.png')
        suitable for use in ButtonState.image.
        """
        ext = source_path.suffix.lower() or ".png"
        hash_name = generate_hash_name(ext)
        dest_dir = self.store._page_images_path(profile_id, page_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / hash_name
        shutil.copy2(source_path, dest)
        return f"Images/{hash_name}"

    def import_profile_image(
        self,
        source_path: Path,
        profile_id: str,
    ) -> str:
        """Copy an image into the profile-level Images/ directory."""
        ext = source_path.suffix.lower() or ".png"
        hash_name = generate_hash_name(ext)
        dest_dir = self.store._profile_images_path(profile_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / hash_name
        shutil.copy2(source_path, dest)
        return f"Images/{hash_name}"

    def resolve_image(
        self,
        profile_id: str,
        page_id: str,
        image_ref: str,
    ) -> Path | None:
        """Resolve an image reference to an absolute path on disk."""
        # Images can be in the page's Images/ dir or the profile's Images/ dir
        page_path = self.store._page_path(profile_id, page_id) / image_ref
        if page_path.exists():
            return page_path
        profile_path = self.store._profile_path(profile_id) / image_ref
        if profile_path.exists():
            return profile_path
        return None

    def list_page_images(self, profile_id: str, page_id: str) -> list[Path]:
        """List all image files in a page's Images/ directory."""
        images_dir = self.store._page_images_path(profile_id, page_id)
        if not images_dir.exists():
            return []
        return sorted(p for p in images_dir.iterdir() if p.is_file())

    def remove_unused_images(self, profile_id: str, page_id: str) -> list[Path]:
        """Remove images not referenced by any button on the page. Returns removed paths."""
        page = self.store.load_page(profile_id, page_id)
        # Collect all image references from button states
        referenced: set[str] = set()
        actions = page.controllers[0].actions
        if actions:
            for action in actions.values():
                for state in action.states:
                    if state.image:
                        referenced.add(state.image)
                # Check nested multi-action states too
                if action.actions:
                    for group in action.actions:
                        for sub_action in group.actions:
                            for state in sub_action.states:
                                if state.image:
                                    referenced.add(state.image)

        # Find and remove unreferenced images
        removed: list[Path] = []
        for img_path in self.list_page_images(profile_id, page_id):
            ref = f"Images/{img_path.name}"
            if ref not in referenced:
                img_path.unlink()
                removed.append(img_path)
        return removed
