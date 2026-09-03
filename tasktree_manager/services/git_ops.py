"""Git operations service for tasktree-manager."""

import os
import re
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .models import GitStatus, Task, Worktree

# Matches the "[ahead 1, behind 2]" suffix of a porcelain branch header
_AHEAD_BEHIND_RE = re.compile(r"\[(?:ahead (\d+))?(?:, )?(?:behind (\d+))?\]")

# Control characters (incl. ESC) that must never reach the terminal from a
# filename or git message: a crafted name could otherwise emit OSC/CSI
# sequences (clipboard writes, screen clears) through the status panel
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")

# Hash of git's empty tree: the diff base for a repo without commits
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def sanitize_text(text: str) -> str:
    """Replace control characters with a visible escape (``\\x1b``)."""
    return _CONTROL_CHARS_RE.sub(lambda m: f"\\x{ord(m.group()):02x}", text)


class GitCommandError(RuntimeError):
    """A git command failed, timed out or could not be started."""


class GitOps:
    """Git operations for worktrees."""

    # Timeout for local-only git commands (status, rev-parse) in seconds
    LOCAL_TIMEOUT = 5
    # Timeout for commands that may hit the network (push/pull/fetch) and
    # for long local work (diffs over big trees). Overridden at app startup
    # from the [git] timeout config setting.
    network_timeout: int = 30

    # Child processes currently running, so the app can terminate them on
    # exit: Textual thread workers run on asyncio's default executor, which
    # asyncio.run() joins at shutdown, so a git fetch still in flight would
    # otherwise keep the process alive after the terminal is restored
    _live_procs: set = set()
    _procs_lock = threading.Lock()

    @staticmethod
    def run(
        cmd: list[str],
        cwd,
        timeout: float,
        *,
        env: dict | None = None,
    ) -> subprocess.CompletedProcess:
        """Run a command with a timeout, tracking it for terminate_all().

        Behaves like subprocess.run(capture_output=True, text=True): the
        child is killed on timeout and TimeoutExpired is re-raised. stdin is
        /dev/null and GIT_TERMINAL_PROMPT=0 so git never waits for a
        credential prompt inside a worker thread.
        """
        full_env = dict(os.environ)
        full_env.setdefault("GIT_TERMINAL_PROMPT", "0")
        if env:
            full_env.update(env)
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=full_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
        )
        with GitOps._procs_lock:
            GitOps._live_procs.add(proc)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        finally:
            with GitOps._procs_lock:
                GitOps._live_procs.discard(proc)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)

    @staticmethod
    def terminate_all() -> None:
        """Terminate every tracked child process (called on app exit)."""
        with GitOps._procs_lock:
            procs = list(GitOps._live_procs)
        for proc in procs:
            try:
                proc.terminate()
            except OSError:
                pass

    @staticmethod
    def get_status(worktree: Worktree) -> GitStatus:
        """Get the git status of a worktree.

        Uses a single `git status --porcelain --branch -z` call to read the
        branch name, ahead/behind counts and changed files at once. The -z
        format is NUL-separated and unquoted, so exotic filenames (quotes,
        spaces, newlines) come through verbatim; control characters are
        escaped before they can reach a widget.
        """
        status = GitStatus()

        if not worktree.path.exists():
            return status

        try:
            result = GitOps.run(
                ["git", "status", "--porcelain", "--branch", "-z"],
                cwd=worktree.path,
                timeout=GitOps.LOCAL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            status.error = "Git status timed out"
            return status
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            status.error = f"Git status error: {e}"
            return status

        if result.returncode != 0:
            detail = sanitize_text(result.stderr.strip()) or "unknown error"
            status.error = f"Git status failed: {detail}"
            return status

        # Rename/copy entries are followed by the original path as an
        # extra NUL-separated token, hence the manual index walk
        # Split on the NUL separators FIRST; sanitizing escapes control
        # characters (NUL included), which must only happen per token
        tokens = [sanitize_text(token) for token in result.stdout.split("\0")]
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if len(token) < 4:
                continue
            if token.startswith("## "):
                GitOps._parse_branch_header(token[3:], status)
                continue
            status_code = token[:2]
            filename = token[3:]

            if "R" in status_code or "C" in status_code:
                if index < len(tokens) and tokens[index]:
                    filename = f"{tokens[index]} -> {filename}"
                    index += 1

            if status_code == "??":
                status.untracked.append(filename)
            elif "U" in status_code or status_code in ("AA", "DD"):
                # Unmerged (conflict) entries - count as modified so the
                # worktree shows as dirty and safety checks block deletion
                status.modified.append(filename)
            elif status_code[0] in "MADRCT":
                status.staged.append(filename)
            elif status_code[1] in "MADRCT":
                status.modified.append(filename)
            else:
                continue
            status.entries.append((status_code, filename))

        return status

    @staticmethod
    def _parse_branch_header(header: str, status: GitStatus) -> None:
        """Parse the `## ...` header of `git status --porcelain --branch`.

        Handles the formats:
            HEAD (no branch)                      <- detached, branch stays ""
            No commits yet on <branch>
            <branch>
            <branch>...<upstream>
            <branch>...<upstream> [ahead 1, behind 2]
        """
        if header.startswith("HEAD"):
            return
        if header.startswith("No commits yet on "):
            status.branch = header[len("No commits yet on ") :]
            return

        status.branch = header.split("...", 1)[0]

        match = _AHEAD_BEHIND_RE.search(header)
        if match:
            status.ahead = int(match.group(1) or 0)
            status.behind = int(match.group(2) or 0)

    @staticmethod
    def update_worktree_status(worktree: Worktree) -> GitStatus:
        """Update a worktree's status fields and return the full status.

        A failed or timed-out status leaves the worktree's last known
        branch/dirty state in place: the default GitStatus looks clean, and
        rendering a dirty worktree with a green check on a transient
        timeout would be wrong.
        """
        status = GitOps.get_status(worktree)
        if not status.error:
            worktree.branch = status.branch
            worktree.is_dirty = status.is_dirty
            worktree.changed_files = status.changed_files
        return status

    @staticmethod
    def push(worktree: Worktree) -> tuple[bool, str]:
        """Push changes in a worktree."""
        try:
            result = GitOps.run(
                ["git", "push", "-u", "origin", "HEAD"],
                cwd=worktree.path,
                timeout=GitOps.network_timeout,
            )
            if result.returncode == 0:
                return True, result.stdout or "Pushed successfully"
            return False, result.stderr or "Push failed"
        except subprocess.TimeoutExpired:
            return False, "Push timed out"
        except (subprocess.SubprocessError, OSError) as e:
            return False, str(e)

    @staticmethod
    def pull(worktree: Worktree) -> tuple[bool, str]:
        """Pull changes in a worktree."""
        try:
            result = GitOps.run(
                ["git", "pull"],
                cwd=worktree.path,
                timeout=GitOps.network_timeout,
            )
            if result.returncode == 0:
                return True, result.stdout or "Pulled successfully"
            return False, result.stderr or "Pull failed"
        except subprocess.TimeoutExpired:
            return False, "Pull timed out"
        except (subprocess.SubprocessError, OSError) as e:
            return False, str(e)

    @staticmethod
    def _git_stdout(
        worktree: Worktree,
        args: list[str],
        *,
        check: bool = False,
        timeout: float | None = None,
        env: dict | None = None,
    ) -> str:
        """Run a local read-only git command in the worktree, returning stdout.

        With ``check=False`` (probes such as rev-parse --verify) any failure
        yields "". With ``check=True`` a timeout, a non-zero exit or a
        missing git raise GitCommandError: the archive helpers use this so a
        diff that could not be produced never masquerades as "nothing to
        archive" right before a branch is deleted. errors="replace" keeps
        non-UTF-8 diff content (e.g. latin-1 sources) from raising
        UnicodeDecodeError mid-archive.
        """
        cmd = ["git", *args]
        try:
            result = GitOps.run(
                cmd,
                cwd=worktree.path,
                timeout=timeout if timeout is not None else GitOps.LOCAL_TIMEOUT,
                env=env,
            )
        except (subprocess.SubprocessError, OSError) as e:
            if check:
                raise GitCommandError(f"{' '.join(cmd)}: {e}") from e
            return ""
        if check and result.returncode != 0:
            raise GitCommandError(f"{' '.join(cmd)}: {result.stderr.strip() or 'failed'}")
        return result.stdout

    @staticmethod
    def get_worktree_diff(worktree: Worktree, label: str | None = None) -> str:
        """Return a unified diff of all uncommitted changes in a worktree.

        Covers staged, unstaged and untracked changes relative to HEAD (the
        empty tree for a repo without commits) in ONE git invocation: the
        real index is copied to a temporary file, everything is ``git add
        -A``-ed into that copy, and ``git diff --cached`` is taken against
        HEAD. The worktree's own index is never touched. ``--binary`` keeps
        binary changes applyable. When *label* is given, every file path is
        prefixed with ``<label>/`` so diffs from several repos can be
        concatenated into one view without colliding on identical paths.

        Returns an empty string when the worktree is clean or missing.
        Raises GitCommandError when the diff cannot be produced.
        """
        if not worktree.path.exists():
            return ""

        # Without a label, git's default a/ b/ prefixes are used.
        prefixes = [f"--src-prefix=a/{label}/", f"--dst-prefix=b/{label}/"] if label else []
        timeout = GitOps.network_timeout

        index_path = GitOps._git_stdout(
            worktree, ["rev-parse", "--git-path", "index"], check=True
        ).strip()
        real_index = Path(index_path)
        if not real_index.is_absolute():
            real_index = worktree.path / real_index
        head = (
            "HEAD"
            if GitOps._git_stdout(worktree, ["rev-parse", "--verify", "--quiet", "HEAD"])
            else _EMPTY_TREE
        )

        fd, tmp_index = tempfile.mkstemp(prefix="tasktree-index-")
        os.close(fd)
        try:
            if real_index.exists():
                shutil.copyfile(real_index, tmp_index)
            else:
                os.unlink(tmp_index)  # let git create a fresh index
            env = {"GIT_INDEX_FILE": tmp_index}
            GitOps._git_stdout(
                worktree, ["add", "-A", "--", "."], check=True, timeout=timeout, env=env
            )
            return GitOps._git_stdout(
                worktree,
                ["diff", "--cached", "--binary", "--no-color", *prefixes, head],
                check=True,
                timeout=timeout,
                env=env,
            )
        finally:
            for leftover in (tmp_index, tmp_index + ".lock"):
                try:
                    os.unlink(leftover)
                except OSError:
                    pass

    @staticmethod
    def get_task_base(worktree: Worktree, branch: str) -> str | None:
        """Read the base branch recorded at worktree creation, if any.

        tasktree-manager stores it as ``branch.<name>.tasktreeBase`` in the
        repo's shared branch config; tasks created before this existed (or
        worktrees made by hand) return None.
        """
        out = GitOps._git_stdout(worktree, ["config", "--get", f"branch.{branch}.tasktreeBase"])
        return out.strip() or None

    @staticmethod
    def get_branch_diff(
        worktree: Worktree, base_branch: str, label: str | None = None, ref: str = "HEAD"
    ) -> str:
        """Return the diff of committed-but-unmerged work: base...<ref>.

        Uses the three-dot form (changes since the merge base), preferring
        ``origin/<base>`` and falling back to the local base branch, then to
        any ref the name resolves to. No fetch is performed — archives need
        completeness of *our* work, not remote freshness. ``ref`` names the
        branch whose work is archived (default HEAD); when it does not
        resolve, HEAD is used. ``--binary`` keeps binary changes applyable.
        Returns "" when no base ref resolves or nothing differs. Raises
        GitCommandError when the diff itself fails.
        """
        if not worktree.path.exists():
            return ""

        base_ref = None
        for candidate in (
            f"refs/remotes/origin/{base_branch}",
            f"refs/heads/{base_branch}",
            f"{base_branch}^{{commit}}",
        ):
            probe = GitOps._git_stdout(worktree, ["rev-parse", "--verify", "--quiet", candidate])
            if probe.strip():
                base_ref = candidate
                break
        if base_ref is None:
            return ""

        head_ref = "HEAD"
        if ref != "HEAD":
            probe = GitOps._git_stdout(
                worktree, ["rev-parse", "--verify", "--quiet", f"refs/heads/{ref}"]
            )
            if probe.strip():
                head_ref = f"refs/heads/{ref}"

        prefixes = [f"--src-prefix=a/{label}/", f"--dst-prefix=b/{label}/"] if label else []
        return GitOps._git_stdout(
            worktree,
            ["diff", "--binary", "--no-color", *prefixes, f"{base_ref}...{head_ref}"],
            check=True,
            timeout=GitOps.network_timeout,
        )

    @staticmethod
    def build_task_diff(task: Task) -> str:
        """Build a combined diff across all of a task's worktrees.

        Each worktree's changes are labelled with its repo name so a single
        review shows every repo without path collisions. Returns an empty
        string when nothing in the task has changed.
        """
        parts = [GitOps.get_worktree_diff(wt, label=wt.name) for wt in task.worktrees]
        return "".join(p for p in parts if p)

    @staticmethod
    def get_default_branch(worktree: Worktree) -> str:
        """Get the default branch (main/master) for a worktree's repo.

        Returns:
            The default branch name, or "main" as fallback.
        """
        try:
            # Try to get the default branch from origin/HEAD
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=GitOps.LOCAL_TIMEOUT,
            )
            if result.returncode == 0:
                # Output is like "refs/remotes/origin/main"; strip the prefix
                # rather than splitting on "/" so slashed branch names
                # (release/1.0) survive intact
                ref = result.stdout.strip()
                branch = ref.removeprefix("refs/remotes/origin/")
                if branch:
                    return branch
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        # Fallback: check which of main/master exists
        for branch in ["main", "master"]:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--verify", f"refs/remotes/origin/{branch}"],
                    cwd=worktree.path,
                    capture_output=True,
                    timeout=GitOps.LOCAL_TIMEOUT,
                )
                if result.returncode == 0:
                    return branch
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass

        # Final fallback
        return "main"

    @staticmethod
    def check_merged(worktree: Worktree, base_branch: str, fetch: bool = True) -> bool:
        """Check if the current branch is merged into base_branch.

        Args:
            worktree: The worktree to check
            base_branch: The base branch to check against (e.g., "main", "master")
            fetch: Fetch origin first. Pass False for fast offline checks that
                can tolerate a slightly stale origin/<base> ref.

        Returns:
            True if current branch is merged into base_branch, False otherwise.
        """
        try:
            if fetch:
                # Fetch latest remote refs so we detect merges done via GitLab/GitHub UI
                GitOps.run(
                    ["git", "fetch", "origin", base_branch],
                    cwd=worktree.path,
                    timeout=GitOps.network_timeout,
                )
            # Use git merge-base --is-ancestor to check if HEAD is reachable from base
            # This checks if the current branch has been merged
            result = GitOps.run(
                ["git", "merge-base", "--is-ancestor", "HEAD", f"origin/{base_branch}"],
                cwd=worktree.path,
                timeout=GitOps.LOCAL_TIMEOUT,
            )
            # Exit code 0 means HEAD is an ancestor of base (merged)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            # If we can't determine, assume not merged (safer)
            return False

    @staticmethod
    def update_all_worktree_statuses(worktrees: list[Worktree], max_workers: int = 8) -> None:
        """Update status for multiple worktrees in parallel.

        Args:
            worktrees: List of worktrees to update
            max_workers: Maximum number of parallel workers
        """
        if not worktrees:
            return

        workers = min(max_workers, len(worktrees))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(GitOps.update_worktree_status, wt): wt for wt in worktrees}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    # One failing worktree must not abort the whole refresh
                    continue

    @staticmethod
    def get_statuses_parallel(
        worktrees: list[Worktree], max_workers: int = 8
    ) -> dict[str, GitStatus]:
        """Get full statuses for multiple worktrees in parallel, keyed by name.

        Args:
            worktrees: List of worktrees to query
            max_workers: Maximum number of parallel workers

        Returns:
            Dict mapping worktree name to its GitStatus
        """
        statuses: dict[str, GitStatus] = {}
        if not worktrees:
            return statuses

        workers = min(max_workers, len(worktrees))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(GitOps.get_status, wt): wt for wt in worktrees}
            for future in as_completed(futures):
                wt = futures[future]
                try:
                    statuses[wt.name] = future.result()
                except Exception:
                    continue
        return statuses

    @staticmethod
    def push_all_parallel(task: Task, max_workers: int = 3) -> list[tuple[str, bool, str]]:
        """Push all worktrees in a task in parallel.

        Args:
            task: The task containing worktrees to push
            max_workers: Maximum number of parallel workers

        Returns:
            List of (worktree_name, success, message) tuples
        """
        if not task.worktrees:
            return []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(GitOps.push, wt): wt for wt in task.worktrees}
            results = []
            for future in as_completed(futures):
                wt = futures[future]
                success, message = future.result()
                results.append((wt.name, success, message))
            return results

    @staticmethod
    def pull_all_parallel(task: Task, max_workers: int = 3) -> list[tuple[str, bool, str]]:
        """Pull all worktrees in a task in parallel.

        Args:
            task: The task containing worktrees to pull
            max_workers: Maximum number of parallel workers

        Returns:
            List of (worktree_name, success, message) tuples
        """
        if not task.worktrees:
            return []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(GitOps.pull, wt): wt for wt in task.worktrees}
            results = []
            for future in as_completed(futures):
                wt = futures[future]
                success, message = future.result()
                results.append((wt.name, success, message))
            return results
