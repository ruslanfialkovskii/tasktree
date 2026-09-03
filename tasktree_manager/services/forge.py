"""Forge (GitLab/GitHub) MR and CI state lookups via the glab/gh CLIs.

The provider is auto-detected per worktree from its ``origin`` URL:
github.com uses ``gh``; hosts containing "gitlab" (or listed in
``Forge.gitlab_hosts``) use ``glab``; anything else — including the
local-path remotes used throughout the test suite — is skipped.

Every failure mode (missing binary, no remote, timeout, auth error,
malformed JSON) degrades to ``None`` = "unknown"; callers must treat that
as "no forge information", never as an error. ``ForgeStatus(mr_state="none")``
is different: the provider answered and there is no MR for the branch.

Note: GitLab's ``mr list`` JSON carries no pipeline data (verified against
glab 1.107), so ``ci_state`` is currently GitHub-only; the ``head_pipeline``/
``pipeline`` keys are still read tolerantly in case a future glab adds them.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config


@dataclass(frozen=True)
class ForgeStatus:
    """MR/PR state for one branch, as reported by the forge CLI."""

    provider: str  # "gitlab" | "github"
    mr_state: str  # "open" | "merged" | "closed" | "none"
    mr_url: str | None = None
    mr_ref: str | None = None  # display ref: "!42" (gitlab) / "#42" (github)
    ci_state: str | None = None  # "running" | "success" | "failed" | None


class Forge:
    """Class-level forge configuration (mirrors the GitOps pattern)."""

    glab_path: str = "glab"
    gh_path: str = "gh"
    enabled: bool = True
    gitlab_hosts: list[str] = []

    # Own timeout, deliberately shorter than GitOps.network_timeout: forge
    # calls run inside TUI polls and safety sweeps where a hung CLI would
    # stall the whole worker pool.
    FORGE_TIMEOUT = 10
    LOCAL_TIMEOUT = 5
    CACHE_TTL = 60.0

    @classmethod
    def configure(cls, config: "Config") -> None:
        """Apply forge-related settings from config and reset caches."""
        cls.glab_path = config.glab_path
        cls.gh_path = config.gh_path
        cls.enabled = config.forge_enabled
        cls.gitlab_hosts = list(config.forge_gitlab_hosts)
        clear_cache()


_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[float, ForgeStatus | None]] = {}
_which_cache: dict[str, str | None] = {}


def clear_cache() -> None:
    """Drop all cached results (needed by tests and after reconfiguration)."""
    with _lock:
        _cache.clear()
        _which_cache.clear()


def _parse_host(url: str) -> str | None:
    """Extract the hostname from a git remote URL, or None for local paths."""
    url = url.strip()
    if not url:
        return None
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if scheme.lower() not in ("http", "https", "ssh", "git"):
            return None
        host = rest.split("/", 1)[0]
        if "@" in host:
            host = host.rsplit("@", 1)[1]
        host = host.split(":", 1)[0]
        return host.lower() or None
    # scp-like: [user@]host:path — exclude local paths and Windows drives
    if url.startswith(("/", ".", "~")):
        return None
    match = re.match(r"^(?:[^@/]+@)?(?P<host>[^:/]+):.+$", url)
    if match:
        host = match.group("host")
        if len(host) == 1:  # Windows drive letter (C:\...)
            return None
        return host.lower()
    return None


def detect_provider(url: str) -> str | None:
    """Map a remote URL to "gitlab" / "github", or None if neither."""
    host = _parse_host(url)
    if host is None:
        return None
    if host == "github.com" or host.endswith(".github.com"):
        return "github"
    if "gitlab" in host or host in {h.lower() for h in Forge.gitlab_hosts}:
        return "gitlab"
    return None


def _get_remote_url(worktree_path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=Forge.LOCAL_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_binary(path: str) -> str | None:
    """shutil.which with memoization — a missing CLI must not cost a lookup per poll."""
    with _lock:
        if path in _which_cache:
            return _which_cache[path]
    resolved = shutil.which(path)
    with _lock:
        _which_cache[path] = resolved
    return resolved


def _run_forge_command(cmd: list[str], cwd: Path) -> str | None:
    """Run a forge CLI command; stdout on success, None on any failure.

    stdin=DEVNULL is essential: an unauthenticated glab/gh may prompt
    interactively, which would hang the calling worker thread.
    """
    from .git_ops import GitOps

    try:
        # GitOps.run tracks the child so app exit can terminate a hung gh/glab
        result = GitOps.run(cmd, cwd=cwd, timeout=Forge.FORGE_TIMEOUT)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


# CI state vocabulary across GitLab pipeline statuses, GitHub CheckRun
# conclusions/statuses and StatusContext states.
_CI_FAILED = {
    "failure",
    "failed",
    "error",
    "timed_out",
    "cancelled",
    "canceled",
    "action_required",
    "startup_failure",
}
_CI_RUNNING = {
    "running",
    "pending",
    "created",
    "waiting_for_resource",
    "preparing",
    "scheduled",
    "in_progress",
    "queued",
    "requested",
    "waiting",
    "expected",
}
_CI_SUCCESS = {"success", "passed"}


def _classify_ci(raw: object) -> str | None:
    state = str(raw or "").lower()
    if state in _CI_FAILED:
        return "failed"
    if state in _CI_RUNNING:
        return "running"
    if state in _CI_SUCCESS:
        return "success"
    return None  # neutral, skipped, manual, unknown


def _reduce_checks(items: object) -> str | None:
    """Reduce a gh statusCheckRollup list to one CI state."""
    if not isinstance(items, list):
        return None
    states = [
        _classify_ci(item.get("conclusion") or item.get("state") or item.get("status"))
        for item in items
        if isinstance(item, dict)
    ]
    if "failed" in states:
        return "failed"
    if "running" in states:
        return "running"
    if "success" in states:
        return "success"
    return None


def _pick_best(records: list[dict], state_of) -> tuple[dict, str] | None:
    """Pick the most relevant MR/PR: open beats merged beats closed.

    An open MR means work is in flight right now — a stale merged MR from a
    previous life of the same branch name must not mask it, or safety checks
    would declare the branch merged while its current MR is still open.
    """
    normalized = [(record, state_of(record)) for record in records if isinstance(record, dict)]
    for preferred in ("open", "merged", "closed"):
        for record, state in normalized:
            if state == preferred:
                return record, state
    return None


_GLAB_STATE_MAP = {"opened": "open", "merged": "merged", "closed": "closed", "locked": "open"}


def _parse_glab_payload(payload: str) -> ForgeStatus | None:
    try:
        data = json.loads(payload)
        if not isinstance(data, list):
            return None
        if not data:
            return ForgeStatus(provider="gitlab", mr_state="none")
        best = _pick_best(data, lambda mr: _GLAB_STATE_MAP.get(str(mr.get("state", "")).lower()))
        if best is None:
            return ForgeStatus(provider="gitlab", mr_state="none")
        mr, state = best
        references = mr.get("references")
        mr_ref = references.get("short") if isinstance(references, dict) else None
        if not mr_ref and mr.get("iid") is not None:
            mr_ref = f"!{mr['iid']}"
        pipeline = mr.get("head_pipeline") or mr.get("pipeline")
        ci_state = _classify_ci(pipeline.get("status")) if isinstance(pipeline, dict) else None
        return ForgeStatus(
            provider="gitlab",
            mr_state=state,
            mr_url=mr.get("web_url"),
            mr_ref=mr_ref,
            ci_state=ci_state,
        )
    except (TypeError, KeyError, ValueError, AttributeError):
        # ValueError covers json.JSONDecodeError
        return None


_GH_STATE_MAP = {"open": "open", "merged": "merged", "closed": "closed"}


def _parse_gh_payload(payload: str) -> ForgeStatus | None:
    try:
        data = json.loads(payload)
        if not isinstance(data, list):
            return None
        if not data:
            return ForgeStatus(provider="github", mr_state="none")
        best = _pick_best(data, lambda pr: _GH_STATE_MAP.get(str(pr.get("state", "")).lower()))
        if best is None:
            return ForgeStatus(provider="github", mr_state="none")
        pr, state = best
        number = pr.get("number")
        return ForgeStatus(
            provider="github",
            mr_state=state,
            mr_url=pr.get("url"),
            mr_ref=f"#{number}" if number is not None else None,
            ci_state=_reduce_checks(pr.get("statusCheckRollup")),
        )
    except (TypeError, KeyError, ValueError, AttributeError):
        return None


def _fetch_status(worktree_path: Path, branch: str) -> ForgeStatus | None:
    provider = detect_provider(_get_remote_url(worktree_path))
    if provider is None:
        return None
    if provider == "gitlab":
        binary = _resolve_binary(Forge.glab_path)
        if binary is None:
            return None
        payload = _run_forge_command(
            [binary, "mr", "list", "--source-branch", branch, "--all", "-F", "json"],
            worktree_path,
        )
        return _parse_glab_payload(payload) if payload is not None else None
    binary = _resolve_binary(Forge.gh_path)
    if binary is None:
        return None
    payload = _run_forge_command(
        [
            binary,
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "state,url,number,statusCheckRollup",
        ],
        worktree_path,
    )
    return _parse_gh_payload(payload) if payload is not None else None


def get_forge_status(
    worktree_path: Path, branch: str, max_age: float | None = None
) -> ForgeStatus | None:
    """MR/PR state for a worktree's branch, TTL-cached; None = unknown.

    ``max_age`` caps how old a cached entry may be (default CACHE_TTL);
    pass 0 to force a live lookup, as the delete safety check does.

    Thread-safe: called concurrently from the safety-check ThreadPoolExecutor
    and TUI poll workers. Two concurrent misses on the same key may fetch
    twice; the second write wins, which is harmless.
    """
    if not Forge.enabled or not branch:
        return None
    ttl = Forge.CACHE_TTL if max_age is None else max_age
    key = (str(worktree_path), branch)
    with _lock:
        cached = _cache.get(key)
        if cached is not None and time.monotonic() - cached[0] < ttl:
            return cached[1]
    result = _fetch_status(worktree_path, branch)
    with _lock:
        _cache[key] = (time.monotonic(), result)
    return result
