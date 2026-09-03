# User Guide

Complete guide to using tasktree-manager for managing development tasks across multiple repositories.

## Table of Contents

- [Introduction](#introduction)
- [Core Concepts](#core-concepts)
- [Getting Started](#getting-started)
- [Understanding the Interface](#understanding-the-interface)
- [Complete Keyboard Reference](#complete-keyboard-reference)
- [Common Workflows](#common-workflows)
- [Working with Worktrees](#working-with-worktrees)
- [Integration with Tools](#integration-with-tools)
- [Tips and Best Practices](#tips-and-best-practices)
- [Limitations](#limitations)

## Introduction

tasktree-manager is a terminal user interface (TUI) application that helps you manage development tasks spanning multiple git repositories. It uses [git worktrees](https://git-scm.com/docs/git-worktree) to create isolated working directories for each task, allowing you to:

- Work on multiple tasks simultaneously without stashing
- Organize related changes across multiple repositories
- Track git status for all worktrees at a glance
- Quickly switch contexts between tasks

### What is tasktree-manager?

Think of tasktree-manager as a **task organizer** for multi-repo development:

- **Task**: A named unit of work (e.g., "FEAT-123", "bugfix-login")
- **Worktree**: A git working directory for one repository within that task
- **tasktree-manager**: The tool that manages creating, organizing, and cleaning up these worktrees

### When to Use tasktree-manager

**Ideal for:**
- Microservices architecture (backend, frontend, infrastructure)
- Monorepo-adjacent workflows (related but separate repositories)
- Feature development spanning multiple repos
- Teams using JIRA, Linear, or similar task trackers
- Developers who juggle multiple parallel tasks

**Not ideal for:**
- Single repository development (use `git worktree` directly)
- Projects with no concurrent task work
- Casual git users (requires familiarity with git workflows)

## Core Concepts

### Tasks

A **task** is a named container for related work across multiple repositories.

```
Task: FEAT-123
├── backend/     (worktree on branch FEAT-123)
├── frontend/    (worktree on branch FEAT-123)
└── api-docs/    (worktree on branch FEAT-123)
```

**Characteristics:**
- Created with a unique name (e.g., `FEAT-123`, `BUG-456-auth`)
- Contains one or more worktrees
- Stored in `TASKS_DIR/task-name/`
- Each task gets its own set of branches across selected repos

### Worktrees

A **worktree** is a git working directory for a specific repository within a task.

**Key points:**
- Each worktree is a full git working directory
- Located at: `TASKS_DIR/task-name/repo-name/`
- On a branch matching the task name
- Independent from your main repository
- Tracked for uncommitted changes, unpushed commits, and sync status

### Directory Structure

```
~/repos/                          # REPOS_DIR (original repositories, never modified)
  ├── backend/.git
  ├── frontend/.git
  └── infrastructure/.git

~/tasks/                          # TASKS_DIR (task worktrees)
  ├── FEAT-123/                   # Task directory
  │   ├── backend/                # Worktree for backend
  │   │   ├── .git               # Git directory (worktree link)
  │   │   └── src/               # Working files
  │   └── frontend/               # Worktree for frontend
  │       ├── .git
  │       └── src/
  └── BUG-456/                    # Another task
      └── backend/

~/.config/tasktree-manager/
  └── config.toml                 # Configuration
```

## Getting Started

### Your First Task

1. **Launch tasktree-manager:**
   ```bash
   tasktree-manager
   ```

2. **Create a task:**
   - Press `n` (new task)
   - Enter task name: `FEAT-123`
   - Enter base branch: `main` (or `master`)
   - Search/filter repositories if needed
   - Select repositories with `Space`
   - Press Tab to "Create" button, then Enter

3. **Result:**
   - Task `FEAT-123` created in `~/tasks/FEAT-123/`
   - Worktrees created for each selected repository
   - Branches `FEAT-123` created in each repository
   - Task appears in the left panel with worktree count

### Making Your First Changes

1. **Select a worktree:**
   - Use `j/k` or arrow keys to navigate
   - Press `Tab` to switch between panels
   - Highlight a worktree in the right panel

2. **Open lazygit:**
   - Press `g` to open lazygit in the selected worktree
   - Stage files, commit changes, resolve conflicts
   - Exit lazygit (press `q` in lazygit)

3. **Review the diff:**
   - Press `h` from the worktree panel to review that repo's changes in [hunk](https://github.com/modem-dev/hunk)
   - Press `h` from the task panel to review a combined diff across **all** the task's repos at once
   - Exit hunk (press `q`)

4. **Or open a shell:**
   - Press `o` to open the worktree in a new terminal tab
   - Make changes with your editor/IDE
   - Run build/test commands
   - Close the tab (or switch back) when done

5. **Push changes:**
   - Press `p` to push all worktrees in the task
   - Or use lazygit (`g`) to push individually

6. **Delete the task:**
   - Press `d` to delete/finish the task
   - Follow prompts if there are uncommitted or unpushed changes
   - Worktrees are removed (branches remain on remote)

## Understanding the Interface

tasktree-manager uses a **3-panel layout**:

```
┌─ tasktree-manager ──────────────────────────────────────────────────────┐
│  Tasks                    │  Worktrees                                   │
│  ● FEAT-123 (3)          │    backend        FEAT-123        ● ✗ 2     │
│    BUG-456 (1)           │    frontend       FEAT-123        ✓         │
│                          │    api-docs       FEAT-123        ↑1 ↓0     │
│                          │                                              │
├──────────────────────────────────────────────────────────────────────────┤
│  Status: backend                                                         │
│  Branch: FEAT-123                                                       │
│  Sync:   ↑1 ↓0                                                         │
│                                                                         │
│   M  src/auth.py                                                       │
│   ?? README.md                                                         │
└──────────────────────────────────────────────────────────────────────────┘
  n New  d Delete  g Lazygit  h Diff  p Push  r Refresh  ? Help  q Quit
```

### Left Panel: Task List

Shows all your tasks:

- **Name**: Task identifier (e.g., `FEAT-123`)
- **Count**: Number of worktrees in parentheses (e.g., `(3)`)
- **Dirty indicator** `●`: Red dot — task has uncommitted changes
- **CLAUDE.md indicator** `◆`: Blue diamond — task has a CLAUDE.md file
- **Claude session status**: `⟳` running (magenta), `!` waiting (yellow), `✓` ended (green)
- **Sort mode**: Press `s` to cycle through sort modes (name ↑/↓, date ↑/↓, dirty/clean first)

**Navigation:**
- `j/k` or arrow keys: Move up/down
- `s`: Cycle sort mode (panel title shows current sort)
- Highlighting a task: Shows its worktrees in right panel

### Right Panel: Worktree List

Shows worktrees for the selected task:

- **Repository name**: Name of the repo (e.g., `backend`)
- **Branch**: Current branch (usually matches task name)
- **Status indicators:**
  - `●` - Has uncommitted changes (staged, modified, or untracked files)
  - `✗ N` - Has N staged or modified files
  - `↑N` - N commits ahead of remote
  - `↓N` - N commits behind remote
  - `✓` - Clean (no changes, in sync)
- **Grouping**: Press `S` (Shift+S) to group worktrees by dirty/clean status

**Navigation:**
- `j/k` or arrow keys: Move up/down
- `S`: Toggle grouping by dirty/clean (panel subtitle shows "grouped" when active)
- Highlighting a worktree: Shows detailed status in bottom panel

### Bottom Panel: Status Display

Shows detailed git status for the selected worktree:

- **Branch**: Current branch name
- **Sync status**: Ahead/behind counts
- **File changes**: Modified, staged, and untracked files with git status codes

**Git status codes:**
- `M` - Modified
- `A` - Added (staged)
- `D` - Deleted
- `R` - Renamed
- `??` - Untracked

### Visual Indicators

**Task & Worktree Status:**

| Indicator | Meaning                                    |
|-----------|--------------------------------------------|
| `●`       | Task/worktree has uncommitted changes      |
| `✗ N`     | N files staged or modified                 |
| `↑N`      | N commits ahead of remote (unpushed)       |
| `↓N`      | N commits behind remote (need to pull)     |
| `✓`       | Clean worktree, in sync                    |

**Claude Code Integration:**

| Indicator | Color   | Meaning                                  |
|-----------|---------|------------------------------------------|
| `◆`       | Blue    | Task/worktree has a CLAUDE.md file       |
| `⟳`       | Magenta | Claude Code session is running           |
| `!`       | Yellow  | Claude Code session is waiting for input |
| `✓`       | Green   | Claude Code session has ended            |

## Complete Keyboard Reference

All keybindings can be customized in [`config.toml`](configuration.md).

The footer is context-sensitive, lazygit-style: it shows the actions for the
focused panel (task actions in the Task List, worktree/git actions in the
Worktree List) plus the always-available `r` Refresh, `?` Help, and `q` Quit.
Every key works regardless of which panel has focus — the footer only changes
what is displayed. Press `?` for the full reference at any time.

### Navigation

| Key        | Action                      | Description                                      |
|------------|-----------------------------|--------------------------------------------------|
| `j`        | Cursor down                 | Move down in current list                        |
| `k`        | Cursor up                   | Move up in current list                          |
| `↓` / `↑`  | Cursor down/up              | Alternative to j/k                               |
| `Tab`      | Focus next panel            | Switch between Task List → Worktree List         |
| `Shift+Tab`| Focus previous panel        | Switch between Worktree List → Task List         |

**Tips:**
- You can also click with mouse (if terminal supports it)
- Focused panel has a highlighted border (accent color)

### Sorting & Grouping

| Key | Action                | Description                                                |
|-----|-----------------------|------------------------------------------------------------|
| `s` | Cycle sort mode       | Cycle through: name ↑/↓, date ↑/↓, dirty first, clean first |
| `S` | Toggle grouping       | Group worktrees by dirty/clean status (Shift+S)            |
| `t` | Cycle theme           | Cycle tasktree → tokyo-night → catppuccin (4x) → gruvbox → dracula → nord |

**Sort modes:**
- `by name ↑` - Alphabetical A-Z (default)
- `by name ↓` - Alphabetical Z-A
- `by date ↓` - Newest first
- `by date ↑` - Oldest first
- `dirty first` - Tasks with changes at top
- `clean first` - Clean tasks at top

**Grouping:**
- When enabled, worktrees are grouped under "Dirty" and "Clean" headers
- Headers are non-selectable; navigation skips them automatically
- Panel title shows "(grouped)" when active

### Task Management

| Key | Action           | Description                                               |
|-----|------------------|-----------------------------------------------------------|
| `n` | New task         | Create a new task with selected repositories              |
| `y` | Clone task       | Create a new task pre-populated with the current task's repos |
| `a` | Add repository   | Add additional repositories to the current task           |
| `d` | Delete/finish    | Delete current task and remove worktrees                  |
| `R` | Rename task      | Set a display alias shown in the task list (folder/branch unchanged; empty input reverts) |

**Task creation workflow:**
1. Press `n`
2. Enter task name (e.g., `JIRA-1234`)
3. Enter base branch (default: `main`)
4. Filter repos by typing in search box (optional)
5. Select repos with `Space` (can select multiple)
6. Tab to "Create" button, press `Enter`

Task names may contain letters, numbers, `.`, `_` and `-`. The name becomes a
single directory under your tasks dir (and a git branch), so `/`, `.`, `..` and a
leading `-` are rejected; base branch names must be plain branch names too (no
leading `-`/`+`, no `:` refspecs, none of the characters git forbids in refs).

**Clone task workflow:**
Useful when you're spinning up several similar tasks that share the same set of repos.

1. Highlight the source task in the left panel
2. Press `y`
3. The modal opens with the source task's repos already selected — just enter a new task name
4. Adjust the repo selection or base branch if needed, then press `Enter`

**Task deletion workflow:**
1. Highlight task in left panel
2. Press `d`
3. If there are uncommitted/unpushed changes:
   - **Push All**: Push all branches, then delete
   - **Open Lazygit**: Resolve issues manually, then try delete again
   - **Force Delete**: Delete anyway (may lose work!)
   - **Cancel**: Abort deletion

### Git Operations

| Key     | Action             | Description                                          |
|---------|--------------------|------------------------------------------------------|
| `g`     | Open lazygit       | Open lazygit in the selected worktree                |
| `h`     | Show diff          | Open hunk: all repos from the task panel, the selected repo from the worktree panel |
| `e`     | Open editor        | Open editor in a new terminal tab at the task/worktree folder (runs `$EDITOR .`; the TUI keeps running) |
| `p`     | Push all           | Push all worktrees in the current task (parallel)    |
| `P`     | Pull all           | Pull all worktrees in the current task (parallel)    |
| `r`     | Refresh status     | Refresh git status for all tasks and worktrees       |

**Parallel operations:**
- `p` and `P` run git operations in parallel for speed
- Progress shown with loading indicators
- Results summarized when complete

### Folder Operations

| Key     | Action             | Description                                          |
|---------|--------------------|------------------------------------------------------|
| `o`     | Open folder        | Open task/worktree folder in new terminal tab        |

**Context-aware behavior:**
- When focused on task list: Opens the task folder (`~/tasks/TASK-NAME`)
- When focused on worktree list: Opens the selected worktree folder

### Claude Code Integration

| Key     | Action                  | Description                                                |
|---------|-------------------------|------------------------------------------------------------|
| `c`     | Open Claude CLI         | Resume the task's Claude Code session if one exists, otherwise start a new one |
| `C`     | Open Claude desktop     | Open the Claude desktop app on the Code page at the task folder |
| `b`     | Dispatch agent          | Run a background Claude agent (`claude --bg`) in the selected worktree |

**How it works:**
- `c` opens Claude Code CLI in a new Ghostty terminal tab at the task directory.
  - If `~/.claude/projects/<task-folder>/` already has session transcripts, runs `claude -r` to pick from them; otherwise runs `claude` to start fresh.
- `C` opens the Claude desktop app via the `claude://code/new?folder=<task-folder>` URL scheme.
- The CLI variant (`c`) generates a task-level `CLAUDE.md` with task/worktree context, copies each repo's own `CLAUDE.md` into worktrees whose branch predates it (never generating stub content), and installs hooks that report session status back to tasktree-manager.
- Session status (`⟳` running, `!` waiting, `✓` ended) appears next to the task name
- Both variants point the session's Claude Code auto-memory at a shared pool (`claude_memory_dir`, default `~/.claude/tasktree-memory`). Task folders are not git repos, so without this each task would get its own memory directory that is orphaned when the task is deleted; with the shared pool, what Claude learns in one task carries over to future tasks.
- Each worktree additionally gets its own `.claude/settings.local.json` pointing auto-memory at the **main repo's** memory directory (`claude_repo_memory`, enabled by default). Sessions started manually inside a worktree (`cd` + `claude`) would otherwise key their memory to the worktree path and lose it when the worktree is deleted; with this, what Claude learns about a repo persists across worktrees and is shared with sessions in the main checkout. The file is git-excluded so worktrees stay clean, and these sessions also report status back to the task indicator.

**Agent dashboard:**

Claude Code's native agent view is scoped to a single repository — it has no concept of a
task spanning several repos. tasktree-manager fills that gap:

- The worktree list polls `claude agents --json` (every `agent_poll_interval` seconds,
  default 10) and shows a per-worktree session badge: `⟳` working, `!` needs input,
  `▣` ready/idle. Any Claude session whose working directory is inside a worktree counts,
  whether started from the TUI, the dashboard, or a plain terminal.
- `b` prompts for an instruction and dispatches a background agent
  (`claude --bg -n <task>/<repo>`) into the selected worktree. Dispatch results land in
  the messages panel (`m`), and the session appears in `claude agents` under the
  `<task>/<repo>` name. Dispatch to several worktrees in parallel is fine.
- If the `claude` CLI is missing or too old for `agents --json`, polling disables itself
  after three failed attempts (one note in the messages panel) — the rest of the app is
  unaffected.

**Forge badges (MR/CI):**

With the GitLab (`glab`) or GitHub (`gh`) CLI installed and authenticated, the worktree
list also shows each branch's MR state (`○` open, `●` merged, `×` closed) and CI state
(`◐` running, `✔` passed, `✘` failed; GitHub only — GitLab's MR list API carries no
pipeline data). The provider is auto-detected from each repo's origin URL; self-hosted
GitLab works when the hostname contains "gitlab" or is listed under `[forge]
gitlab_hosts`. The same lookup makes safety checks recognize squash/rebase-merged
branches: a branch whose MR is merged no longer blocks task deletion even though
`git merge-base` cannot see the merge. Set `[forge] enabled = false` to turn all of
this off.

### General

| Key     | Action                  | Description                                  |
|---------|-------------------------|----------------------------------------------|
| `Ctrl+P`| Open Command Palette    | Search and run any action (hotkeys shown), switch themes |
| `o`     | Open folder             | Open current folder in new terminal tab      |
| `m`     | Toggle messages         | Show/hide the activity messages panel        |
| `?`     | Show help               | Display help modal with keybindings          |
| `q`     | Quit                    | Exit tasktree-manager                        |

## Common Workflows

### Workflow 1: Feature Development Across Multiple Repos

**Scenario:** Implementing a feature that requires changes in backend, frontend, and API documentation.

```bash
# Start tasktree-manager
tasktree-manager

# Create task
Press n
Task name: FEAT-123-new-auth
Base branch: main
Select: backend, frontend, api-docs
Create

# Work in backend
Tab (to worktree list)
j (to highlight backend)
o (open new terminal tab)

# In the tab: make changes
cd src
vim auth.py
# ... make changes ...
exit

# Commit with lazygit
g (open lazygit)
# Stage files, write commit message
q (quit lazygit)

# Repeat for frontend and api-docs
# ... make changes in each worktree ...

# Push all changes
Tab (back to task list)
p (push all worktrees)

# Create pull requests (outside tasktree-manager)
# Use GitHub CLI, web interface, etc.

# After PRs merged, delete task
d (delete task)
Confirm deletion
```

**Result:** All changes pushed, branches on remote, local worktrees cleaned up.

### Workflow 2: Quick Bug Fix in Single Repo

**Scenario:** Urgent bug fix needed in one repository.

```bash
tasktree-manager

# Create task
Press n
Task name: BUG-456-login-error
Base branch: main
Select: backend (only)
Create

# Open lazygit immediately
Tab
Enter or g

# Fix the bug in lazygit or shell
# ... make fix ...
# Commit and push in lazygit

# Done - delete task
Esc (back to tasktree-manager)
d (delete)
Confirm
```

**Time:** ~2 minutes from task creation to cleanup.

### Workflow 3: Code Review Setup

**Scenario:** Checking out someone else's feature branch for review.

```bash
# Option 1: Create task from existing branch
tasktree-manager
Press n
Task name: review-feat-789
Base branch: feat-789  # Their branch name
Select: backend, frontend
Create

# Option 2: Manual checkout in worktree
tasktree-manager
Press n
Task name: review-feat-789
Base branch: main
Select: backend
Create

Tab
o (open new terminal tab)
git fetch origin feat-789:feat-789
git checkout feat-789
exit

# Review code
g (lazygit)
# Browse commits, view diffs
```

**When done:**
```bash
d (delete task)
```

### Workflow 4: Long-Running Feature with Periodic Syncs

**Scenario:** Working on a feature over several days/weeks, need to stay synced with main.

```bash
# Day 1: Create task
tasktree-manager
Press n
Task name: FEAT-999-big-feature
Base branch: main
Select: backend, frontend, infrastructure
Create

# Work, commit, push
# ... work ...
p (push all)
q (quit tasktree-manager)

# Day 2: Pull updates from main
tasktree-manager
j (select FEAT-999)
Tab
o (new tab in first worktree)

# Merge main into feature branch
git fetch origin main:main
git merge main
# Resolve conflicts if any
exit

# Repeat for other worktrees
# Or use lazygit (g) for GUI merge

# Continue working
# ... work ...
p (push all)

# Day 5: Feature complete
# Push final changes
p
# Create PR (outside tasktree-manager)
# After PR merged:
d (delete task)
```

### Workflow 5: Emergency Hotfix

**Scenario:** Production issue, need immediate fix.

```bash
tasktree-manager

# Create hotfix task
Press n
Task name: HOTFIX-critical-bug
Base branch: production  # or main
Select: backend
Create

# Make fix
Tab
g (lazygit)
# Make minimal change
# Commit with clear message
# Push

# Deploy (outside tasktree-manager)
# CI/CD picks up the branch

# Clean up
Esc
d (delete task)
```

**Speed:** Entire workflow in under 5 minutes.

## Working with Worktrees

### Creating Worktrees

**During task creation:**
- Select repositories when creating task with `n`
- All selected repos get worktrees automatically

**Adding to existing task:**
1. Highlight task in left panel
2. Press `a` (add repo)
3. Select additional repositories
4. Enter base branch
5. Create

### Managing Worktrees

**Viewing status:**
- Highlight worktree in right panel
- Detailed status appears in bottom panel

**Working in worktree:**
- Press `e` to open editor directly in worktree
- Press `g` for lazygit (recommended for git operations)
- Press `o` for a shell in a new terminal tab (building, testing, other commands)

**Git operations:**
- **Staging/committing**: Use lazygit (`g`)
- **Pushing**: Use `p` for all worktrees, or push individually in lazygit
- **Pulling**: Use `P` for all worktrees, or pull individually in lazygit
- **Merging/rebasing**: Use lazygit or shell

### Deleting Worktrees

**Delete entire task:**
1. Highlight task in left panel
2. Press `d`
3. Handle safety checks:
   - **Uncommitted changes**: Commit or stash first
   - **Unpushed commits**: Push or force delete
   - **Unmerged branches**: Merge PR or force delete
   - **Wrong branch checked out**: a worktree that is detached or on another branch
     is reported as an error — switch back to the task branch (the check and the
     archive follow the task branch, because that is what deletion removes)

**Delete a single worktree:**
1. Highlight the worktree in the right panel
2. Press `D` — the same safety check, dialog (Push / Open Lazygit / Force Delete)
   and diff archive apply, scoped to that one repo

**Safety features:**
- tasktree-manager checks for uncommitted changes
- Checks for unpushed commits
- Offers to push before deletion
- With `glab`/`gh` installed, branches whose MR/PR was squash- or rebase-merged count as
  merged (plain `git merge-base` cannot see those merges)
- Force delete available (with confirmation)

**What happens on delete:**
- ✅ The task's remaining diff (committed-but-unmerged + uncommitted work) is archived to
  `archive_dir` (default `<tasks_dir>/.archive/<task>-<timestamp>.patch`) before anything
  is removed — the messages panel (`m`) shows the archive path
- ✅ Worktrees removed from `TASKS_DIR`
- ✅ Branches remain on remote (if pushed)
- ✅ Original repos in `REPOS_DIR` untouched
- ❌ The local task branch is deleted from each repo (`git branch -D`) — unpushed
  commits survive only in the archive patch, which is why the safety check blocks
  unpushed work and why a worktree must be on its task branch to count as safe

**From scripts:** `tasktree-manager finish <task>` runs the same guided flow headlessly
(safety sweep → optional `--push` → archive → delete), and `tasktree-manager status
[--json|--oneline] [--forge]` reports per-worktree state — see the README's Headless CLI
section.

### Manual Cleanup

If tasktree-manager crashes or worktrees are corrupted:

```bash
# List git worktrees
cd ~/repos/backend
git worktree list

# Remove specific worktree
git worktree remove ~/tasks/TASK-NAME/backend

# Remove directory manually if needed
rm -rf ~/tasks/TASK-NAME
```

## Integration with Tools

### Lazygit

[lazygit](https://github.com/jesseduffield/lazygit) is the recommended tool for git operations in tasktree-manager.

**Why lazygit:**
- Visual interface for staging, committing, pushing
- Conflict resolution
- Branch management
- Stash management
- Integrated diff viewer

**Using lazygit:**
1. Highlight worktree
2. Press `g`
3. tasktree-manager suspends, lazygit opens
4. Do your git work
5. Press `q` in lazygit to return to tasktree-manager
6. Status auto-refreshes and selection is preserved

**Install lazygit:**
```bash
# macOS
brew install lazygit

# Ubuntu
apt install lazygit

# Others
# See: https://github.com/jesseduffield/lazygit
```

### Hunk

[hunk](https://github.com/modem-dev/hunk) is a review-first terminal diff viewer, well suited to reviewing agent-authored changesets across a multi-repo task.

**Why hunk:**
- Fast, keyboard-driven diff review with a desktop-inspired layout
- Reviews an entire task's changes across all its repos in one view
- Complements lazygit (which stages/commits per repo)

**Using hunk:**
1. From the **worktree panel**, press `h` to review the selected repo's uncommitted changes
2. From the **task panel**, press `h` to review a combined diff across **all** the task's repos at once (each file is grouped under its repo name)
3. tasktree-manager suspends, hunk opens
4. Press `q` in hunk to return; status auto-refreshes and selection is preserved

The combined task view includes both tracked (staged and unstaged) changes and untracked files.

**Install hunk:**
```bash
# macOS
brew install hunk

# npm
npm i -g hunkdiff

# See: https://github.com/modem-dev/hunk
```

### Editors

**Direct editor integration:**
1. Highlight task or worktree
2. Press `e` to open your configured editor in a new Ghostty tab (`$EDITOR .`)
3. tasktree-manager keeps running alongside the editor (macOS + Ghostty only, see
   Limitations)

**Configure your editor** in `~/.config/tasktree-manager/config.toml`:
```toml
[tools]
editor = "nvim"  # or "vim", "code", "emacs", etc.
```

Or set the `$EDITOR` environment variable.

**Alternative: Open a terminal tab first:**
1. Press `o` (new terminal tab in the worktree)
2. In the tab:
   ```bash
   vim .               # Vim
   nvim .              # Neovim
   code .              # VS Code
   emacs .             # Emacs
   ```

**VS Code workspace:**
```bash
# In worktree shell
code ~/tasks/FEAT-123  # Open entire task as workspace
```

**IDE integration:**
- Most IDEs can open directories in `~/tasks/TASK-NAME/repo-name`
- Use "Open Folder" or equivalent
- Git integration works normally

### CI/CD

tasktree-manager creates normal git branches, so CI/CD works seamlessly:

1. Push branch: `p` in tasktree-manager
2. CI detects new branch
3. Runs tests/builds
4. Create PR (GitHub, GitLab, etc.)
5. CI runs on PR
6. Merge PR when green
7. Delete task in tasktree-manager: `d`

**Branch naming:**
- Task name becomes branch name
- Use CI-friendly names: `JIRA-123`, `feat-auth`, `bugfix-login`
- Avoid spaces and special characters

### GitHub CLI

Integrate with GitHub CLI for PR creation:

```bash
# In a worktree tab (press o in tasktree-manager)
gh pr create --title "Add authentication" --body "Implements FEAT-123"

# Or after pushing all worktrees
# Outside tasktree-manager
cd ~/repos/backend
gh pr create --head FEAT-123
```

## Tips and Best Practices

### Naming Conventions

**Task names:**
- Use issue tracker IDs: `JIRA-1234`, `PROJ-567`
- Or descriptive names: `feat-auth`, `bugfix-login`, `refactor-api`
- Avoid spaces: Use `-` or `_`
- Keep short but meaningful

**Branch naming:**
- Task name becomes branch name
- Example: Task `FEAT-123` creates branch `FEAT-123`
- Ensure names are valid git branch names

### Directory Organization

**Recommended structure:**
```
~/repos/              # All your git repositories
  ├── work/           # Work projects
  │   ├── backend/
  │   └── frontend/
  └── personal/       # Personal projects
      └── blog/

~/tasks/              # All task worktrees
  ├── FEAT-123/
  └── BUG-456/
```

**Tips:**
- Set `REPOS_DIR=~/repos` (tasktree-manager scans recursively)
- Keep `TASKS_DIR` on fast storage (SSD)
- Don't nest `TASKS_DIR` inside `REPOS_DIR`

### Performance Optimization

**For many repositories:**
- tasktree-manager scans `REPOS_DIR` recursively
- If you have 100+ repos, initial load may be slow
- Consider organizing repos in subdirectories
- Only include active project directories in `REPOS_DIR`

**For large repositories:**
- Increase `git.timeout` in config.toml
- Use `P` (pull all) cautiously with large repos
- Consider using `g` (lazygit) for selective operations

**For slow networks:**
- Increase `git.timeout = 60` or higher
- Use lazygit for manual push/pull control
- Avoid `p`/`P` on cellular connections

### Team Workflows

**Branch naming alignment:**
- Agree on task naming with team (e.g., JIRA IDs)
- Ensures consistency in PR titles and branches

**CI/CD integration:**
- Configure CI to run on all branches (or pattern match)
- Example GitHub Actions:
  ```yaml
  on:
    push:
      branches: ['**']  # All branches
  ```

**Code review:**
- Use Workflow 3 (Code Review Setup) to check out PRs
- Or use GitHub CLI: `gh pr checkout 123`

**Shared repos directory:**
- Each developer has own `REPOS_DIR` (don't share)
- Each developer has own `TASKS_DIR` (don't share)
- Share only remote branches (push/pull as normal)

### Common Mistakes

**❌ Don't:**
- Delete `REPOS_DIR` (these are your original repos!)
- Commit directly in `REPOS_DIR` (work in task worktrees)
- Share `TASKS_DIR` between machines (worktrees are local)
- Force delete tasks with unpushed work

**✅ Do:**
- Work in worktrees (`~/tasks/TASK-NAME/repo`)
- Push regularly (`p` key)
- Delete tasks when done (`d` key)
- Keep original repos in `REPOS_DIR` clean

## Limitations

### Current Limitations

1. **Single user**: No concurrent access to same `TASKS_DIR`
2. **Unix-like systems only**: macOS, Linux, WSL2 (no native Windows)
3. **Terminal UI**: No GUI (intentional)
4. **No task persistence across machines**: Worktrees are local
5. **No automated conflict resolution**: Use lazygit or shell
6. **Limited metadata**: No task descriptions, assignees, or custom fields (yet)

### Known Issues

For current bugs and planned features, see [ROADMAP.md](../ROADMAP.md).

**Workarounds:**

- **Want GUI?** Use lazygit (`g` key) for visual git operations
- **Multi-machine sync?** Use branches on remote (push/pull normally)
- **Task metadata?** Use issue tracker (JIRA, Linear) alongside tasktree-manager

## Next Steps

- [Configuration Reference](configuration.md) - Customize keybindings and settings
- [Troubleshooting Guide](troubleshooting.md) - Solve common issues
- [ROADMAP.md](../ROADMAP.md) - See planned features
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribute to tasktree-manager
