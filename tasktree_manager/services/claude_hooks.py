"""Claude Code hook configuration for status monitoring."""

import json
import os
from datetime import datetime
from pathlib import Path


def claude_config_dir() -> Path:
    """Claude Code's config home: $CLAUDE_CONFIG_DIR, else ~/.claude.

    Transcripts (projects/<encoded-path>/*.jsonl) and per-project memory
    live under it, so every lookup must honour the override or a user who
    relocated their config gets no session resume and diverging memory.
    """
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def _encode_project_path(folder: Path) -> str:
    """Encode a path the way Claude CLI names ~/.claude/projects/ entries.

    The encoding replaces "/" and "." with "-".
    """
    return str(folder).replace("/", "-").replace(".", "-")


def has_claude_session(folder: Path) -> bool:
    """Return True if Claude Code has a recorded session for the given folder.

    Claude CLI stores transcripts at <config dir>/projects/<encoded-path>/*.jsonl.
    """
    project_dir = claude_config_dir() / "projects" / _encode_project_path(folder)
    if not project_dir.is_dir():
        return False
    return any(project_dir.glob("*.jsonl"))


def repo_memory_dir(repo_path: Path) -> Path:
    """Return the main repo's own Claude auto-memory directory.

    Sessions running in the main checkout use this directory by default,
    so pointing worktree sessions here gives every worktree of a repo —
    and the main checkout itself — one shared memory that outlives any
    single worktree.
    """
    return claude_config_dir() / "projects" / _encode_project_path(repo_path) / "memory"


def _make_hook(status: str, status_file: str) -> dict:
    """Create a single hook entry that writes status to the given file path."""
    safe_path = status_file.replace("'", "'\\''")
    return {
        "type": "command",
        "command": f'printf \'{{"status":"{status}","ts":%d}}\' $(date +%s) > \'{safe_path}\'',
        "async": True,
    }


def _build_hooks_config(status_file: str) -> dict:
    """Build hooks config with absolute path to status file."""
    return {
        "SessionStart": [{"hooks": [_make_hook("running", status_file)]}],
        "UserPromptSubmit": [{"hooks": [_make_hook("running", status_file)]}],
        "Stop": [{"hooks": [_make_hook("waiting", status_file)]}],
        "SessionEnd": [{"hooks": [_make_hook("ended", status_file)]}],
    }


def _load_settings(settings_file: Path) -> dict:
    """Read existing settings JSON, tolerating a missing or corrupt file.

    A file that does not parse is moved aside to ``<name>.broken-<ts>``
    rather than silently overwritten: settings.local.json also holds the
    user's permissions.allow/deny and hooks, which would otherwise be lost.
    """
    if not settings_file.exists():
        return {}
    try:
        data = json.loads(settings_file.read_text())
    except OSError:
        return {}
    except json.JSONDecodeError:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            settings_file.rename(settings_file.with_name(f"{settings_file.name}.broken-{stamp}"))
        except OSError:
            pass
        return {}
    return data if isinstance(data, dict) else {}


def _is_tasktree_hook_group(group: object) -> bool:
    """True if a hook group was written by tasktree (targets .claude_status)."""
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks", [])
    if not isinstance(hooks, list):
        return False
    # The command value is user-editable JSON, so never assume it is a string
    return any(
        isinstance(hook, dict)
        and isinstance(hook.get("command"), str)
        and ".claude_status" in hook["command"]
        for hook in hooks
    )


def _merge_hooks(existing_hooks: object, new_hooks: dict) -> dict:
    """Merge tasktree's status hooks into an existing hooks config.

    User-defined hook groups are preserved untouched (settings.local.json
    holds executable configuration the user may have written by hand);
    only groups previously written by tasktree are replaced, so repeated
    calls do not stack duplicates.
    """
    merged = dict(existing_hooks) if isinstance(existing_hooks, dict) else {}
    for event, groups in new_hooks.items():
        current = merged.get(event)
        kept = (
            [g for g in current if not _is_tasktree_hook_group(g)]
            if isinstance(current, list)
            else []
        )
        merged[event] = kept + groups
    return merged


def ensure_claude_hooks(task_path: Path, memory_dir: str = "") -> None:
    """Create .claude/settings.local.json with status-reporting hooks.

    Merges with existing settings if the file already exists, preserving
    user's own configuration while adding/updating the status hooks.

    Task folders are not git repositories, so Claude Code keys its auto
    memory to the task path — memory that becomes orphaned when the task
    is deleted. When memory_dir is set, autoMemoryDirectory redirects all
    task sessions to one shared pool that persists across tasks.
    """
    claude_dir = task_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    settings_file = claude_dir / "settings.local.json"
    existing = _load_settings(settings_file)

    # Merge hooks into existing settings, preserving user-defined groups
    existing["hooks"] = _merge_hooks(
        existing.get("hooks"), _build_hooks_config(str(task_path / ".claude_status"))
    )

    if memory_dir:
        existing["autoMemoryDirectory"] = str(Path(memory_dir).expanduser())

    settings_file.write_text(json.dumps(existing, indent=2) + "\n")


def exclude_from_git(repo_path: Path, entry: str) -> None:
    """Add a pattern to <repo>/.git/info/exclude (shared with its worktrees).

    Idempotent. A file without a trailing newline gets one first so the new
    entry is never glued onto the user's last pattern.
    """
    git_dir = repo_path / ".git"
    if not git_dir.is_dir():
        return

    exclude_file = git_dir / "info" / "exclude"
    try:
        existing = exclude_file.read_text() if exclude_file.exists() else ""
        if entry in existing.splitlines():
            return
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        with exclude_file.open("a") as f:
            f.write(prefix + entry + "\n")
    except OSError:
        return


def ensure_worktree_claude_settings(
    worktree_path: Path, repo_path: Path, status_file: Path
) -> None:
    """Create .claude/settings.local.json inside a worktree.

    Points autoMemoryDirectory at the main repo's own memory directory, so
    memory saved while working in any worktree of a repo persists after the
    worktree is deleted and is shared with future worktrees and with
    sessions in the main checkout. Also installs the status-reporting hooks
    (writing to the task's status file) so sessions started manually inside
    a worktree light up the task indicator.
    """
    claude_dir = worktree_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    settings_file = claude_dir / "settings.local.json"
    existing = _load_settings(settings_file)

    # Merge, preserving user-defined hook groups (same policy as task hooks)
    existing["hooks"] = _merge_hooks(existing.get("hooks"), _build_hooks_config(str(status_file)))
    existing["autoMemoryDirectory"] = str(repo_memory_dir(repo_path))

    settings_file.write_text(json.dumps(existing, indent=2) + "\n")
    # Hide the generated file from git status in the repo and its worktrees
    exclude_from_git(repo_path, ".claude/settings.local.json")
