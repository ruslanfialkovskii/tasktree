"""Configuration management for tasktree-manager."""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# tomllib is stdlib from 3.11; tomli (a runtime dependency on 3.10) is the
# same parser published as a package
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ConfigError(ValueError):
    """The config file exists but cannot be parsed."""


# Default keybindings - action name to key mapping
DEFAULT_KEYBINDINGS: dict[str, str] = {
    "quit": "q",
    "help": "?",
    "new_task": "n",
    "clone_task": "y",
    "add_repo": "a",
    "delete_task": "d",
    "rename_task": "R",
    "open_lazygit": "g",
    "show_diff": "h",
    "open_folder": "o",
    "open_editor": "e",
    "open_claude_resume": "c",
    "open_claude_gui_code": "C",
    "push_all": "p",
    "pull_all": "P",
    "refresh": "r",
    "toggle_messages": "m",
    "cycle_theme": "t",
    "toggle_grouping": "S",
    "cycle_sort": "s",
    "delete_worktree": "D",
    "dispatch_agent": "b",
    "focus_next": "tab",
    "focus_previous": "shift+tab",
    "cursor_down": "j",
    "cursor_up": "k",
}


def _toml_int(section: dict, key: str, default: int) -> int:
    """Read an int config value, falling back to the default on bad types."""
    try:
        return int(section.get(key, default))
    except (TypeError, ValueError):
        return default


# Default patterns excluded when symlinking gitignored files into worktrees.
# Caches/build artifacts are excluded as noise; key material is excluded so
# private keys and certificates never spread beyond the main checkout
# (.env files remain shared — that is the point of the feature).
DEFAULT_SYMLINK_BLOCKLIST: list[str] = [
    "*.pyc",
    "*.pyo",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "*.log",
    "*.egg-info",
    ".eggs",
    "dist",
    "build",
    ".tox",
    ".nox",
    "*.so",
    "*.dylib",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
    "id_rsa",
    "id_ecdsa",
    "id_ed25519",
]


@dataclass
class Config:
    """Configuration for tasktree-manager application.

    Configuration is loaded from (in order of priority):
    1. Environment variables (highest priority)
    2. Config file (~/.config/tasktree-manager/config.toml)
    3. Default values (lowest priority)
    """

    # Directory settings
    repos_dir: Path = field(default_factory=lambda: Path.home() / "repos")
    tasks_dir: Path = field(default_factory=lambda: Path.home() / "tasks")
    config_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "tasktree-manager")
    # Archive directory for finished-task diffs ("" = <tasks_dir>/.archive)
    archive_dir: str = ""

    # UI settings
    theme: str = "tasktree"
    show_hidden_files: bool = False
    refresh_interval: int = 30  # Auto-refresh interval in seconds (0 = disabled)
    agent_poll_interval: int = 10  # Claude agent session poll in seconds (0 = disabled)
    forge_poll_interval: int = 60  # MR/CI status poll in seconds (0 = disabled)

    # Git settings
    default_base_branch: str = "main"
    auto_push: bool = False
    git_timeout: int = 30

    # External tools
    editor: str = ""
    lazygit_path: str = "lazygit"
    hunk_path: str = "hunk"
    claude_path: str = "claude"
    claude_memory_dir: str = "~/.claude/tasktree-memory"
    claude_repo_memory: bool = True
    glab_path: str = "glab"
    gh_path: str = "gh"

    # Forge (MR/PR state via glab/gh)
    forge_enabled: bool = True
    forge_gitlab_hosts: list[str] = field(default_factory=list)

    # Keybindings (action -> key mapping)
    keybindings: dict[str, str] = field(default_factory=lambda: DEFAULT_KEYBINDINGS.copy())

    # Symlink settings - patterns to exclude from symlinking gitignored files
    symlink_blocklist: list[str] = field(default_factory=lambda: list(DEFAULT_SYMLINK_BLOCKLIST))

    # Fields overridden by environment variables for this session, mapped to
    # the config-file (or default) value they replaced. save() writes these
    # values back so a one-off `REPOS_DIR=... tasktree-manager` run never
    # rewrites the user's config file.
    env_overrides: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from config file and environment variables.

        Priority: Environment variables > Config file > Defaults

        Raises:
            ConfigError: the config file exists but is not valid TOML.
        """
        config_dir = (
            Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
            / "tasktree-manager"
        )
        config_file = config_dir / "config.toml"

        # Start with defaults
        config_data: dict = {}

        # Load from config file if it exists
        if config_file.exists():
            config_data = cls._load_toml(config_file)

        # Build config with file values or defaults
        repos_dir = Path(config_data.get("repos_dir", Path.home() / "repos")).expanduser()
        tasks_dir = Path(config_data.get("tasks_dir", Path.home() / "tasks")).expanduser()
        archive_dir = config_data.get("archive_dir", "")
        if not isinstance(archive_dir, str):
            archive_dir = ""

        # UI settings
        ui_config = config_data.get("ui", {})
        theme = ui_config.get("theme", "tasktree")
        show_hidden_files = ui_config.get("show_hidden_files", False)
        refresh_interval = _toml_int(ui_config, "refresh_interval", 30)
        agent_poll_interval = _toml_int(ui_config, "agent_poll_interval", 10)
        forge_poll_interval = _toml_int(ui_config, "forge_poll_interval", 60)

        # Git settings
        git_config = config_data.get("git", {})
        default_base_branch = git_config.get("default_base_branch", "main")
        auto_push = git_config.get("auto_push", False)
        git_timeout = _toml_int(git_config, "timeout", 30)

        # External tools
        tools_config = config_data.get("tools", {})
        editor = tools_config.get("editor", "")
        # Tool paths are used as argv[0] (no shell), so "~" must be expanded
        # here; the `c` key goes through a shell and would otherwise be the
        # only place a "~/.claude/local/claude" path worked
        lazygit_path = os.path.expanduser(str(tools_config.get("lazygit_path", "lazygit")))
        hunk_path = os.path.expanduser(str(tools_config.get("hunk_path", "hunk")))
        claude_path = os.path.expanduser(str(tools_config.get("claude_path", "claude")))
        claude_memory_dir = tools_config.get("claude_memory_dir", "~/.claude/tasktree-memory")
        claude_repo_memory = bool(tools_config.get("claude_repo_memory", True))
        glab_path = os.path.expanduser(str(tools_config.get("glab_path", "glab")))
        gh_path = os.path.expanduser(str(tools_config.get("gh_path", "gh")))

        # Forge settings
        forge_config = config_data.get("forge", {})
        forge_enabled = bool(forge_config.get("enabled", True))
        forge_gitlab_hosts = forge_config.get("gitlab_hosts", [])
        if isinstance(forge_gitlab_hosts, list):
            # Drop non-string elements: they would crash provider detection
            # (h.lower()) and Config.save (_toml_escape) at use time
            forge_gitlab_hosts = [h for h in forge_gitlab_hosts if isinstance(h, str)]
        else:
            forge_gitlab_hosts = []

        # Keybindings - start with defaults and override with config
        keybindings = DEFAULT_KEYBINDINGS.copy()
        keybindings_config = config_data.get("keybindings", {})
        for action, key in keybindings_config.items():
            if action in keybindings and isinstance(key, str):
                keybindings[action] = key

        # Symlink settings. The key replaces the defaults wholesale, so it
        # must be a list of patterns: a scalar would iterate as characters
        # ("*" blocks everything) and a non-string element crashes fnmatch
        symlink_config = config_data.get("symlinks", {})
        symlink_blocklist = symlink_config.get("blocklist", list(DEFAULT_SYMLINK_BLOCKLIST))
        if isinstance(symlink_blocklist, list):
            symlink_blocklist = [p for p in symlink_blocklist if isinstance(p, str)]
        else:
            symlink_blocklist = list(DEFAULT_SYMLINK_BLOCKLIST)

        # Environment variables override config file. Empty values are
        # ignored: Path("") is the current directory, which would silently
        # turn $PWD into the tasks dir (every subdirectory a deletable task).
        env_overrides: dict[str, object] = {}
        if os.environ.get("REPOS_DIR"):
            env_overrides["repos_dir"] = repos_dir
            repos_dir = Path(os.environ["REPOS_DIR"]).expanduser()
        if os.environ.get("TASKS_DIR"):
            env_overrides["tasks_dir"] = tasks_dir
            tasks_dir = Path(os.environ["TASKS_DIR"]).expanduser()
        if os.environ.get("TASKTREE_THEME"):
            env_overrides["theme"] = theme
            theme = os.environ["TASKTREE_THEME"]
        if os.environ.get("TASKTREE_DEFAULT_BRANCH"):
            env_overrides["default_base_branch"] = default_base_branch
            default_base_branch = os.environ["TASKTREE_DEFAULT_BRANCH"]
        if os.environ.get("EDITOR") and not editor:
            env_overrides["editor"] = editor
            editor = os.environ["EDITOR"]

        return cls(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=config_dir,
            archive_dir=archive_dir,
            theme=theme,
            show_hidden_files=show_hidden_files,
            refresh_interval=refresh_interval,
            agent_poll_interval=agent_poll_interval,
            forge_poll_interval=forge_poll_interval,
            default_base_branch=default_base_branch,
            auto_push=auto_push,
            git_timeout=git_timeout,
            editor=editor,
            lazygit_path=lazygit_path,
            hunk_path=hunk_path,
            claude_path=claude_path,
            claude_memory_dir=claude_memory_dir,
            claude_repo_memory=claude_repo_memory,
            glab_path=glab_path,
            gh_path=gh_path,
            forge_enabled=forge_enabled,
            forge_gitlab_hosts=forge_gitlab_hosts,
            keybindings=keybindings,
            symlink_blocklist=symlink_blocklist,
            env_overrides=env_overrides,
        )

    @staticmethod
    def _load_toml(config_file: Path) -> dict:
        """Load the TOML config file.

        A parse error is fatal rather than "no config": treating a typo as
        an empty file would fall back to ~/repos and ~/tasks, show the setup
        wizard, and let save() overwrite the user's file with defaults.
        """
        try:
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"Invalid config file {config_file}: {e}") from e
        except OSError as e:
            raise ConfigError(f"Cannot read config file {config_file}: {e}") from e
        if not isinstance(data, dict):
            raise ConfigError(f"Invalid config file {config_file}: expected a table")
        return data

    def set_persistent(self, name: str, value: object) -> None:
        """Set a field and make save() persist it even if the env overrode it."""
        setattr(self, name, value)
        self.env_overrides.pop(name, None)

    def _persisted(self, name: str) -> object:
        """Value save() writes for a field: the pre-env value if overridden."""
        return self.env_overrides.get(name, getattr(self, name))

    @staticmethod
    def _toml_escape(value: str) -> str:
        """Escape a string value for TOML output."""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _toml_list(items: list[str]) -> str:
        """Format a list of strings as a TOML array."""
        escaped = [f'"{Config._toml_escape(item)}"' for item in items]
        return "[" + ", ".join(escaped) + "]"

    def save(self) -> None:
        """Save configuration to config file.

        Written atomically (temp file + rename) so a crash mid-write cannot
        leave a truncated file. Raises OSError when the directory or file is
        not writable; callers decide how to surface that.
        """
        self.config_dir.mkdir(parents=True, exist_ok=True)
        config_file = self.config_dir / "config.toml"

        # Only pin the blocklist when the user changed it: an explicit copy
        # of the defaults would freeze them, so hardened defaults added in
        # later releases (key material patterns) would never reach the user
        if list(self.symlink_blocklist) == list(DEFAULT_SYMLINK_BLOCKLIST):
            blocklist_line = (
                "# Uncomment to replace the built-in defaults (the list replaces, not extends):\n"
                f"# blocklist = {self._toml_list(self.symlink_blocklist)}"
            )
        else:
            blocklist_line = f"blocklist = {self._toml_list(self.symlink_blocklist)}"

        config_content = f'''# tasktree-manager configuration
# https://github.com/ruslan/tasktree-manager

# ============================================================================
# Directory Settings
# ============================================================================

# Directory containing your git repositories
repos_dir = "{self._toml_escape(str(self._persisted("repos_dir")))}"

# Directory for task worktrees
tasks_dir = "{self._toml_escape(str(self._persisted("tasks_dir")))}"

# Directory for finished-task diff archives ("" = <tasks_dir>/.archive)
archive_dir = "{self._toml_escape(self.archive_dir)}"

# ============================================================================
# UI Settings
# ============================================================================
[ui]

# Theme to use (tasktree, tokyo-night, catppuccin-mocha, catppuccin-latte,
# nord, gruvbox, dracula, monokai, rose-pine, textual-dark, textual-light, ...)
theme = "{self._toml_escape(str(self._persisted("theme")))}"

# Show hidden files in file listings
show_hidden_files = {str(self.show_hidden_files).lower()}

# Auto-refresh interval in seconds (0 = disabled)
refresh_interval = {self.refresh_interval}

# Claude agent session poll interval in seconds (0 = disabled)
agent_poll_interval = {self.agent_poll_interval}

# MR/CI forge status poll interval in seconds (0 = disabled)
forge_poll_interval = {self.forge_poll_interval}

# ============================================================================
# Git Settings
# ============================================================================
[git]

# Default base branch for new worktrees (main, master, develop, etc.)
default_base_branch = "{self._toml_escape(str(self._persisted("default_base_branch")))}"

# Automatically push after committing (not recommended for most workflows)
auto_push = {str(self.auto_push).lower()}

# Timeout for git operations in seconds
timeout = {self.git_timeout}

# ============================================================================
# External Tools
# ============================================================================
[tools]

# Preferred editor (leave empty to use $EDITOR)
editor = "{self._toml_escape(str(self._persisted("editor")))}"

# Path to lazygit executable
lazygit_path = "{self._toml_escape(self.lazygit_path)}"

# Path to hunk executable (terminal diff viewer, see https://github.com/modem-dev/hunk)
hunk_path = "{self._toml_escape(self.hunk_path)}"

# Path to claude CLI executable
claude_path = "{self._toml_escape(self.claude_path)}"

# Shared Claude Code auto-memory directory for task sessions.
# Task folders are not git repos, so without this each task gets its own
# memory that is orphaned when the task is deleted. Set to "" to disable.
claude_memory_dir = "{self._toml_escape(self.claude_memory_dir)}"

# Per-repo Claude Code memory for worktree sessions. Writes
# .claude/settings.local.json into each worktree pointing its auto-memory
# at the main repo's memory directory, so memory saved in a worktree
# survives worktree deletion and is shared with future worktrees of the
# same repo and with the main checkout. Set to false to disable.
claude_repo_memory = {str(self.claude_repo_memory).lower()}

# Path to glab executable (GitLab CLI, used for MR/CI status)
glab_path = "{self._toml_escape(self.glab_path)}"

# Path to gh executable (GitHub CLI, used for PR/CI status)
gh_path = "{self._toml_escape(self.gh_path)}"

# ============================================================================
# Forge (MR/PR state via glab/gh)
# ============================================================================
[forge]

# Query MR/PR state from GitLab/GitHub CLIs (glab/gh). Set to false to
# disable all forge lookups (e.g. air-gapped environments).
enabled = {str(self.forge_enabled).lower()}

# Extra self-hosted GitLab hostnames (hosts containing "gitlab" and
# github.com are auto-detected from each repo's origin URL).
gitlab_hosts = {self._toml_list(self.forge_gitlab_hosts)}

# ============================================================================
# Keybindings
# ============================================================================
# Customize keyboard shortcuts. Uncomment and modify to change defaults.
# Available modifiers: ctrl+, shift+, alt+
# Special keys: enter, tab, escape, space, backspace, delete, up, down, left, right
[keybindings]
quit = "{self._toml_escape(self.keybindings.get("quit", "q"))}"
help = "{self._toml_escape(self.keybindings.get("help", "?"))}"
new_task = "{self._toml_escape(self.keybindings.get("new_task", "n"))}"
clone_task = "{self._toml_escape(self.keybindings.get("clone_task", "y"))}"
add_repo = "{self._toml_escape(self.keybindings.get("add_repo", "a"))}"
delete_task = "{self._toml_escape(self.keybindings.get("delete_task", "d"))}"
rename_task = "{self._toml_escape(self.keybindings.get("rename_task", "R"))}"
open_lazygit = "{self._toml_escape(self.keybindings.get("open_lazygit", "g"))}"
show_diff = "{self._toml_escape(self.keybindings.get("show_diff", "h"))}"
open_folder = "{self._toml_escape(self.keybindings.get("open_folder", "o"))}"
open_editor = "{self._toml_escape(self.keybindings.get("open_editor", "e"))}"
open_claude_resume = "{self._toml_escape(self.keybindings.get("open_claude_resume", "c"))}"
open_claude_gui_code = "{self._toml_escape(self.keybindings.get("open_claude_gui_code", "C"))}"
push_all = "{self._toml_escape(self.keybindings.get("push_all", "p"))}"
pull_all = "{self._toml_escape(self.keybindings.get("pull_all", "P"))}"
refresh = "{self._toml_escape(self.keybindings.get("refresh", "r"))}"
toggle_messages = "{self._toml_escape(self.keybindings.get("toggle_messages", "m"))}"
toggle_grouping = "{self._toml_escape(self.keybindings.get("toggle_grouping", "S"))}"
cycle_sort = "{self._toml_escape(self.keybindings.get("cycle_sort", "s"))}"
delete_worktree = "{self._toml_escape(self.keybindings.get("delete_worktree", "D"))}"
dispatch_agent = "{self._toml_escape(self.keybindings.get("dispatch_agent", "b"))}"
focus_next = "{self._toml_escape(self.keybindings.get("focus_next", "tab"))}"
focus_previous = "{self._toml_escape(self.keybindings.get("focus_previous", "shift+tab"))}"
cursor_down = "{self._toml_escape(self.keybindings.get("cursor_down", "j"))}"
cursor_up = "{self._toml_escape(self.keybindings.get("cursor_up", "k"))}"

# ============================================================================
# Symlinks
# ============================================================================
# When creating worktrees, tasktree-manager symlinks gitignored files from the source repo.
# This blocklist specifies patterns to exclude from symlinking (e.g., cache files).
[symlinks]
{blocklist_line}
'''
        tmp_file = config_file.with_name(config_file.name + ".tmp")
        tmp_file.write_text(config_content)
        os.replace(tmp_file, config_file)

    def is_configured(self) -> bool:
        """Check if configuration is valid and directories exist."""
        return (
            self.repos_dir.exists() and self.repos_dir.is_dir() and self.tasks_dir.parent.exists()
        )

    def ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get_archive_dir(self) -> Path:
        """Get the archive directory for finished-task diffs.

        A relative path is anchored under tasks_dir, never $PWD — `finish`
        may run from inside a worktree, and a CWD-relative archive would be
        written into the very tree that is deleted seconds later.
        """
        if self.archive_dir:
            path = Path(self.archive_dir).expanduser()
            if not path.is_absolute():
                path = self.tasks_dir / path
            return path
        return self.tasks_dir / ".archive"

    def get_available_repos(self) -> list[str]:
        """Get list of available repositories in REPOS_DIR."""
        if not self.repos_dir.exists():
            return []

        repos = []
        skip_dirs = {".terraform", "node_modules", "vendor", ".git"}

        for dirpath, dirnames, _ in os.walk(self.repos_dir):
            # Prune directories we don't want to descend into
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]

            # Check if current directory has a .git subdirectory
            current = Path(dirpath)
            if (current / ".git").is_dir():
                try:
                    rel_path = current.relative_to(self.repos_dir)
                    repos.append(str(rel_path))
                except ValueError:
                    continue
                # Don't descend into this repo's subdirectories
                dirnames.clear()

        return sorted(repos)

    def get_editor(self) -> str:
        """Get the editor to use, with fallback to environment or vi."""
        if self.editor:
            return self.editor
        return os.environ.get("EDITOR", "vi")

    def get_keybinding(self, action: str) -> str:
        """Get the keybinding for an action.

        Args:
            action: The action name (e.g., 'quit', 'new_task')

        Returns:
            The key binding string (e.g., 'q', 'ctrl+n')
        """
        return self.keybindings.get(action, DEFAULT_KEYBINDINGS.get(action, ""))
