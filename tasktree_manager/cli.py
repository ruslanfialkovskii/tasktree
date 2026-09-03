"""Headless CLI for tasktree-manager.

Running ``tasktree-manager`` with no arguments starts the TUI; any argument
routes here instead. Built for scripts and automation (e.g. Claude skills
that create a task and then work in its worktrees): plain text on stdout,
errors on stderr, exit code 0 on success and 1 on failure.
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .services import forge
from .services.config import Config, ConfigError
from .services.git_ops import GitOps
from .services.models import Task
from .services.task_manager import TaskManager


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the headless CLI."""
    parser = argparse.ArgumentParser(
        prog="tasktree-manager",
        description="Manage git worktree-based tasks (run with no arguments for the TUI).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a task with worktrees for the given repos")
    create.add_argument("name", help="Task name (also used as the branch name)")
    create.add_argument(
        "--repos",
        required=True,
        help="Comma-separated repo names from REPOS_DIR (e.g. repo-a,repo-b)",
    )
    create.add_argument(
        "--base",
        default=None,
        help="Base branch for the worktrees (default: git.default_base_branch from config)",
    )
    create.set_defaults(func=cmd_create)

    list_parser = sub.add_parser("list", help="List tasks with their repos and dirty state")
    list_parser.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    list_parser.set_defaults(func=cmd_list)

    repos = sub.add_parser("repos", help="List available repos in REPOS_DIR (one per line)")
    repos.set_defaults(func=cmd_repos)

    delete = sub.add_parser("delete", help="Delete a task and its worktrees")
    delete.add_argument("name", help="Task name")
    delete.add_argument(
        "--force",
        action="store_true",
        help="Delete even with uncommitted, unpushed or unmerged work",
    )
    delete.set_defaults(func=cmd_delete)

    add_repo = sub.add_parser("add-repo", help="Add a repo worktree to an existing task")
    add_repo.add_argument("name", help="Task name")
    add_repo.add_argument("repo", help="Repo name from REPOS_DIR")
    add_repo.add_argument("--base", default=None, help="Base branch for the worktree")
    add_repo.set_defaults(func=cmd_add_repo)

    finish = sub.add_parser(
        "finish", help="Finish a task: safety sweep, archive its diff, then delete"
    )
    finish.add_argument("name", help="Task name")
    finish.add_argument("--push", action="store_true", help="Push unpushed branches first")
    finish.add_argument(
        "--no-archive",
        action="store_true",
        dest="no_archive",
        help="Skip writing the diff archive",
    )
    finish.add_argument(
        "--force",
        action="store_true",
        help="Finish even with unfinished work (the archive is still written)",
    )
    finish.set_defaults(func=cmd_finish)

    status = sub.add_parser("status", help="Show per-worktree status for a task")
    status.add_argument(
        "name", nargs="?", default=None, help="Task name (default: inferred from $PWD)"
    )
    output_group = status.add_mutually_exclusive_group()
    output_group.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    output_group.add_argument(
        "--oneline",
        action="store_true",
        help="Single-line summary for statuslines and shell prompts",
    )
    status.add_argument(
        "--forge",
        action="store_true",
        dest="with_forge",
        help="Include MR/CI state from glab/gh (live network call)",
    )
    status.set_defaults(func=cmd_status)

    return parser


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _unknown_repos_error(config: Config, repos: list[str]) -> str | None:
    """Return an error message if any repo is not in REPOS_DIR, else None."""
    available = config.get_available_repos()
    unknown = [r for r in repos if r not in available]
    if unknown:
        return (
            f"unknown repo(s): {', '.join(unknown)}; available: {', '.join(available) or '(none)'}"
        )
    return None


def cmd_create(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Create a task with worktrees for the given repos."""
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    if not repos:
        return _error("--repos needs at least one repo name")
    error = _unknown_repos_error(config, repos)
    if error:
        return _error(error)
    if manager.get_task(args.name):
        return _error(f"task already exists: {args.name}")

    base = args.base or config.default_base_branch
    task = manager.create_task(args.name, repos, base)
    # CLI-created tasks may never pass through the TUI's lazy Claude prep,
    # so materialize CLAUDE.md files and worktree settings right away
    manager.ensure_claude_md_files(task)
    manager.ensure_worktree_settings(task)

    repo_list = ", ".join(wt.name for wt in task.worktrees)
    print(f"Created task {task.name} at {task.path} ({len(task.worktrees)} repo(s): {repo_list})")
    return 0


def cmd_list(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """List tasks with their repos and dirty state."""
    tasks = manager.list_tasks()
    dirty: dict[str, bool] = {}
    for task in tasks:
        statuses = GitOps.get_statuses_parallel(task.worktrees)
        dirty[task.name] = any(s.is_dirty for s in statuses.values())

    if args.as_json:
        payload = [
            {
                "name": task.name,
                "display_name": task.display_name,
                "path": str(task.path),
                "repos": [wt.name for wt in task.worktrees],
                "dirty": dirty[task.name],
            }
            for task in tasks
        ]
        print(json.dumps(payload, indent=2))
        return 0

    if not tasks:
        print("No tasks")
        return 0
    for task in tasks:
        state = "dirty" if dirty[task.name] else "clean"
        repos = ", ".join(wt.name for wt in task.worktrees) or "(no repos)"
        print(f"{task.name}\t{state}\t{repos}")
    return 0


def cmd_repos(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """List available repos (handles nested repos, unlike a plain ls)."""
    for repo in config.get_available_repos():
        print(repo)
    return 0


def cmd_delete(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Delete a task after a safety check (bypass with --force)."""
    task = manager.get_task(args.name)
    if not task:
        return _error(f"no such task: {args.name}")

    report = manager.check_task_safety(task)
    if not report.is_safe() and not args.force:
        print(f"error: task {args.name} has unfinished work:", file=sys.stderr)
        for issue in report.errors + report.dirty + report.unpushed + report.unmerged:
            print(f"  {issue.repo_name}: {issue.details}", file=sys.stderr)
        print("use --force to delete anyway", file=sys.stderr)
        return 1

    # Same safety net as the TUI: the remaining diff is archived before the
    # worktrees and branches are removed, --force included
    archive_path = manager.archive_task(task)
    if archive_path is not None:
        print(f"Archived diff to {archive_path}")
    manager.finish_task(task)
    print(f"Deleted task {args.name}")
    return 0


def cmd_finish(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Guided task finish: sweep -> optional push -> archive -> delete."""
    task = manager.get_task(args.name)
    if not task:
        return _error(f"no such task: {args.name}")

    # Push unconditionally when asked (TUI parity: `git push -u origin HEAD`).
    # Gating on has_unpushed() would skip never-pushed --no-track branches,
    # whose missing upstream makes ahead read as 0.
    if args.push:
        success, failed = manager.push_all_branches(task)
        for repo in success:
            print(f"Pushed {repo}")
        for repo in failed:
            print(f"error: push failed: {repo}", file=sys.stderr)

    report = manager.check_task_safety(task)

    # Squash/rebase merges detected via the forge are worth surfacing even
    # when everything is fine — they explain why the branch counts as merged
    for issue in report.merged_via_forge:
        print(f"{issue.repo_name}: {issue.details}")

    if not report.is_safe() and not args.force:
        print(f"error: task {args.name} has unfinished work:", file=sys.stderr)
        for issue in report.errors + report.dirty + report.unpushed + report.unmerged:
            print(f"  {issue.repo_name}: {issue.details}", file=sys.stderr)
        if not args.push and (report.has_unpushed() or report.has_unmerged()):
            print("use --push to push branches first", file=sys.stderr)
        print("use --force to finish anyway", file=sys.stderr)
        return 1

    if not args.no_archive:
        notes = [f"{issue.repo_name}: {issue.details}" for issue in report.merged_via_forge]
        archive_path = manager.archive_task(task, notes=notes or None)
        if archive_path is not None:
            print(f"Archived diff to {archive_path}")
        else:
            print("Nothing to archive")

    manager.finish_task(task)
    print(f"Finished task {args.name}")
    return 0


def cmd_add_repo(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Add a repo worktree to an existing task."""
    task = manager.get_task(args.name)
    if not task:
        return _error(f"no such task: {args.name}")
    error = _unknown_repos_error(config, [args.repo])
    if error:
        return _error(error)
    if any(wt.name == args.repo for wt in task.worktrees):
        print(f"Repo {args.repo} already in task {args.name}")
        return 0

    base = args.base or config.default_base_branch
    manager.add_repo_to_task(task, args.repo, base)
    print(f"Added {args.repo} to task {args.name}")
    return 0


def _find_task_by_cwd(manager: TaskManager) -> Task | None:
    """Find the task whose directory contains the current working directory."""
    cwd = Path.cwd().resolve()
    for task in manager.list_tasks():
        task_path = task.path.resolve()
        if cwd == task_path or cwd.is_relative_to(task_path):
            return task
    return None


def _read_claude_status(task: Task) -> dict | None:
    """Read the task's hook-written .claude_status file, or None."""
    status_file = task.path / ".claude_status"
    try:
        data = json.loads(status_file.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {"status": data.get("status", "unknown"), "ts": data.get("ts")}


def _oneline_status(task: Task, rows: list[tuple], claude: dict | None) -> str:
    """Compact one-line summary for statuslines and shell prompts.

    Per repo: ✓ = clean, in sync and merged; ●N (dirty), ↑N/↓N
    (ahead/behind); ○ = clean and in sync but not merged (work in flight);
    ! on a status error. Matches the TUI glyph vocabulary.
    """
    parts = [task.name]
    for worktree, status, _base, merged_via, _forge_status in rows:
        repo = worktree.name.split("/")[-1]
        if status.error:
            flags = "!"
        else:
            flags = ""
            if status.is_dirty:
                flags += f"●{status.changed_files}"
            if status.ahead:
                flags += f"↑{status.ahead}"
            if status.behind:
                flags += f"↓{status.behind}"
            if not flags:
                # Every glyph earns its cell: a truly done branch gets ✓,
                # a clean-but-unmerged one gets ○ so unfinished work never
                # renders as a bare (invisible) repo name
                flags = "✓" if merged_via is not None else "○"
        parts.append(f"{repo}{flags}")
    if claude is not None:
        parts.append(f"claude:{claude['status']}")
    return " ".join(parts)


def cmd_status(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Show per-worktree status for a task (fast/offline by default)."""
    if args.name:
        task = manager.get_task(args.name)
        if not task:
            return _error(f"no such task: {args.name}")
    else:
        task = _find_task_by_cwd(manager)
        if not task:
            return _error("not inside a task directory; pass a task name")

    statuses = GitOps.get_statuses_parallel(task.worktrees)
    claude = _read_claude_status(task)

    rows: list[tuple] = []
    for worktree in task.worktrees:
        status = statuses.get(worktree.name)
        if status is None:
            continue
        base = GitOps.get_default_branch(worktree)
        # fetch=False keeps the default path offline-fast; origin/<base> may
        # be slightly stale, which is fine for a prompt/statusline
        merged_via = "ancestor" if GitOps.check_merged(worktree, base, fetch=False) else None
        forge_status = None
        if args.with_forge:
            branch = status.branch or task.name
            forge_status = forge.get_forge_status(worktree.path, branch)
            if (
                merged_via is None
                and forge_status is not None
                and forge_status.mr_state == "merged"
            ):
                merged_via = "forge"
        rows.append((worktree, status, base, merged_via, forge_status))

    if args.oneline:
        print(_oneline_status(task, rows, claude))
        return 0

    if args.as_json:
        payload = {
            "task": task.name,
            "path": str(task.path),
            "claude": claude,
            "worktrees": [
                {
                    "repo": worktree.name,
                    "branch": status.branch,
                    "ahead": status.ahead,
                    "behind": status.behind,
                    "staged": len(status.staged),
                    "modified": len(status.modified),
                    "untracked": len(status.untracked),
                    "dirty": status.is_dirty,
                    "merged": merged_via is not None,
                    "merged_via": merged_via,
                    "forge": (
                        {
                            "provider": forge_status.provider,
                            "mr_state": forge_status.mr_state,
                            "mr_url": forge_status.mr_url,
                            "mr_ref": forge_status.mr_ref,
                            "ci_state": forge_status.ci_state,
                        }
                        if forge_status is not None
                        else None
                    ),
                    "error": status.error or None,
                }
                for worktree, status, _base, merged_via, forge_status in rows
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    claude_state = claude["status"] if claude else "-"
    print(f"Task: {task.name}\tclaude: {claude_state}")
    for worktree, status, base, merged_via, forge_status in rows:
        if status.error:
            print(f"{worktree.name}\t{status.branch or '?'}\terror: {status.error}")
            continue
        state = f"dirty ({status.changed_files} files)" if status.is_dirty else "clean"
        sync = f"ahead {status.ahead}, behind {status.behind}"
        merged = f"merged ({merged_via})" if merged_via else f"not merged to {base}"
        line = f"{worktree.name}\t{status.branch}\t{state}\t{sync}\t{merged}"
        if forge_status is not None and forge_status.mr_state != "none":
            mr = f"MR {forge_status.mr_ref or '?'} {forge_status.mr_state}"
            if forge_status.ci_state:
                mr += f" (CI {forge_status.ci_state})"
            line += f"\t{mr}"
        print(line)
    return 0


def run_cli(argv: list[str], config: Config | None = None) -> int:
    """Parse argv and run the matching subcommand, returning an exit code."""
    args = build_parser().parse_args(argv)
    if config is None:
        try:
            config = Config.load()
        except ConfigError as e:
            return _error(str(e))
    config.ensure_dirs()
    GitOps.network_timeout = config.git_timeout
    forge.Forge.configure(config)
    manager = TaskManager(config)
    try:
        return args.func(manager, config, args)
    except FileNotFoundError as e:
        return _error(f"repository not found: {e}")
    except PermissionError:
        return _error("permission denied: check directory permissions")
    except ValueError as e:
        return _error(str(e))
    except Exception as e:  # same taxonomy as the TUI worker: keep output clean
        return _error(f"{type(e).__name__}: {e}")
