"""Task management service for tasktree-manager."""

import fnmatch
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from . import forge
from .claude_hooks import ensure_worktree_claude_settings, exclude_from_git
from .config import Config
from .models import RepoIssue, Task, TaskSafetyReport, Worktree

# Task name validation pattern. No '/': a task is exactly one directory
# level under TASKS_DIR (list_tasks() only reads that level), and a slashed
# name would be surfaced as its parent directory with the wrong branch name.
TASK_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._\-]+$")


def validate_task_name(name: str) -> str | None:
    """Validate a task name, returning an error message or None if valid.

    Task names become a directory under TASKS_DIR and a git branch name, so
    they must be a single path segment that cannot traverse ('.', '..') or
    look like a git option (leading '-').
    """
    if not name:
        return "Task name cannot be empty"
    if name.startswith("-"):
        return "Task name cannot start with '-'"
    if not TASK_NAME_PATTERN.match(name):
        return "Task name can only contain letters, numbers, '.', '_', '-'"
    if name in (".", ".."):
        return "Task name cannot be '.' or '..'"
    return None


# Characters git itself forbids in ref names, plus ':' (which would turn the
# `git fetch origin <base>` argument into a src:dst refspec that overwrites a
# local branch) and control characters.
_BRANCH_FORBIDDEN = re.compile(r"[\s~^:?*\[\\\x00-\x1f\x7f]|\.\.|@\{")


def validate_branch_name(branch: str) -> str | None:
    """Validate a base branch name, returning an error message or None.

    Branch names are passed as positional git arguments: a leading '-' would
    be parsed as a git option (e.g. --upload-pack=<command>), and a refspec
    such as '+refs/heads/main:refs/heads/develop' would make the fetch
    force-move the local 'develop' branch before failing.
    """
    if not branch:
        return "Branch name cannot be empty"
    if branch.startswith(("-", "+")):
        return "Branch name cannot start with '-' or '+'"
    if _BRANCH_FORBIDDEN.search(branch) or branch.endswith(("/", ".lock", ".")):
        return "Branch name contains characters git does not allow"
    return None


def normalize_base_branch(branch: str) -> str:
    """Strip ref prefixes so 'origin/main' and 'refs/heads/main' mean 'main'.

    The base is fetched as ``origin/<base>`` and recorded in branch config;
    a remote-qualified spelling would be recorded verbatim and later resolve
    to nothing when the archive looks for refs/remotes/origin/origin/main.
    """
    for prefix in ("refs/remotes/origin/", "refs/heads/", "origin/"):
        if branch.startswith(prefix) and len(branch) > len(prefix):
            return branch[len(prefix) :]
    return branch


class TaskManager:
    """Manages tasks and worktrees."""

    def __init__(self, config: Config):
        self.config = config

    def _validate_task_name(self, name: str) -> None:
        """Validate task name for safety.

        Raises:
            ValueError: If task name is invalid
        """
        error = validate_task_name(name)
        if error:
            raise ValueError(error)
        # Belt and braces: the segment checks make escapes impossible, but
        # a task path must never resolve outside the tasks directory —
        # finish_task() runs rmtree on it.
        task_path = (self.config.tasks_dir / name).resolve()
        if not task_path.is_relative_to(self.config.tasks_dir.resolve()):
            raise ValueError("Task name resolves outside the tasks directory")

    def list_tasks(self) -> list[Task]:
        """List all tasks in the tasks directory."""
        if not self.config.tasks_dir.exists():
            return []

        tasks = []
        for item in sorted(self.config.tasks_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                task = Task(name=item.name, path=item)
                task.worktrees = self._get_worktrees(task)
                tasks.append(task)
        return tasks

    # Directories to skip when scanning for worktrees
    IGNORED_PATHS = {".terraform", "node_modules", "vendor", ".git"}

    def _get_worktrees(self, task: Task) -> list[Worktree]:
        """Get all worktrees for a task (with directory pruning)."""
        worktrees = []
        if not task.path.exists():
            return worktrees

        for dirpath, dirnames, filenames in os.walk(task.path):
            # A worktree has a .git file (or a .git directory for a plain
            # clone dropped into the task); test before pruning, which
            # removes ".git" from dirnames
            has_git = ".git" in dirnames or ".git" in filenames
            # Prune ignored directories in-place
            dirnames[:] = [d for d in dirnames if d not in self.IGNORED_PATHS]

            if has_git:
                worktree_path = Path(dirpath)
                rel_path = worktree_path.relative_to(task.path)
                # Skip the task root itself if it has .git
                if str(rel_path) != ".":
                    worktrees.append(Worktree(name=str(rel_path), path=worktree_path))
                # A worktree's own tree can hold thousands of directories
                # (and nested repos are not worktrees): stop descending
                dirnames[:] = []

        return sorted(worktrees, key=lambda w: w.name)

    def get_task(self, name: str) -> Task | None:
        """Get a specific task by name.

        Raises ValueError for names that are not valid task names: callers
        (the CLI in particular) go on to rmtree the returned path, so '',
        '.', '..' or an absolute path must never resolve to a Task.
        """
        self._validate_task_name(name)
        task_path = self.config.tasks_dir / name
        if not task_path.exists():
            return None

        task = Task(name=name, path=task_path)
        task.worktrees = self._get_worktrees(task)
        return task

    def create_task(self, name: str, repos: list[str], base_branch: str = "master") -> Task:
        """Create a new task with worktrees for specified repos."""
        # Validate task name
        self._validate_task_name(name)

        task_path = self.config.tasks_dir / name
        created_dir = not task_path.exists()
        task_path.mkdir(parents=True, exist_ok=True)

        task = Task(name=name, path=task_path)

        try:
            for repo_name in repos:
                self._create_worktree(task, repo_name, base_branch)
        except BaseException:
            # A half-created task (a bad base branch in repo #2, a fetch
            # timeout) must not linger as a ghost: it shows up in the list
            # with no repos and blocks a retry with "task already exists"
            if created_dir:
                self._rollback_task(task)
            raise

        task.worktrees = self._get_worktrees(task)
        return task

    def _rollback_task(self, task: Task) -> None:
        """Best-effort removal of a task this call created but could not finish."""
        try:
            for worktree in self._get_worktrees(task):
                self._remove_worktree(worktree, task.name)
        finally:
            shutil.rmtree(task.path, ignore_errors=True)

    def _create_worktree(self, task: Task, repo_name: str, base_branch: str) -> None:
        """Create a worktree for a repo within a task."""
        from .git_ops import GitOps

        error = validate_branch_name(base_branch)
        if error:
            raise ValueError(error)
        base_branch = normalize_base_branch(base_branch)

        repo_path = self.config.repos_dir / repo_name
        worktree_path = task.path / repo_name

        if not repo_path.exists():
            raise ValueError(f"Repository not found: {repo_name}")

        if worktree_path.exists():
            return  # Already exists

        # Ensure parent directory exists for nested repos
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # A worktree directory deleted by hand leaves git's registration
        # behind, and `worktree add` then refuses with "already used by
        # worktree"; nothing else in the app would ever prune it
        self._run_cleanup_git(["git", "worktree", "prune"], cwd=repo_path, timeout=10)

        # Check if branch already exists
        branch_check = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{task.name}"],
            cwd=repo_path,
            capture_output=True,
            timeout=10,
        )
        branch_exists = branch_check.returncode == 0

        network_timeout = self.config.git_timeout
        if branch_exists:
            # Reuse the branch as it is. Resetting it to the base (-B) would
            # silently orphan every commit that only exists on that branch,
            # e.g. a task recreated after its branch was left behind.
            add_cmd = ["git", "worktree", "add", str(worktree_path), task.name]
        else:
            # Fetch the base branch and base the worktree on the remote-tracking
            # ref directly. The local base branch is not trustworthy: the main
            # checkout may sit on another branch or be behind origin, and pulling
            # it (the old approach) silently did nothing in those cases, creating
            # worktrees from stale code. Falls back to the local branch when the
            # fetch fails or hangs (offline, or a repo without an "origin" remote).
            fetch_ok = False
            try:
                fetch = GitOps.run(
                    ["git", "fetch", "origin", base_branch],
                    cwd=repo_path,
                    timeout=network_timeout,
                )
                fetch_ok = fetch.returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
                fetch_ok = False

            start_point = base_branch
            if fetch_ok:
                remote_ref = subprocess.run(
                    ["git", "rev-parse", "--verify", f"refs/remotes/origin/{base_branch}"],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=10,
                )
                if remote_ref.returncode == 0:
                    start_point = f"origin/{base_branch}"

            # Create git worktree with task name as branch. --no-track keeps the
            # task branch from tracking origin/<base>; push sets its own upstream
            # (git push -u origin HEAD).
            add_cmd = [
                "git",
                "worktree",
                "add",
                "--no-track",
                "-b",
                task.name,
                str(worktree_path),
                start_point,
            ]

        result = GitOps.run(add_cmd, cwd=repo_path, timeout=network_timeout)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise ValueError(f"Failed to create worktree for {repo_name}: {error_msg}")

        # Record which base the task branched from (branch config is shared
        # repo-wide) so archive_task can diff against the real base instead
        # of guessing the repo's default branch
        subprocess.run(
            ["git", "config", f"branch.{task.name}.tasktreeBase", base_branch],
            cwd=worktree_path,
            capture_output=True,
            timeout=10,
        )

        # Create symlinks for gitignored files
        self._create_gitignore_symlinks(repo_path, worktree_path)

        # Point Claude auto-memory at the repo's own memory dir so it
        # survives worktree deletion (sessions may start here manually,
        # before any launch-time backfill runs)
        if self.config.claude_repo_memory:
            ensure_worktree_claude_settings(worktree_path, repo_path, task.path / ".claude_status")

    def _list_gitignored_files(self, repo_path: Path) -> list[str]:
        """List gitignored files in a repo, relative to the repo root.

        Delegates to git so full gitignore semantics apply (nested
        .gitignore files, directory-wide patterns like ``*.log``).
        ``--directory`` collapses wholly-ignored directories into single
        (later skipped) entries, so huge ignored trees like node_modules
        are never walked or symlinked file-by-file.
        """
        try:
            result = subprocess.run(
                [
                    "git",
                    "ls-files",
                    "--others",
                    "--ignored",
                    "--exclude-standard",
                    "--directory",
                    "-z",
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                # A non-UTF-8 filename must degrade to a skipped entry, not
                # raise UnicodeDecodeError and abort worktree creation
                errors="replace",
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            return []
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.split("\0") if f and not f.endswith("/")]

    def _matches_blocklist(self, filename: str, blocklist: list[str]) -> bool:
        """Check if filename matches any blocklist pattern.

        Args:
            filename: The filename to check
            blocklist: List of glob patterns to match against

        Returns:
            True if the filename matches any blocklist pattern
        """
        return any(fnmatch.fnmatch(filename, pattern) for pattern in blocklist)

    def _create_gitignore_symlinks(self, source_repo: Path, worktree_path: Path) -> None:
        """Create symlinks for gitignored files from source repo to worktree.

        This allows gitignored files like .env to be shared between the main repo
        and worktrees without having to manually copy them. Files matching the
        symlink_blocklist in config are excluded, as is anything under .git or
        .claude (tasktree writes its own worktree .claude settings; a symlink
        there would redirect writes into the main checkout).

        Args:
            source_repo: Path to the source repository
            worktree_path: Path to the new worktree
        """
        blocklist = self.config.symlink_blocklist

        for rel_name in self._list_gitignored_files(source_repo):
            match = source_repo / rel_name
            if not match.is_file():
                continue
            rel_path = Path(rel_name)
            if ".git" in rel_path.parts or ".claude" in rel_path.parts:
                continue
            # Skip files matching the blocklist, by filename or by
            # repo-relative path (so patterns like "secrets/*" work too)
            if self._matches_blocklist(match.name, blocklist) or self._matches_blocklist(
                rel_name, blocklist
            ):
                continue
            link_path = worktree_path / rel_path
            # is_symlink() check catches broken symlinks, for which
            # exists() returns False but symlink_to() would still fail
            if not (link_path.exists() or link_path.is_symlink()):
                link_path.parent.mkdir(parents=True, exist_ok=True)
                link_path.symlink_to(match)

    def add_repo_to_task(self, task: Task, repo_name: str, base_branch: str = "master") -> None:
        """Add a repo worktree to an existing task."""
        self._create_worktree(task, repo_name, base_branch)
        task.worktrees = self._get_worktrees(task)

    def finish_task(self, task: Task) -> None:
        """Finish/delete a task and clean up worktrees."""
        for worktree in task.worktrees:
            self._remove_worktree(worktree, task.name)

        # Remove task directory
        if task.path.exists():
            shutil.rmtree(task.path)

    def set_task_display_name(self, task: Task, display_name: str | None) -> None:
        """Set or clear the task's display alias (TUI label only).

        The folder, branches and worktrees keep the real task name; the alias
        lives in <task>/.tasktree_name. Empty input — or an alias equal to the
        real name — clears the file.
        """
        marker = task.path / ".tasktree_name"
        name = (display_name or "").strip()
        if name == task.name:
            name = ""
        if name:
            marker.write_text(name + "\n", encoding="utf-8")
        elif marker.exists():
            marker.unlink()

    def archive_task(self, task: Task, notes: list[str] | None = None) -> Path | None:
        """Write the task's combined diff to the archive directory.

        Captures committed-but-unmerged work (base...HEAD) plus uncommitted
        changes per worktree, labelled with repo names, preceded by a
        '#'-prefixed metadata header (git apply skips leading non-diff lines).
        Must run before finish_task, which rmtrees the task directory; the
        archive lives outside it (config.get_archive_dir()).

        Returns the archive path, or None when there is nothing to archive.
        """
        from .git_ops import GitOps

        sections: list[str] = []
        header = [
            f"# tasktree-manager archive: {task.name}",
            f"# created: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        ]
        for worktree in task.worktrees:
            if not worktree.path.exists():
                continue
            # Archive the task branch, not whatever HEAD happens to be:
            # finish_task deletes refs/heads/<task>, so a detached or
            # switched worktree must not hide that branch's commits
            branch = task.name
            # Prefer the base recorded at creation — diffing a --base
            # release/1.0 task against the repo default would bloat the
            # archive or, with no default ref resolvable, silently drop
            # the committed work right before the branch is deleted
            base_branch = GitOps.get_task_base(worktree, branch) or GitOps.get_default_branch(
                worktree
            )
            branch_diff = GitOps.get_branch_diff(
                worktree, base_branch, label=worktree.name, ref=branch
            )
            uncommitted_diff = GitOps.get_worktree_diff(worktree, label=worktree.name)
            header.append(f"# repo: {worktree.name} branch: {branch} base: {base_branch}")
            sections.append(branch_diff)
            sections.append(uncommitted_diff)
        for note in notes or []:
            header.append(f"# {note}")

        content = "".join(s for s in sections if s)
        if not content:
            return None

        archive_dir = self.config.get_archive_dir()
        archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = task.name.replace("/", "-")
        archive_path = archive_dir / f"{safe_name}-{timestamp}.patch"
        # Explicit encoding: under LANG=C the locale default is ASCII and a
        # single non-ASCII diff byte would abort the archive
        archive_path.write_text("\n".join(header) + "\n\n" + content, encoding="utf-8")
        return archive_path

    def _remove_worktree(self, worktree: Worktree, branch_name: str) -> None:
        """Remove a worktree from its main repo.

        Args:
            worktree: The worktree to remove
            branch_name: The branch name to delete (usually the task name)
        """
        main_repo = None

        # Try to find main repo from the worktree itself (if it exists and is valid)
        if worktree.path.exists():
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                    cwd=worktree.path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (subprocess.SubprocessError, OSError):
                result = None
            if result and result.returncode == 0:
                main_git_dir = Path(result.stdout.strip())
                main_repo = main_git_dir.parent if main_git_dir.name == ".git" else main_git_dir

        # Fallback: derive main repo from worktree.name (which is the repo relative path)
        if main_repo is None:
            fallback_repo = self.config.repos_dir / worktree.name
            if fallback_repo.exists() and (fallback_repo / ".git").exists():
                main_repo = fallback_repo

        if main_repo is None:
            # Can't find main repo - just clean up the directory if it exists
            return

        # Remove the worktree using git (if path exists). This deletes the
        # worktree's file tree, so give it the (longer) configured timeout.
        if worktree.path.exists():
            self._run_cleanup_git(
                ["git", "worktree", "remove", "--force", str(worktree.path)],
                cwd=main_repo,
                timeout=self.config.git_timeout,
            )

        # Prune stale worktree references (handles case where path was already deleted)
        self._run_cleanup_git(["git", "worktree", "prune"], cwd=main_repo, timeout=10)

        # Delete the branch
        self._run_cleanup_git(["git", "branch", "-D", branch_name], cwd=main_repo, timeout=10)

    @staticmethod
    def _run_cleanup_git(cmd: list[str], cwd: Path, timeout: int) -> None:
        """Run a best-effort git cleanup command, ignoring failures.

        The timeout keeps a hung git (e.g. a repo on an unreachable network
        mount) from blocking task deletion forever; anything git leaves
        behind is caught by the caller's rmtree or the next worktree prune.
        """
        try:
            subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
        except (subprocess.SubprocessError, OSError):
            pass

    def remove_worktree_from_task(self, task: Task, worktree: Worktree) -> None:
        """Remove a single worktree from a task.

        Args:
            task: The task the worktree belongs to
            worktree: The worktree to remove
        """
        self._remove_worktree(worktree, task.name)
        if worktree.path.exists():
            shutil.rmtree(worktree.path)
        task.worktrees = self._get_worktrees(task)

    def get_repos_not_in_task(self, task: Task) -> list[str]:
        """Get list of repos that are not yet in the task."""
        all_repos = set(self.config.get_available_repos())
        task_repos = {wt.name for wt in task.worktrees}
        return sorted(all_repos - task_repos)

    def check_task_safety(self, task: Task) -> TaskSafetyReport:
        """Check if task is safe to delete (parallel version).

        Checks for:
        - Unpushed commits (ahead of remote)
        - Unmerged branches (not merged to main/master)
        - Uncommitted changes (dirty working tree)

        Args:
            task: The task to check

        Returns:
            TaskSafetyReport with lists of issues found
        """
        from .git_ops import GitOps

        report = TaskSafetyReport()
        valid_worktrees = [wt for wt in task.worktrees if wt.path.exists()]

        if not valid_worktrees:
            return report

        def _check_worktree(worktree: Worktree) -> list[RepoIssue]:
            """Check a single worktree and return list of issues."""
            issues = []

            # Get fresh git status
            status = GitOps.get_status(worktree)

            # A failed status means the worktree's state is unknown — the
            # default GitStatus looks clean, and the forge could even clear
            # the branch as merged. Block instead of guessing.
            if status.error:
                issues.append(
                    RepoIssue(
                        repo_name=worktree.name,
                        worktree_path=worktree.path,
                        issue_type="error",
                        details=f"git status failed: {status.error}",
                    )
                )
                return issues

            # Every verdict below (ahead count, merge-base) is about HEAD,
            # while deletion removes refs/heads/<task>. A detached or
            # switched worktree would therefore read as clean/merged even
            # when the task branch holds unpushed commits: block instead.
            if status.branch != task.name:
                checked_out = status.branch or "detached HEAD"
                issues.append(
                    RepoIssue(
                        repo_name=worktree.name,
                        worktree_path=worktree.path,
                        issue_type="error",
                        details=(
                            f"checked out '{checked_out}', not task branch '{task.name}'"
                            " (switch back before deleting)"
                        ),
                    )
                )
                return issues

            # Check for uncommitted changes
            if status.is_dirty:
                issues.append(
                    RepoIssue(
                        repo_name=worktree.name,
                        worktree_path=worktree.path,
                        issue_type="dirty",
                        details=f"{status.changed_files} file{'s' if status.changed_files != 1 else ''} changed",
                    )
                )

            if status.ahead > 0:
                issues.append(
                    RepoIssue(
                        repo_name=worktree.name,
                        worktree_path=worktree.path,
                        issue_type="unpushed",
                        details=f"{status.ahead} commit{'s' if status.ahead != 1 else ''} ahead",
                    )
                )

            # Judge "merged" against the base the task was branched from
            # (recorded at creation), not the repo default: a release/1.0
            # task merged into origin/release/1.0 is done
            default_branch = GitOps.get_task_base(worktree, task.name) or GitOps.get_default_branch(
                worktree
            )
            if not GitOps.check_merged(worktree, default_branch):
                # Squash/rebase merges are invisible to the ancestor check;
                # ask the forge (glab/gh) before flagging the branch unmerged.
                # max_age=0 bypasses the badge cache: this verdict gates a
                # destructive action, so an MR merged a moment ago must count
                branch = status.branch or task.name
                forge_status = forge.get_forge_status(worktree.path, branch, max_age=0)
                if forge_status is not None and forge_status.mr_state == "merged":
                    ref = forge_status.mr_ref or "MR"
                    issues.append(
                        RepoIssue(
                            repo_name=worktree.name,
                            worktree_path=worktree.path,
                            issue_type="merged",
                            details=f"merged remotely via {ref}",
                            branch=branch,
                            mr_url=forge_status.mr_url,
                            mr_state="merged",
                        )
                    )
                else:
                    details = f"not merged to {default_branch}"
                    mr_url = mr_state = None
                    if forge_status is not None and forge_status.mr_state == "open":
                        ref = forge_status.mr_ref or "MR"
                        ci = f", CI {forge_status.ci_state}" if forge_status.ci_state else ""
                        details += f" ({ref} open{ci})"
                        mr_url = forge_status.mr_url
                        mr_state = forge_status.mr_state
                    issues.append(
                        RepoIssue(
                            repo_name=worktree.name,
                            worktree_path=worktree.path,
                            issue_type="unmerged",
                            details=details,
                            branch=branch,
                            mr_url=mr_url,
                            mr_state=mr_state,
                        )
                    )

            return issues

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_check_worktree, wt): wt for wt in valid_worktrees}
            for future in as_completed(futures):
                for issue in future.result():
                    if issue.issue_type == "dirty":
                        report.dirty.append(issue)
                    elif issue.issue_type == "unpushed":
                        report.unpushed.append(issue)
                    elif issue.issue_type == "unmerged":
                        report.unmerged.append(issue)
                    elif issue.issue_type == "error":
                        report.errors.append(issue)
                    elif issue.issue_type == "merged":
                        report.merged_via_forge.append(issue)

        return report

    def push_all_branches(self, task: Task) -> tuple[list[str], list[str]]:
        """Push all branches for task to origin (parallel).

        Args:
            task: The task whose branches to push

        Returns:
            Tuple of (successful_repos, failed_repos) with repo names
        """
        from .git_ops import GitOps

        success_repos = []
        failed_repos = []

        # Handle nonexistent worktrees
        valid_worktrees = []
        for wt in task.worktrees:
            if wt.path.exists():
                valid_worktrees.append(wt)
            else:
                failed_repos.append(wt.name)

        if valid_worktrees:
            # Use parallel push for valid worktrees
            results = GitOps.push_all_parallel(
                Task(name=task.name, path=task.path, worktrees=valid_worktrees)
            )
            for name, success, _ in results:
                if success:
                    success_repos.append(name)
                else:
                    failed_repos.append(name)

        return success_repos, failed_repos

    def ensure_worktree_settings(self, task: Task) -> None:
        """Backfill per-worktree Claude settings for existing worktrees.

        Covers worktrees created before repo memory support (or outside
        tasktree). New worktrees get their settings at creation time.
        """
        if not self.config.claude_repo_memory:
            return

        status_file = task.path / ".claude_status"
        for worktree in task.worktrees:
            repo_path = self.config.repos_dir / worktree.name
            if repo_path.exists() and worktree.path.exists():
                ensure_worktree_claude_settings(worktree.path, repo_path, status_file)

    def ensure_claude_md_files(self, task: Task) -> None:
        """Create the task CLAUDE.md and backfill worktree ones from the repo.

        The task-level file is generated (the task dir is not a git repo).
        Worktree-level files are never generated: when a worktree's branch
        predates the repo's own CLAUDE.md, the repo's file is copied in;
        when the repo has none, the worktree gets none.

        Args:
            task: The task to create CLAUDE.md files for
        """
        task_claude_md = task.path / "CLAUDE.md"
        if not task_claude_md.exists():
            self._create_task_claude_md(task)

        for worktree in task.worktrees:
            wt_claude_md = worktree.path / "CLAUDE.md"
            if not wt_claude_md.exists():
                self._copy_repo_claude_md(worktree)

    def _create_task_claude_md(self, task: Task) -> None:
        """Generate task CLAUDE.md with task name + worktree paths.

        Args:
            task: The task to create CLAUDE.md for
        """
        content = f"""# Task: {task.name}

## Worktrees

"""
        for wt in task.worktrees:
            content += f"- **{wt.name}**: `{wt.path}`\n"
            if wt.branch:
                content += f"  - Branch: `{wt.branch}`\n"

        content += "\n## Notes\n\nAdd task-specific context here.\n"
        (task.path / "CLAUDE.md").write_text(content)

    def _copy_repo_claude_md(self, worktree: Worktree) -> None:
        """Copy the source repo's CLAUDE.md into a worktree that lacks one.

        Happens when the worktree's branch predates the repo's CLAUDE.md.
        Prefers the committed file on the remote default branch (the main
        checkout may be stale or on another branch); falls back to the main
        checkout's working-tree file. Does nothing when the repo has no
        CLAUDE.md — tasktree never generates stub content for repos.

        Args:
            worktree: The worktree to backfill
        """
        repo_path = self.config.repos_dir / worktree.name
        if not repo_path.exists():
            return

        content: str | None = None
        from_commit = False
        try:
            head = subprocess.run(
                ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if head.returncode == 0:
                show = subprocess.run(
                    ["git", "show", f"{head.stdout.strip()}:CLAUDE.md"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if show.returncode == 0:
                    content = show.stdout
                    from_commit = True
        except (OSError, subprocess.SubprocessError):
            pass

        if content is None:
            repo_claude_md = repo_path / "CLAUDE.md"
            if repo_claude_md.exists():
                content = repo_claude_md.read_text()

        if content:
            (worktree.path / "CLAUDE.md").write_text(content)
            if from_commit:
                # The copy is untracked on this branch and would mark the
                # worktree dirty (blocking deletion) for a file tasktree
                # itself wrote. The repo already tracks CLAUDE.md on its
                # default branch, so excluding the untracked copy repo-wide
                # hides nothing a user would want to commit.
                exclude_from_git(repo_path, "CLAUDE.md")
