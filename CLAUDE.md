# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

tasktree-manager is a TUI application for managing git worktree-based tasks, styled like lazygit. It allows users to create tasks that span multiple repositories, each with their own worktree.

## Commands

All commands use mise. Run `mise install` first to set up the environment.

```bash
mise run install       # Install dependencies (uses uv pip)
mise run test          # Run all tests
mise run test:cov      # Run tests with coverage
mise run lint          # Run ruff linter
mise run lint:fix      # Auto-fix lint issues
mise run format        # Format code with ruff
mise run dev           # Run app in Textual dev mode with console
mise run run           # Run the app normally
```

Run a single test:
```bash
pytest tests/test_app.py::TestTaskTreeApp::test_app_starts -v
```

## Architecture

### Core Data Model

- **Task**: A named task (e.g., "DIC-1813") containing multiple worktrees, stored as a directory in `TASKS_DIR` (~/.wtasks)
- **Worktree**: A git worktree within a task, created from a repo in `REPOS_DIR` (~/repos). Branch name matches task name.
- **GitStatus**: Status info for a worktree (branch, staged/modified/untracked files, ahead/behind counts)

### Services Layer (`tasktree_manager/services/`)

- `config.py`: Loads configuration from environment variables (`REPOS_DIR`, `TASKS_DIR`)
- `task_manager.py`: CRUD operations for tasks and worktrees (creates git worktrees via subprocess)
- `git_ops.py`: Git status queries, push/pull operations (all via subprocess)

### Headless CLI (`tasktree_manager/cli.py`)

`tasktree-manager` with any argument routes to the CLI instead of the TUI (dispatch in
`app.py:main`). Subcommands `create`/`list`/`delete`/`add-repo`/`repos` are thin wrappers over
the services layer for scripts and AI agents (the `/wtask` skill drives them). `delete` enforces
the same `check_task_safety` gate as the TUI unless `--force`, and always archives the remaining
diff first. Task names are a single path segment (no `/`); `get_task` validates names because
its result is rmtree'd.

### Theming

Uses Textual's theming system with design tokens (`$panel`, `$surface`, `$border`, `$border-blurred`, `$block-cursor-*`, `$footer-key-*`, etc.) so all styling adapts to any theme. `tasktree_manager/themes.py` registers six themes from the design system: the default `tasktree` (lazygit-classic ANSI palette) plus tuned `tokyo-night`, `catppuccin-mocha`, `gruvbox`, `dracula`, and `nord` (these override Textual's built-ins of the same name so the design's panel layering and selection colors apply). Panels sit darker than the screen ground; title bars carry a `[n]` number, dim context, and a right-aligned counter. Switch themes via the Command Palette (`Ctrl+P`); other Textual built-ins also work. The design source of truth is the "TaskTree-Manager design system" Claude Design project (tokens, component specs, full-app mockup).

### Widgets Layer (`tasktree_manager/widgets/`)

All widgets extend Textual's `ListView` or `Static`:
- `task_list.py`: Left panel showing tasks with dirty indicators
- `worktree_list.py`: Right panel showing worktrees for selected task
- `status_panel.py`: Bottom panel showing git status for selected worktree
- `create_modal.py`: Modal dialogs (all extend `ThemedModalScreen` base class)

### App (`tasktree_manager/app.py`)

`TaskTreeApp` is the main Textual App. It:
- Composes the 3-panel layout
- Handles message events from list widgets (`TaskHighlighted`, `WorktreeHighlighted`)
- Implements actions for keybindings (n=new task, d=delete, g=lazygit, etc.)
- Uses `app.suspend()` to shell out to lazygit or $SHELL
- Uses static `CSS` class variable with Textual design tokens

### Styling Pattern

CSS uses Textual's design tokens (e.g., `$primary`, `$background`, `$surface`, `$error`) for theme-aware styling:
- Main app CSS is defined in `TaskTreeApp.CSS` class variable
- Modals use `DEFAULT_CSS` class attribute with design tokens
- List items use `.--highlight` styling for both the ListItem and its child Static widget

## Testing

Tests use pytest-asyncio for async Textual widget testing. The `conftest.py` creates:
- Temporary repos/tasks directories
- Real git repos with initial commits for integration tests
- Fixtures: `config`, `task_manager`, `sample_repo`, `sample_repos`, `app`

Example test pattern for Textual apps:
```python
async def test_app_starts():
    async with TaskTreeApp().run_test() as pilot:
        assert pilot.app.query_one("#task-list")
```

## Development Preferences

- **Documentation lookup**: Use Context7 MCP tool when needing up-to-date library documentation (Textual, Rich, etc.)
- **Code intelligence**: Use Python LSP for type checking and diagnostics
- **Documentation updates**: After implementing tasks or plans, update README.md and other relevant markdown files to reflect changes
