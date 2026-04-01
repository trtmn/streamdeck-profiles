"""Backup and restore Stream Deck profiles."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from deck.store import ProfileStore

_DEFAULT_BACKUP_DIR = Path.home() / "StreamDeckBackups"


class BackupManager:
    """Manage profile backups outside the Stream Deck app's directory tree."""

    def __init__(
        self,
        store: ProfileStore,
        backup_dir: Path | None = None,
    ) -> None:
        self.store = store
        self.backup_dir = backup_dir or _DEFAULT_BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_profile(self, profile_id: str) -> Path:
        """Create a timestamped zip backup of a single profile. Returns the backup path."""
        profile_dir = self.store._profile_path(profile_id)
        if not profile_dir.exists():
            raise FileNotFoundError(f"Profile not found: {profile_id}")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"{profile_id}_{timestamp}.zip"
        backup_path = self.backup_dir / backup_name

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_STORED) as zf:
            for file_path in sorted(profile_dir.rglob("*")):
                if file_path.is_file():
                    arcname = file_path.relative_to(profile_dir.parent)
                    zf.write(file_path, arcname)

        return backup_path

    def backup_all(self) -> Path:
        """Zip all profiles into one archive. Returns the backup path."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = self.backup_dir / f"all_profiles_{timestamp}.zip"

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_STORED) as zf:
            for profile_dir in sorted(self.store.profiles_dir.glob("*.sdProfile")):
                for file_path in sorted(profile_dir.rglob("*")):
                    if file_path.is_file():
                        arcname = file_path.relative_to(self.store.profiles_dir)
                        zf.write(file_path, arcname)

        return backup_path

    def restore_profile(self, backup_path: Path) -> str:
        """Extract a profile backup into ProfilesV3/. Returns the profile UUID."""
        with zipfile.ZipFile(backup_path, "r") as zf:
            # Find the .sdProfile directory name from the archive
            names = zf.namelist()
            profile_dirs = {n.split("/")[0] for n in names if ".sdProfile" in n.split("/")[0]}
            if not profile_dirs:
                raise ValueError(f"No .sdProfile found in {backup_path}")
            profile_dir_name = profile_dirs.pop()
            profile_id = profile_dir_name.replace(".sdProfile", "")
            zf.extractall(self.store.profiles_dir)

        return profile_id

    def list_backups(self) -> list[Path]:
        """List all backup zip files, newest first."""
        return sorted(self.backup_dir.glob("*.zip"), reverse=True)
