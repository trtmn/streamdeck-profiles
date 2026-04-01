"""CLI for managing Stream Deck profiles."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from deck import app, backup, images, store
from deck.models import DeviceInfo, DeviceLayout


def _get_store() -> store.ProfileStore:
    return store.ProfileStore()


def _resolve_profile(s: store.ProfileStore, name_or_id: str) -> str:
    """Resolve a profile name or UUID to a profile_id."""
    # Try as UUID first (check if directory exists)
    if (s._profile_path(name_or_id)).exists():
        return name_or_id
    # Try case-insensitive name lookup
    match = s.find_profile_by_name(name_or_id)
    if match:
        return match.profile_id
    click.echo(f"Profile not found: {name_or_id}", err=True)
    sys.exit(1)


@click.group()
def cli() -> None:
    """Manage Elgato Stream Deck profiles, pages, and buttons."""


@cli.command("devices")
def list_devices() -> None:
    """List connected Stream Deck devices with grid sizes."""
    devices = app.list_devices()
    if not devices:
        click.echo("No devices found. Is Stream Deck running?", err=True)
        sys.exit(1)
    for d in devices:
        click.echo(f"  {d.name:<25} {d.size:>5}  ({d.button_count} buttons, type={d.type})")


@cli.command("list")
def list_profiles() -> None:
    """List all profiles."""
    s = _get_store()
    profiles = s.list_profiles()
    if not profiles:
        click.echo("No profiles found.")
        return
    for p in profiles:
        layout = DeviceLayout.from_model(p.device_model)
        device = layout.name if layout else p.device_model
        app_str = f" ({p.app_identifier})" if p.app_identifier else ""
        click.echo(f"  {p.name:<25} {device:<6} {p.page_count} pages{app_str}")
        click.echo(f"    id: {p.profile_id}")


@cli.command("pages")
@click.argument("profile")
def list_pages(profile: str) -> None:
    """List pages in a profile."""
    s = _get_store()
    profile_id = _resolve_profile(s, profile)
    pages = s.list_pages(profile_id)
    if not pages:
        click.echo("No pages found.")
        return
    for p in pages:
        current = " *" if p.is_current else ""
        name = f' "{p.name}"' if p.name else ""
        click.echo(f"  {p.page_id}{name}  ({p.button_count} buttons){current}")


@cli.command("buttons")
@click.argument("profile")
@click.argument("page", required=False)
def list_buttons(profile: str, page: str | None) -> None:
    """List buttons on a page. If page is omitted, uses current page."""
    s = _get_store()
    profile_id = _resolve_profile(s, profile)
    if page is None:
        prof = s.load_profile(profile_id)
        page = prof.pages.current
    page_manifest = s.load_page(profile_id, page)
    actions = page_manifest.controllers[0].actions
    if not actions:
        click.echo("No buttons on this page.")
        return
    for pos in sorted(actions.keys(), key=lambda k: (int(k.split(",")[1]), int(k.split(",")[0]))):
        a = actions[pos]
        title = ""
        if a.states:
            title = (a.states[0].title or "").replace("\n", " ").strip()
        click.echo(f"  {pos:>5}  {a.name:<35} {title}")


@cli.command("button-info")
@click.argument("profile")
@click.argument("page")
@click.argument("position")
def button_info(profile: str, page: str, position: str) -> None:
    """Show full details of a button as JSON."""
    s = _get_store()
    profile_id = _resolve_profile(s, profile)
    action = s.get_button(profile_id, page, position)
    if action is None:
        click.echo(f"No button at position {position}", err=True)
        sys.exit(1)
    click.echo(json.dumps(action.to_dict(), indent=2))


@cli.command("remove-button")
@click.argument("profile")
@click.argument("page")
@click.argument("position")
def remove_button(profile: str, page: str, position: str) -> None:
    """Remove a button at the given position."""
    s = _get_store()
    profile_id = _resolve_profile(s, profile)
    removed = s.remove_button(profile_id, page, position)
    if removed:
        click.echo(f"Removed: {removed.name} at {position}")
    else:
        click.echo(f"No button at {position}")


@cli.command("move-button")
@click.argument("profile")
@click.argument("page")
@click.argument("from_pos")
@click.argument("to_pos")
def move_button(profile: str, page: str, from_pos: str, to_pos: str) -> None:
    """Move a button from one position to another."""
    s = _get_store()
    profile_id = _resolve_profile(s, profile)
    s.move_button(profile_id, page, from_pos, to_pos)
    click.echo(f"Moved {from_pos} -> {to_pos}")


@cli.command("create-profile")
@click.argument("name")
@click.option("--device", type=click.Choice(["XL", "MK1"]), required=True)
@click.option("--app", "app_id", default=None, help="App identifier (path or '*')")
def create_profile(name: str, device: str, app_id: str | None) -> None:
    """Create a new empty profile."""
    s = _get_store()
    layout = DeviceLayout[device]
    # Use the first matching device UUID from existing profiles
    device_uuid = ""
    for p in s.list_profiles():
        if p.device_model == layout.model:
            prof = s.load_profile(p.profile_id)
            device_uuid = prof.device.uuid
            break
    device_info = DeviceInfo(model=layout.model, uuid=device_uuid)
    profile_id = s.create_profile(name, device_info, app_id)
    click.echo(f"Created profile: {name}")
    click.echo(f"  id: {profile_id}")


@cli.command("import-image")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.argument("profile")
@click.argument("page")
def import_image(source: Path, profile: str, page: str) -> None:
    """Import an image into a page's Images/ directory."""
    s = _get_store()
    profile_id = _resolve_profile(s, profile)
    mgr = images.ImageManager(s)
    ref = mgr.import_image(source, profile_id, page)
    click.echo(f"Imported: {ref}")


@cli.command("backup")
@click.argument("profile", required=False)
def backup_cmd(profile: str | None) -> None:
    """Backup a profile (or all profiles)."""
    s = _get_store()
    mgr = backup.BackupManager(s)
    if profile:
        profile_id = _resolve_profile(s, profile)
        path = mgr.backup_profile(profile_id)
    else:
        path = mgr.backup_all()
    click.echo(f"Backed up to: {path}")


@cli.command("restart")
def restart_cmd() -> None:
    """Restart the Stream Deck app to apply changes."""
    click.echo("Restarting Stream Deck...")
    if app.restart():
        click.echo("Done.")
    else:
        click.echo("Failed to restart.", err=True)
        sys.exit(1)


@cli.command("export")
@click.argument("profile")
@click.argument("page", required=False)
def export_cmd(profile: str, page: str | None) -> None:
    """Export a profile or page as formatted JSON."""
    s = _get_store()
    profile_id = _resolve_profile(s, profile)
    if page:
        data = s.load_page(profile_id, page)
    else:
        data = s.load_profile(profile_id)
    click.echo(json.dumps(data.to_dict(), indent=2))


@cli.command("exec")
@click.argument("profile")
@click.argument("page", required=False)
@click.argument("position", required=False)
def exec_cmd(profile: str, page: str | None, position: str | None) -> None:
    """Execute a button action natively.

    If PAGE is omitted, uses the current page.
    POSITION is col,row (e.g., 0,0).
    """
    from deck.executor import UnsupportedActionError, execute

    s = _get_store()
    profile_id = _resolve_profile(s, profile)
    if page is None:
        prof = s.load_profile(profile_id)
        page = prof.pages.current
    if position is None:
        click.echo("Position required (e.g., 0,0)", err=True)
        sys.exit(1)
    action = s.get_button(profile_id, page, position)
    if action is None:
        click.echo(f"No button at position {position}", err=True)
        sys.exit(1)
    try:
        result = execute(action.to_dict())
        click.echo(result)
    except UnsupportedActionError as e:
        click.echo(f"Cannot execute: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
