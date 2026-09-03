# tasktree-manager

> A beautiful TUI for managing git worktrees across multiple repositories

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-228%20passed-green.svg)](./tests/)

**tasktree-manager** is a terminal user interface (TUI) application for managing development tasks that span multiple git repositories. Create tasks, organize worktrees, and track status across your entire codebase—all from a beautiful, keyboard-driven interface inspired by [lazygit](https://github.com/jesseduffield/lazygit).

## ✨ Features

- 🎯 **Task-Based Workflow** - Group related worktrees across multiple repositories
- 🌳 **Git Worktree Management** - Create, delete, and manage worktrees seamlessly
- 📊 **Real-Time Status** - See uncommitted changes, branch info, and sync status at a glance
- 🔀 **Sorting & Grouping** - Sort tasks by name/date/status, group worktrees by dirty/clean
- 🎨 **Beautiful Themes** - lazygit-inspired default plus 20+ themes (Catppuccin, Tokyo Night, Nord, ...) via Command Palette (Ctrl+P)
- ⌨️ **Keyboard-First** - Navigate and control everything without touching the mouse
- 🚀 **Fast & Responsive** - Parallel git operations with loading indicators
- 🔧 **Flexible Configuration** - TOML config file, custom keybindings, environment variables
- 🤖 **Headless CLI** - Create, list, inspect, finish, and delete tasks from scripts and AI agents without opening the TUI
- 🛰️ **Agent Dashboard** - Live Claude Code session state per worktree (from `claude agents`), plus one-key background-agent dispatch — the multi-repo agent view Claude Code lacks natively
- 🔀 **Forge-Aware Safety** - MR/PR and CI state via `glab`/`gh`; squash- and rebase-merged branches count as merged instead of blocking deletion forever
- 📦 **Finish Flow with Archives** - Ending a task saves its combined diff (committed-but-unmerged + uncommitted) to an archive before deleting

## 📊 Status Indicators

| Indicator | Meaning |
|-----------|---------|
| `●` red | Uncommitted changes |
| `◆` blue | Has CLAUDE.md file |
| `⟳` magenta | Claude Code session running / agent working |
| `!` yellow | Claude Code session waiting for input |
| `▣` green | Agent session ready (idle) |
| `✓` green | Clean worktree / Claude session ended |
| `✗ N` red | N files changed |
| `↑N` green | N commits ahead of remote |
| `↓N` yellow | N commits behind remote |
| `○` green / `●` magenta / `×` red | MR open / merged / closed |
| `◐` yellow / `✔` green / `✘` red | CI running / passed / failed |

## 🚀 Quick Start

### Installation

```bash
# Using pipx (recommended)
pipx install tasktree-manager
```

See the [Installation Guide](docs/installation.md) for other methods and platform-specific instructions.

### First Run

```bash
tasktree-manager
```

On first run, you'll configure:
- **Repositories Directory**: Where your git repos live (e.g., `~/repos`)
- **Tasks Directory**: Where worktrees will be created (e.g., `~/tasks`)

### Basic Workflow

1. **Create a task** - Press `n`, enter task name, select repositories
2. **Work on code** - Press `e` for editor, `g` for lazygit, or `o` for a shell in a new terminal tab
3. **Review changes** - Press `h` to view the diff in [hunk](https://github.com/modem-dev/hunk) (all repos from the task panel, one repo from the worktree panel)
4. **Push changes** - Press `p` to push all worktrees
5. **Delete task** - Press `d` when finished

For detailed workflows and examples, see the [User Guide](docs/user-guide.md).

### Headless CLI

Running `tasktree-manager` with arguments skips the TUI — useful for scripts and AI-agent
workflows (e.g. a skill that creates a Jira ticket and then the matching task):

```bash
tasktree-manager create DIC-1901-argocd-tls --repos backend,frontend  # --base overrides the default base branch
tasktree-manager list --json     # tasks with repos and dirty state (plain text without --json)
tasktree-manager repos           # available repos in REPOS_DIR
tasktree-manager add-repo DIC-1901-argocd-tls infra
tasktree-manager status                       # current task inferred from $PWD; also --json / --oneline / --forge
tasktree-manager finish DIC-1901-argocd-tls   # safety sweep -> archive diff -> delete; --push / --no-archive / --force
tasktree-manager delete DIC-1901-argocd-tls   # archive diff -> delete; refuses on unfinished work; --force overrides
```

Exit code is 0 on success, 1 on failure with the reason on stderr. `delete` and `finish` run
the same safety check as the TUI (uncommitted, unpushed, or unmerged work blocks deletion);
with `glab`/`gh` installed, squash/rebase-merged branches are recognized as merged.
`status --oneline` emits a compact `TASK repoA✓ repoB●2↑1` summary that slots straight into
a Claude Code statusline or shell prompt.

## 📖 Documentation

**Complete guides:**
- [Installation Guide](docs/installation.md) - Platform-specific setup, system requirements, troubleshooting
- [User Guide](docs/user-guide.md) - Workflows, keyboard shortcuts, tips and best practices
- [Configuration Reference](docs/configuration.md) - All config options, keybindings, themes
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions

**Quick Reference:**

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| `n` | New task | `g` | Open lazygit |
| `a` | Add repo | `h` | Show diff (hunk) |
| `d` | Delete task | `e` | Open editor |
| `p` | Push all | `o` | Open folder |
| `P` | Pull all | `y` | Clone task |
| `c` | Claude (resume) | `C` | Claude (new) |
| `b` | Dispatch agent | `D` | Delete worktree |
| `r` | Refresh | `s` | Sort tasks |
| `S` | Group worktrees | `m` | Messages |
| `t` | Cycle theme | `Tab` | Next panel |
| `R` | Rename task | | |
| `?` | Show help | `q` | Quit |

**Themes:** The default `tasktree` theme pairs a lazygit-classic ANSI palette with layered panels, numbered title bars, green focus borders, and a keycap footer. Five more design-system palettes ship tuned to the same shape — tokyo-night, catppuccin-mocha, gruvbox, dracula, nord — and every other Textual built-in theme works too (`Ctrl+P` to switch); the whole UI is styled with Textual design tokens, so any theme restyles it consistently.

## 🏗️ How It Works

tasktree-manager uses [git worktrees](https://git-scm.com/docs/git-worktree) to create isolated working directories for each task. Work on multiple branches simultaneously without stashing or context switching.

**Directory Structure:**
```
~/repos/                    # Your git repositories (never modified)
  ├── backend/
  └── frontend/

~/tasks/                    # Task worktrees (managed by tasktree-manager)
  ├── FEAT-123/
  │   ├── backend/          # Worktree on branch FEAT-123
  │   └── frontend/         # Worktree on branch FEAT-123
  └── BUG-456/
      └── backend/
```

Learn more in the [User Guide](docs/user-guide.md#core-concepts).

## 🛠️ Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development setup and guidelines.

**Quick Start:**
```bash
git clone https://github.com/yourusername/tasktree-manager.git
cd tasktree-manager
mise install
mise run install
mise run test
```

**Common Commands:**
```bash
mise run dev           # Run with dev console
mise run test          # Run tests
mise run lint:fix      # Auto-fix lint issues
```

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Quick contribution steps:**
1. Fork and create feature branch
2. Make changes and add tests
3. Run `mise run test` and `mise run lint`
4. Submit pull request

## 📋 Requirements

- Python 3.10+ (3.13+ recommended)
- Git 2.0+
- 256-color terminal
- Unix-like OS (macOS, Linux, WSL2). Opening a folder, editor or Claude session in a
  new terminal tab (`o`, `e`, `c`) drives Ghostty via AppleScript and is macOS-only;
  elsewhere those keys show a notice

See [Installation Guide](docs/installation.md) for detailed requirements and setup.

## 🐛 Troubleshooting

Common issues and quick fixes:

- **"No repositories found"** - Check `repos_dir` in config contains git repos
- **"Worktree creation failed"** - Verify base branch exists and you have permissions
- **Theme not changing** - Use `Ctrl+P` to select theme, or check config file permissions
- **Command not found** - Run `pipx ensurepath` and restart terminal

For comprehensive troubleshooting, see the [Troubleshooting Guide](docs/troubleshooting.md).

## 🗺️ Roadmap

Recently shipped: agent dashboard (per-worktree Claude session badges + background dispatch),
forge-aware merged detection (glab/gh, squash/rebase merges), MR/CI status badges,
guided `finish` flow with diff archiving, `status` subcommand for scripts and statuslines.

Upcoming:
- **v0.3.0** - Search/filter, task templates
- **v0.4.0** - JIRA status column, git hooks, automation
- **v1.0.0** - Stable release

See [ROADMAP.md](ROADMAP.md) and [CHANGELOG.md](CHANGELOG.md) for details.

## 📄 License

MIT License - see [LICENSE](./LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by [lazygit](https://github.com/jesseduffield/lazygit)
- Built with [Textual](https://github.com/Textualize/textual)
- Themes adapted from VS Code and Catppuccin

## 💬 Support & Community

- 🐛 [Bug Reports](https://github.com/yourusername/tasktree-manager/issues)
- 💡 [Feature Requests](https://github.com/yourusername/tasktree-manager/issues)
- 💬 [Discussions](https://github.com/yourusername/tasktree-manager/discussions)
- 📖 [Documentation](docs/)

---

**Made with ❤️ by developers, for developers** | [⭐ Star this repo](https://github.com/yourusername/tasktree-manager)
