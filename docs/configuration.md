# Configuration Reference

Complete reference for all tasktree-manager configuration options.

## Table of Contents

- [Configuration System Overview](#configuration-system-overview)
- [Configuration File Location](#configuration-file-location)
- [Complete Configuration Example](#complete-configuration-example)
- [Directory Settings](#directory-settings)
- [UI Settings](#ui-settings)
- [Git Settings](#git-settings)
- [External Tools](#external-tools)
- [Symlinks](#symlinks)
- [Keybindings Reference](#keybindings-reference)
- [Environment Variables](#environment-variables)
- [Themes](#themes)
- [Configuration Precedence](#configuration-precedence)

## Configuration System Overview

tasktree-manager uses a **3-tier configuration system** with the following priority:

1. **Environment Variables** (highest priority) - Override everything
2. **Config File** (`config.toml`) - Persistent user preferences
3. **Default Values** (lowest priority) - Built-in sensible defaults

This allows you to:
- Set permanent preferences in `config.toml`
- Override settings per-session with environment variables
- Use defaults without any configuration

## Configuration File Location

### Default Location

```
~/.config/tasktree-manager/config.toml
```

### XDG Base Directory Support

tasktree-manager respects the XDG Base Directory specification. Set `XDG_CONFIG_HOME` to customize:

```bash
export XDG_CONFIG_HOME=~/.myconfig
# Config will be at: ~/.myconfig/tasktree-manager/config.toml
```

### Creating the Config File

On first run, tasktree-manager creates `config.toml` via the setup wizard. To manually create or reset:

```bash
# Remove existing config (optional)
rm ~/.config/tasktree-manager/config.toml

# Run tasktree-manager to trigger setup wizard
tasktree-manager
```

## Complete Configuration Example

Here's a fully annotated `config.toml` with all available options:

```toml
# tasktree-manager configuration
# https://github.com/yourusername/tasktree-manager

# ============================================================================
# Directory Settings
# ============================================================================

# Directory containing your git repositories
# Supports absolute paths and ~ expansion
repos_dir = "/Users/username/repos"

# Directory for task worktrees
# Created automatically if it doesn't exist
tasks_dir = "/Users/username/tasks"

# Directory for finished-task diff archives
# Relative paths resolve under tasks_dir (never the current directory)
# Default: "" (uses <tasks_dir>/.archive)
archive_dir = ""

# ============================================================================
# UI Settings
# ============================================================================
[ui]

# Theme to use for the interface
# Options: tasktree (default), tokyo-night, catppuccin-mocha, catppuccin-latte,
# catppuccin-frappe, catppuccin-macchiato, nord, gruvbox, dracula, monokai,
# rose-pine, textual-dark, textual-light, ...
theme = "tasktree"

# Show hidden files in file listings
# Default: false
show_hidden_files = false

# Auto-refresh interval in seconds (0 = disabled)
# Periodically refreshes git status in the background
# Default: 30
refresh_interval = 30

# Claude agent session poll interval in seconds (0 = disabled)
# Polls `claude agents --json` for per-worktree session state badges
# Default: 10
agent_poll_interval = 10

# MR/CI forge status poll interval in seconds (0 = disabled)
# Polls glab/gh for MR and pipeline state badges in the worktree list
# Default: 60
forge_poll_interval = 60

# ============================================================================
# Git Settings
# ============================================================================
[git]

# Default base branch for new worktrees
# Common values: main, master, develop, trunk
# Default: main
default_base_branch = "main"

# Automatically push after committing
# Not recommended for most workflows - use manual push (p) instead
# Default: false
auto_push = false

# Timeout for git operations in seconds
# Increase for slow connections or large repos
# Default: 30
timeout = 30

# ============================================================================
# External Tools
# ============================================================================
[tools]

# Preferred editor command
# Leave empty to use $EDITOR environment variable
# Examples: "vim", "nvim", "code", "emacs"
# Default: "" (uses $EDITOR, falls back to vi)
editor = ""

# Path to lazygit executable
# Default: "lazygit" (searches PATH)
lazygit_path = "lazygit"

# Path to hunk executable (terminal diff viewer)
# https://github.com/modem-dev/hunk
# Default: "hunk" (searches PATH)
hunk_path = "hunk"

# Path to claude CLI executable
# Default: "claude" (searches PATH)
claude_path = "claude"

# Shared Claude Code auto-memory directory for task sessions.
# Task folders are not git repositories, so by default Claude Code would key
# its auto memory to the task path — memory that is orphaned when the task is
# deleted. tasktree-manager writes this path as "autoMemoryDirectory" into each
# task's .claude/settings.local.json so every task session reads and writes one
# shared memory pool that persists across tasks.
# Set to "" to disable (each task keeps its own throwaway memory).
# If you relocated Claude Code's config home with $CLAUDE_CONFIG_DIR, point
# this under that directory too (the per-repo worktree memory below and
# session resume already honour the variable).
# Default: "~/.claude/tasktree-memory"
claude_memory_dir = "~/.claude/tasktree-memory"

# Per-repo Claude Code memory for worktree sessions.
# Sessions started inside a worktree would otherwise key their auto memory to
# the worktree path — memory that dies with the worktree. When enabled,
# tasktree-manager writes .claude/settings.local.json into each worktree
# pointing "autoMemoryDirectory" at the main repo's own memory directory
# (~/.claude/projects/<encoded-repo-path>/memory). What Claude learns in any
# worktree of a repo survives worktree deletion and is shared with future
# worktrees of that repo and with sessions in the main checkout. The settings
# file is added to the repo's .git/info/exclude so worktrees stay clean.
# Default: true
claude_repo_memory = true

# Path to glab executable (GitLab CLI, used for MR/CI status)
# Default: "glab" (searches PATH)
glab_path = "glab"

# Path to gh executable (GitHub CLI, used for PR/CI status)
# Default: "gh" (searches PATH)
gh_path = "gh"

# ============================================================================
# Forge (MR/PR state via glab/gh)
# ============================================================================
[forge]

# Query MR/PR and CI state from GitLab/GitHub CLIs.
# Used for worktree badges, squash-merge-aware safety checks, and
# `status --forge`. Set to false to disable all forge lookups
# (e.g. air-gapped environments).
# Default: true
enabled = true

# Extra self-hosted GitLab hostnames. Hosts containing "gitlab" and
# github.com are auto-detected from each repo's origin URL; list hosts
# here only when the hostname doesn't contain "gitlab".
# Default: []
gitlab_hosts = []

# ============================================================================
# Keybindings
# ============================================================================
# Customize keyboard shortcuts
# Uncomment and modify to change defaults
# Available modifiers: ctrl+, shift+, alt+
# Special keys: enter, tab, escape, space, backspace, delete, up, down, left, right
[keybindings]

# Application control
quit = "q"              # Quit application
help = "?"              # Show help modal

# Task management
new_task = "n"          # Create new task
add_repo = "a"          # Add repository to current task
delete_task = "d"       # Delete/finish task
rename_task = "R"       # Rename task display label (folder/branch unchanged, shift+r)
delete_worktree = "D"   # Remove single worktree from task (shift+d)

# Git operations
open_lazygit = "g"      # Open lazygit in selected worktree
show_diff = "h"         # Open hunk diff (task panel = all repos, worktree panel = one repo)
open_editor = "e"       # Open editor in selected task/worktree
open_folder = "o"       # Open folder in new terminal tab
push_all = "p"          # Push all worktrees in current task
pull_all = "P"          # Pull all worktrees in current task (shift+p)
refresh = "r"           # Refresh git status

# Claude Code integration
open_claude_resume = "c"    # Open Claude CLI (resume if a session exists, else new)
open_claude_gui_code = "C"  # Open Claude desktop on Code page in task folder (shift+c)
dispatch_agent = "b"        # Dispatch background Claude agent in selected worktree

# Messages panel
toggle_messages = "m"       # Show/hide the activity messages panel

# Navigation
focus_next = "tab"          # Switch to next panel
focus_previous = "shift+tab" # Switch to previous panel
cursor_down = "j"           # Move cursor down
cursor_up = "k"             # Move cursor up

# Sorting and grouping
cycle_sort = "s"            # Cycle task sort mode
toggle_grouping = "S"       # Toggle worktree grouping (shift+s)

# Appearance
cycle_theme = "t"           # Cycle through the design-system themes

# ============================================================================
# Symlinks
# ============================================================================
# When creating worktrees, gitignored files are symlinked from the source repo.
# Blocklist specifies patterns to exclude (e.g., cache files, key material).
[symlinks]
blocklist = [
    "*.pyc",
    "*.pyo",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "*.log",
    "*.pem",
    "*.key",
    "id_rsa",
]
```

## Directory Settings

| Option     | Type | Default   | Environment Variable | Description                                    |
|------------|------|-----------|---------------------|------------------------------------------------|
| `repos_dir` | path | `~/repos` | `REPOS_DIR`         | Directory containing your git repositories     |
| `tasks_dir` | path | `~/tasks` | `TASKS_DIR`         | Directory where task worktrees will be created |
| `archive_dir` | path | `""` (`<tasks_dir>/.archive`) | - | Directory for finished-task diff archives |

### Details

**`repos_dir`:**
- Must exist before creating tasks
- Can contain repositories in subdirectories (tasktree-manager scans recursively)
- Supports `~` expansion and absolute paths
- Original repositories are NEVER modified

**`tasks_dir`:**
- Created automatically if it doesn't exist
- Each task creates a subdirectory: `tasks_dir/TASK-NAME/`
- Each worktree within: `tasks_dir/TASK-NAME/repo-name/`

### Examples

```toml
# Single repos directory
repos_dir = "/Users/alice/code"

# Multiple levels (tasktree-manager scans recursively)
repos_dir = "/Users/alice/projects"
# Can contain: projects/work/api, projects/personal/blog, etc.

# Separate SSD for tasks (performance)
tasks_dir = "/Volumes/FastSSD/worktrees"
```

## UI Settings

| Option              | Type    | Default         | Environment Variable  | Description                              |
|--------------------|---------|-----------------|-----------------------|------------------------------------------|
| `theme`            | string  | `tasktree`      | `TASKTREE_THEME`     | Color theme for the interface            |
| `show_hidden_files` | boolean | `false`         | -                     | Show hidden files in listings            |
| `refresh_interval`  | integer | `30`            | -                     | Auto-refresh interval in seconds (0 = disabled) |
| `agent_poll_interval` | integer | `10`          | -                     | Claude agent session poll in seconds (0 = disabled) |
| `forge_poll_interval` | integer | `60`          | -                     | MR/CI forge status poll in seconds (0 = disabled) |

### `theme`

Available themes (press `Ctrl+P` in app to switch):

- `tasktree` - Default: lazygit-classic ANSI palette with green focus borders
- `tokyo-night` - Blue accent on deep blue-black
- `catppuccin-mocha` - Mauve accent, soothing pastels
- `gruvbox` - Orange accent, retro warm
- `dracula` - Purple accent, high-contrast pastels
- `nord` - Frost cyan accent, arctic palette

These six come from the tasktree design system, with matched panel layering
and selection colors. All other Textual built-in themes also work
(`catppuccin-latte`, `rose-pine`, `monokai`, `solarized-dark`,
`textual-dark`/`-light`, ...).

The whole UI is styled with Textual design tokens (panel surfaces, focus
borders, selection bars, footer keycaps), so every theme restyles all of it
consistently.

### `show_hidden_files`

Currently unused (reserved for future file browser features).

### `refresh_interval`

Automatically refreshes git status for all tasks and worktrees in the background:

- Default: `30` (every 30 seconds)
- Set to `0` to disable auto-refresh
- Runs in a background thread — does not block the UI
- Preserves current task and worktree selection during refresh

```toml
[ui]
refresh_interval = 15  # Refresh every 15 seconds
```

## Git Settings

| Option                | Type    | Default | Environment Variable      | Description                              |
|----------------------|---------|---------|---------------------------|------------------------------------------|
| `default_base_branch` | string  | `main`  | `TASKTREE_DEFAULT_BRANCH` | Default branch for creating worktrees    |
| `auto_push`          | boolean | `false` | -                         | Auto-push after committing (not recommended) |
| `timeout`            | integer | `30`    | -                         | Git operation timeout in seconds         |

### Details

**`default_base_branch`:**
- Used when creating new tasks (can override per-task)
- Must exist in the repository
- Common values: `main`, `master`, `develop`, `trunk`
- Example: If set to `main`, new worktrees branch from `main`

**`auto_push`:**
- **Not recommended** for most workflows
- When `true`, git operations auto-push to remote
- Most users should use manual push (`p` key) for control

**`timeout`:**
- Timeout for git commands that touch the network (fetch, push, pull) and worktree creation
- Local status queries use a fixed short timeout (5s) and are not affected
- Increase for slow networks or large repositories
- Set to `60` or higher for very large repos

## External Tools

| Option         | Type   | Default     | Environment Variable | Description                          |
|---------------|--------|-------------|---------------------|--------------------------------------|
| `editor`      | string | `""`        | `EDITOR`            | Command to launch your editor        |
| `lazygit_path` | string | `"lazygit"` | -                   | Path to lazygit executable           |
| `hunk_path`   | string | `"hunk"`    | -                   | Path to hunk diff-viewer executable  |
| `glab_path`   | string | `"glab"`    | -                   | Path to GitLab CLI (MR/CI status)    |
| `gh_path`     | string | `"gh"`      | -                   | Path to GitHub CLI (PR/CI status)    |

## Forge Settings

MR/PR and CI state is looked up through the GitLab (`glab`) and GitHub (`gh`)
CLIs. The provider is auto-detected per repository from its `origin` URL:
`github.com` uses `gh`; hosts containing "gitlab" (or listed in
`gitlab_hosts`) use `glab`; anything else (including local-path remotes) is
skipped. Lookups power the worktree MR/CI badges, squash-merge-aware safety
checks, and `tasktree-manager status --forge`. Missing CLIs or network
failures degrade silently — features fall back to plain git behavior.

| Option         | Type       | Default | Description                                        |
|----------------|------------|---------|----------------------------------------------------|
| `enabled`      | boolean    | `true`  | Master switch for all forge lookups                |
| `gitlab_hosts` | array[str] | `[]`    | Extra self-hosted GitLab hostnames to auto-detect  |

### Details

**`editor`:**
- Leave empty (`""`) to use `$EDITOR` environment variable
- Fallback: `vi`
- Examples: `"vim"`, `"nvim"`, `"code"`, `"emacs -nw"`
- Used when pressing `e` to open editor in task/worktree folder

**`lazygit_path`:**
- Default `"lazygit"` searches PATH
- Use absolute path for custom location: `"/opt/homebrew/bin/lazygit"`
- Install lazygit: `brew install lazygit` (macOS), `apt install lazygit` (Ubuntu)

**`hunk_path`:**
- [hunk](https://github.com/modem-dev/hunk) is a review-first terminal diff viewer
- Default `"hunk"` searches PATH
- Use absolute path for custom location: `"/opt/homebrew/bin/hunk"`
- Install hunk: `brew install hunk` (macOS) or `npm i -g hunkdiff`
- Used when pressing `h`: from the task panel it opens a combined diff across all the task's repos; from the worktree panel it opens the selected repo's diff

## Symlinks

When creating worktrees, tasktree-manager automatically symlinks gitignored files (like `.env`) from the source repository. This allows environment files to be shared without copying.

| Option      | Type       | Default        | Description                                    |
|-------------|------------|----------------|------------------------------------------------|
| `blocklist` | array[str] | (see below)    | Glob patterns for files to exclude from symlinking |

### Default Blocklist

By default, these patterns are excluded from symlinking. Caches and build
artifacts are excluded as noise; key material (`*.pem`, `*.key`, SSH keys)
is excluded so private keys never spread beyond the main checkout:

```toml
[symlinks]
blocklist = [
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
```

### How It Works

1. When a worktree is created, tasktree-manager asks git for the repo's
   ignored files (`git ls-files --others --ignored --exclude-standard`), so
   full gitignore semantics apply: nested `.gitignore` files work, and a
   root pattern like `*.log` matches in subdirectories
2. Wholly-ignored directories (e.g. `node_modules/`) are skipped entirely —
   their contents are never walked or symlinked
3. Files matching the blocklist (by filename or repo-relative path, so
   patterns like `secrets/*` work) and anything under `.git/` or `.claude/`
   are skipped
4. Remaining files are symlinked to the worktree

### Customizing the Blocklist

**Allow all gitignored files (empty blocklist):**
```toml
[symlinks]
blocklist = []
```

**Block specific patterns:**
```toml
[symlinks]
blocklist = [
    ".env*",        # Block all .env files
    "*.secret",     # Block secret files
    "credentials*", # Block credential files
]
```

**Add to default blocklist (must include ALL default patterns — an explicit
blocklist replaces the defaults entirely, including the key-material
protection):**
```toml
[symlinks]
blocklist = [
    # Default patterns
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
    # Your additions
    "*.tmp",
    ".DS_Store",
]
```

> **Upgrading note:** if your existing `config.toml` already contains a
> `blocklist`, it keeps overriding the defaults — the key-material patterns
> added in newer versions do NOT apply until you add them (or delete the
> `blocklist` line to inherit the defaults). Saving the config from the app
> (for example on a theme switch) no longer writes the default list: the key
> is only written when you customised it, so the built-in defaults keep
> applying as they evolve.

### Common Use Cases

**Symlink environment files, block caches and keys:**
```toml
[symlinks]
blocklist = ["*.pyc", "__pycache__", ".coverage", "*.log", "*.pem", "*.key", "id_rsa"]
```
This allows `.env`, `.mise.toml` to be symlinked while blocking cache files
and private keys.

**Block everything (disable symlinks):**
```toml
[symlinks]
blocklist = ["*"]
```

## Keybindings Reference

All 22 customizable keybindings with descriptions:

### Application Control

| Action   | Default | Description                             | Customization Example     |
|----------|---------|------------------------------------------|---------------------------|
| `quit`   | `q`     | Quit tasktree-manager                   | `quit = "ctrl+q"`         |
| `help`   | `?`     | Show help modal with keybindings        | `help = "F1"`             |

### Task Management

| Action        | Default | Description                            | Customization Example      |
|---------------|---------|----------------------------------------|----------------------------|
| `new_task`    | `n`     | Create a new task                      | `new_task = "ctrl+n"`      |
| `clone_task`  | `y`     | Clone current task (same repos, new name) | `clone_task = "ctrl+y"`  |
| `add_repo`    | `a`     | Add repository to current task         | `add_repo = "ctrl+a"`      |
| `delete_task` | `d`     | Delete/finish current task             | `delete_task = "delete"`   |
| `rename_task` | `R`     | Rename task display label (alias only) | `rename_task = "ctrl+r"`   |

### Git Operations

| Action         | Default  | Description                           | Customization Example       |
|----------------|----------|---------------------------------------|-----------------------------|
| `open_lazygit` | `g`      | Open lazygit in selected worktree     | `open_lazygit = "ctrl+g"`   |
| `show_diff`    | `h`      | Open hunk diff (task = all repos, worktree = one) | `show_diff = "ctrl+h"` |
| `open_editor`  | `e`      | Open editor in task/worktree folder   | `open_editor = "ctrl+e"`    |
| `open_folder`  | `o`      | Open folder in new terminal tab       | `open_folder = "ctrl+o"`    |
| `push_all`     | `p`      | Push all worktrees in current task    | `push_all = "ctrl+p"`       |
| `pull_all`     | `P`      | Pull all worktrees in current task    | `pull_all = "ctrl+shift+p"` |
| `refresh`      | `r`      | Refresh git status for all worktrees  | `refresh = "F5"`            |

### Claude Code Integration

| Action                | Default | Description                                          | Customization Example                |
|-----------------------|---------|------------------------------------------------------|--------------------------------------|
| `open_claude_resume`  | `c`     | Open Claude CLI (resume if session exists, else new) | `open_claude_resume = "ctrl+c"`      |
| `open_claude_gui_code`| `C`     | Open Claude desktop on Code page in task folder      | `open_claude_gui_code = "ctrl+shift+c"` |
| `toggle_messages`     | `m`     | Show/hide activity messages panel                    | `toggle_messages = "ctrl+m"`         |

### Navigation

| Action            | Default     | Description                    | Customization Example            |
|-------------------|-------------|--------------------------------|----------------------------------|
| `focus_next`      | `tab`       | Switch to next panel           | `focus_next = "ctrl+]"`          |
| `focus_previous`  | `shift+tab` | Switch to previous panel       | `focus_previous = "ctrl+["`      |
| `cursor_down`     | `j`         | Move cursor down in lists      | `cursor_down = "down"`           |
| `cursor_up`       | `k`         | Move cursor up in lists        | `cursor_up = "up"`               |

### Sorting & Grouping

| Action            | Default | Description                              | Customization Example            |
|-------------------|---------|------------------------------------------|----------------------------------|
| `cycle_sort`      | `s`     | Cycle task sort mode                     | `cycle_sort = "ctrl+s"`          |
| `toggle_grouping` | `S`     | Toggle worktree grouping by dirty/clean  | `toggle_grouping = "ctrl+g"`     |
| `cycle_theme`     | `t`     | Cycle through the design-system themes   | `cycle_theme = "ctrl+t"`         |

### Available Key Syntax

**Single characters:**
- Letters: `a-z` (case-insensitive)
- Numbers: `0-9`
- Punctuation: `?`, `/`, `.`, `,`, `;`, `'`, etc.

**Special keys:**
- `enter`, `tab`, `escape`, `space`
- `backspace`, `delete`
- `up`, `down`, `left`, `right`
- `home`, `end`, `pageup`, `pagedown`
- `F1` through `F12`

**Modifiers:**
- `ctrl+key` - Control key combinations
- `shift+key` - Shift key combinations (works with special keys like `tab`)
- `alt+key` - Alt/Option key combinations

**Platform notes:**
- On macOS, `alt+` may not work reliably in all terminals
- Some terminals may intercept certain key combinations (e.g., `ctrl+t`)
- Test your custom bindings to ensure terminal compatibility

### Customization Examples

**Vim-style navigation:**
```toml
[keybindings]
cursor_down = "j"
cursor_up = "k"
focus_next = "l"
focus_previous = "h"
```

**IDE-style shortcuts:**
```toml
[keybindings]
new_task = "ctrl+n"
delete_task = "ctrl+d"
open_folder = "ctrl+t"
refresh = "F5"
quit = "ctrl+q"
```

**Arrow keys navigation:**
```toml
[keybindings]
cursor_down = "down"
cursor_up = "up"
focus_next = "right"
focus_previous = "left"
```

## Environment Variables

Override configuration for a single session using environment variables:

| Variable                  | Config Equivalent      | Example                          |
|---------------------------|------------------------|----------------------------------|
| `REPOS_DIR`               | `repos_dir`            | `export REPOS_DIR=~/code`        |
| `TASKS_DIR`               | `tasks_dir`            | `export TASKS_DIR=~/worktrees`   |
| `TASKTREE_THEME`          | `ui.theme`             | `export TASKTREE_THEME=nord`     |
| `TASKTREE_DEFAULT_BRANCH` | `git.default_base_branch` | `export TASKTREE_DEFAULT_BRANCH=develop` |
| `EDITOR`                  | `tools.editor` (fallback: used only when `tools.editor` is empty) | `export EDITOR=nvim` |
| `XDG_CONFIG_HOME`         | (config location)      | `export XDG_CONFIG_HOME=~/.cfg`  |

Environment overrides apply to the running session only: saving the config (for
example by switching themes with `t`) writes the config-file values back, never the
overridden ones. Empty values (`TASKS_DIR=`) are ignored. A config file that fails to
parse is an error at startup, not an empty config.

### Usage Examples

**Temporary different repos directory:**
```bash
REPOS_DIR=~/other-projects tasktree-manager
```

**Try a theme without changing config:**
```bash
TASKTREE_THEME=gruvbox tasktree-manager
```

**Use different config location:**
```bash
XDG_CONFIG_HOME=~/.myconfig tasktree-manager
```

**Multiple overrides:**
```bash
REPOS_DIR=~/work TASKS_DIR=/tmp/tasks TASKTREE_THEME=nord tasktree-manager
```

## Themes

### Switching Themes

**In the app:**
1. Press `Ctrl+P` to open Command Palette
2. Search for "theme"
3. Select your preferred theme
4. Theme is saved automatically to `config.toml`

**Via config file:**
```toml
[ui]
theme = "nord"
```

**Via environment variable:**
```bash
TASKTREE_THEME=dracula tasktree-manager
```

### Theme Descriptions

| Theme                | Style               | Best For                          |
|----------------------|---------------------|-----------------------------------|
| `tasktree`           | Lazygit-style ANSI  | Default, terminal-native feel     |
| `tokyo-night`        | Modern dark         | Clean, professional               |
| `catppuccin-mocha`   | Soothing pastel     | Popular, easy on the eyes         |
| `gruvbox`            | Retro warm          | Nostalgic, comfortable            |
| `dracula`            | Pastel dark         | Popular, easy to read             |
| `nord`               | Arctic blue         | Low-contrast, easy on eyes        |

### Theme Persistence

Theme selection via `Ctrl+P` automatically updates `config.toml`:

```toml
[ui]
theme = "tokyo-night"
```

Your theme persists across sessions unless overridden by `TASKTREE_THEME` environment variable.

## Configuration Precedence

When the same setting is defined in multiple places, this priority order applies:

### Priority Order (Highest to Lowest)

1. **Environment Variables** - Session-specific overrides
2. **Config File** (`~/.config/tasktree-manager/config.toml`) - User preferences
3. **Default Values** - Built-in sensible defaults

### Examples

#### Example 1: repos_dir Resolution

```toml
# config.toml
repos_dir = "/Users/alice/repos"
```

```bash
# Environment variable
export REPOS_DIR=~/work

# Run tasktree-manager
tasktree-manager
```

**Result:** Uses `~/work` (environment variable wins)

#### Example 2: theme Resolution

```toml
# config.toml
[ui]
theme = "nord"
```

```bash
# No environment variable
tasktree-manager
```

**Result:** Uses `nord` from config.toml

#### Example 3: default_base_branch Resolution

```toml
# config.toml has no git.default_base_branch
```

```bash
# No environment variable
tasktree-manager
```

**Result:** Uses `main` (built-in default)

#### Example 4: Multiple Settings

```toml
# config.toml
repos_dir = "/Users/alice/repos"
tasks_dir = "/Users/alice/tasks"

[ui]
theme = "gruvbox"

[git]
default_base_branch = "develop"
```

```bash
export REPOS_DIR=~/work
export TASKTREE_THEME=nord
# TASKS_DIR not set
# TASKTREE_DEFAULT_BRANCH not set

tasktree-manager
```

**Result:**
- `repos_dir`: `~/work` (env var)
- `tasks_dir`: `/Users/alice/tasks` (config file)
- `theme`: `nord` (env var)
- `default_base_branch`: `develop` (config file)

### Debugging Configuration

To see which configuration is being used:

1. Open help modal (`?` key)
2. Bottom shows config location: `Config: ~/.config/tasktree-manager/config.toml`
3. View actual file:
   ```bash
   cat ~/.config/tasktree-manager/config.toml
   ```

4. Check environment variables:
   ```bash
   env | grep -E '(REPOS_DIR|TASKS_DIR|TASKTREE_|EDITOR|SHELL)'
   ```

## Next Steps

- [User Guide](user-guide.md) - Learn workflows and best practices
- [Troubleshooting](troubleshooting.md) - Configuration issues and solutions
- [Installation Guide](installation.md) - Setup and requirements
