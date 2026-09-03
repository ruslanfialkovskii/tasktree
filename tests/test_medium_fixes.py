"""Regression tests for the medium-severity review fixes."""

import subprocess
from pathlib import Path

import pytest
from textual.widgets import Button, Input

from tasktree_manager.cli import run_cli
from tasktree_manager.services import forge
from tasktree_manager.services.claude_hooks import (
    claude_config_dir,
    exclude_from_git,
    has_claude_session,
    repo_memory_dir,
)
from tasktree_manager.services.config import DEFAULT_SYMLINK_BLOCKLIST, Config
from tasktree_manager.services.forge import ForgeStatus
from tasktree_manager.services.git_ops import GitCommandError, GitOps, sanitize_text
from tasktree_manager.services.models import Worktree
from tasktree_manager.services.task_manager import normalize_base_branch
from tasktree_manager.widgets.create_modal import (
    AddRepoModal,
    ConfirmModal,
    CreateTaskModal,
    SafeDeleteModal,
)
from tasktree_manager.widgets.setup_modal import SetupModal


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _commit_file(path: Path, name: str, content: str = "x\n") -> None:
    (path / name).write_text(content)
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", f"add {name}")


# --------------------------------------------------------------------------
# task_manager
# --------------------------------------------------------------------------


class TestCreateTaskRollback:
    def test_bad_base_leaves_no_ghost_task(self, task_manager, sample_repos):
        with pytest.raises(ValueError, match="Failed to create worktree"):
            task_manager.create_task("GHOST", ["repo-alpha"], "no-such-branch")
        assert not (task_manager.config.tasks_dir / "GHOST").exists()
        assert task_manager.list_tasks() == []

    def test_partial_failure_rolls_back_created_worktrees(self, task_manager, sample_repos):
        """Repo #1 succeeds, repo #2 does not exist: the task and the first
        worktree (and its branch) are removed again."""
        _, branch = sample_repos
        with pytest.raises(ValueError, match="Repository not found"):
            task_manager.create_task("PARTIAL", ["repo-alpha", "missing-repo"], branch)
        assert not (task_manager.config.tasks_dir / "PARTIAL").exists()
        branches = subprocess.run(
            ["git", "branch", "--list", "PARTIAL"],
            cwd=task_manager.config.repos_dir / "repo-alpha",
            capture_output=True,
            text=True,
        ).stdout
        assert branches.strip() == ""

    def test_cli_create_bad_base_allows_retry(self, config, sample_repos, capsys):
        _, branch = sample_repos
        assert run_cli(["create", "RETRY", "--repos", "repo-alpha", "--base", "nope"], config) == 1
        assert "Failed to create worktree" in capsys.readouterr().err
        assert run_cli(["create", "RETRY", "--repos", "repo-alpha", "--base", branch], config) == 0


class TestWorktreeCreation:
    def test_prunes_stale_registration(self, task_manager, sample_repos):
        """A worktree directory deleted by hand no longer blocks re-adding."""
        _, branch = sample_repos
        task = task_manager.create_task("STALE", ["repo-alpha"], branch)
        subprocess.run(["rm", "-rf", str(task.worktrees[0].path)], check=True)
        task = task_manager.get_task("STALE")
        assert task.worktrees == []
        task_manager.add_repo_to_task(task, "repo-alpha", branch)
        assert [wt.name for wt in task.worktrees] == ["repo-alpha"]

    def test_fetch_timeout_falls_back_to_local_base(self, task_manager, sample_repos, monkeypatch):
        _, branch = sample_repos
        real_run = GitOps.run

        def flaky_run(cmd, cwd, timeout, **kwargs):
            if cmd[:2] == ["git", "fetch"]:
                raise subprocess.TimeoutExpired(cmd, timeout)
            return real_run(cmd, cwd, timeout, **kwargs)

        monkeypatch.setattr(GitOps, "run", staticmethod(flaky_run))
        task = task_manager.create_task("OFFLINE", ["repo-alpha"], branch)
        assert task.worktrees[0].path.exists()

    @pytest.mark.parametrize(
        "spelled,expected",
        [("origin/main", "main"), ("refs/heads/main", "main"), ("refs/remotes/origin/dev", "dev")],
    )
    def test_normalize_base_branch(self, spelled, expected):
        assert normalize_base_branch(spelled) == expected

    def test_origin_prefixed_base_is_recorded_normalised(self, task_manager, repo_with_origin):
        base = repo_with_origin
        task = task_manager.create_task("PREFIXED", ["repo-remote"], f"origin/{base}")
        wt = task.worktrees[0]
        assert GitOps.get_task_base(wt, "PREFIXED") == base
        _commit_file(wt.path, "work.txt")
        archive = task_manager.archive_task(task)
        assert archive is not None and "work.txt" in archive.read_text()


class TestSafetyUsesRecordedBase:
    def test_merged_into_recorded_base_is_safe(self, config, task_manager, repo_with_origin):
        base = repo_with_origin
        repo = config.repos_dir / "repo-remote"
        _git(repo, "branch", "release-1", base)
        _git(repo, "push", "-q", "origin", "release-1")

        task = task_manager.create_task("REL", ["repo-remote"], "release-1")
        wt = task.worktrees[0]
        _commit_file(wt.path, "rel.txt")
        _git(wt.path, "push", "-q", "-u", "origin", "HEAD")
        # Fast-forward the remote release branch to the task branch
        _git(wt.path, "push", "-q", "origin", "HEAD:release-1")

        report = task_manager.check_task_safety(task)
        assert report.is_safe(), report

    def test_safety_bypasses_forge_cache(self, task_manager, sample_repo, monkeypatch):
        _, branch = sample_repo
        task = task_manager.create_task("FORGE-TTL", ["sample-repo"], branch)
        seen: list[float | None] = []

        def fake(worktree_path, branch, max_age=None):
            seen.append(max_age)
            return ForgeStatus(provider="gitlab", mr_state="merged", mr_ref="!1")

        monkeypatch.setattr(forge, "get_forge_status", fake)
        monkeypatch.setattr(forge.Forge, "enabled", True)
        task_manager.check_task_safety(task)
        assert seen and all(age == 0 for age in seen)


class TestForgeCacheMaxAge:
    def test_max_age_zero_refetches(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(forge.Forge, "enabled", True)
        monkeypatch.setattr(forge, "_fetch_status", lambda p, b: calls.append(1) or None)
        forge.clear_cache()
        forge.get_forge_status(tmp_path, "b")
        forge.get_forge_status(tmp_path, "b")
        assert len(calls) == 1  # TTL cache hit
        forge.get_forge_status(tmp_path, "b", max_age=0)
        assert len(calls) == 2


class TestCopiedClaudeMdNotDirty:
    def test_copied_claude_md_is_excluded(self, config, task_manager, repo_with_origin):
        base = repo_with_origin
        repo = config.repos_dir / "repo-remote"
        # Repo default branch gets a CLAUDE.md; the task branches off earlier
        _git(repo, "branch", "old-base", "HEAD")
        _git(repo, "push", "-q", "origin", "old-base")
        _commit_file(repo, "CLAUDE.md", "# repo\n")
        _git(repo, "push", "-q", "origin", "HEAD")
        _git(repo, "remote", "set-head", "origin", base)

        task = task_manager.create_task("CMD", ["repo-remote"], "old-base")
        task_manager.ensure_claude_md_files(task)
        wt = task.worktrees[0]
        assert (wt.path / "CLAUDE.md").read_text() == "# repo\n"
        status = GitOps.get_status(wt)
        assert not status.is_dirty, status.untracked


# --------------------------------------------------------------------------
# git_ops
# --------------------------------------------------------------------------


class TestGitOpsHardening:
    def test_sanitize_control_characters(self):
        assert sanitize_text("a\x1b]52;c;x\x07b") == "a\\x1b]52;c;x\\x07b"

    def test_status_escapes_control_chars_in_filenames(self, sample_repo):
        repo_path, _ = sample_repo
        (repo_path / "bad\x1b[2Jname.txt").write_text("x\n")
        status = GitOps.get_status(Worktree(name="r", path=repo_path))
        assert status.untracked == ["bad\\x1b[2Jname.txt"]

    def test_status_error_keeps_last_known_state(self, sample_repo, monkeypatch):
        repo_path, _ = sample_repo
        wt = Worktree(name="r", path=repo_path, branch="feat", is_dirty=True, changed_files=7)

        def timeout(cmd, cwd, timeout, **kw):
            raise subprocess.TimeoutExpired(cmd, timeout)

        monkeypatch.setattr(GitOps, "run", staticmethod(timeout))
        status = GitOps.update_worktree_status(wt)
        assert status.error
        assert (wt.branch, wt.is_dirty, wt.changed_files) == ("feat", True, 7)

    def test_worktree_diff_covers_binary_and_untracked_in_one_pass(self, sample_repo):
        repo_path, _ = sample_repo
        (repo_path / "logo.bin").write_bytes(bytes(range(256)))
        (repo_path / "new.txt").write_text("new\n")
        (repo_path / "README.md").write_text("changed\n")
        diff = GitOps.get_worktree_diff(Worktree(name="r", path=repo_path), label="r")
        assert "GIT binary patch" in diff
        assert "b/r/new.txt" in diff and "b/r/README.md" in diff
        # The real index was not touched: nothing is staged
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        ).stdout
        assert staged.strip() == ""

    def test_diff_failure_raises_instead_of_empty(self, sample_repo, monkeypatch):
        repo_path, _ = sample_repo
        (repo_path / "new.txt").write_text("new\n")

        def timeout(cmd, cwd, timeout, **kw):
            raise subprocess.TimeoutExpired(cmd, timeout)

        monkeypatch.setattr(GitOps, "run", staticmethod(timeout))
        with pytest.raises(GitCommandError):
            GitOps.get_worktree_diff(Worktree(name="r", path=repo_path))

    def test_archive_failure_blocks_cli_finish(self, config, repo_with_origin, monkeypatch, capsys):
        base = repo_with_origin
        assert run_cli(["create", "ARCH", "--repos", "repo-remote", "--base", base], config) == 0
        (config.tasks_dir / "ARCH" / "repo-remote" / "wip.txt").write_text("wip\n")

        def boom(worktree, label=None):
            raise GitCommandError("git diff: timed out")

        monkeypatch.setattr(GitOps, "get_worktree_diff", staticmethod(boom))
        capsys.readouterr()
        assert run_cli(["finish", "ARCH", "--force"], config) == 1
        assert "timed out" in capsys.readouterr().err
        assert (config.tasks_dir / "ARCH").exists()

    def test_terminate_all_kills_tracked_children(self):
        import threading

        results = {}

        def runner():
            try:
                GitOps.run(["sleep", "30"], cwd=".", timeout=60)
                results["rc"] = 0
            except Exception as e:  # pragma: no cover - diagnostic
                results["rc"] = e

        t = threading.Thread(target=runner)
        t.start()
        for _ in range(100):
            with GitOps._procs_lock:
                if GitOps._live_procs:
                    break
            threading.Event().wait(0.02)
        GitOps.terminate_all()
        t.join(timeout=5)
        assert not t.is_alive()


# --------------------------------------------------------------------------
# claude_hooks
# --------------------------------------------------------------------------


class TestClaudeHooksFixes:
    def test_exclude_appends_newline_first(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        exclude = repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("*.log")  # no trailing newline
        exclude_from_git(repo, ".claude/settings.local.json")
        exclude_from_git(repo, ".claude/settings.local.json")
        assert exclude.read_text().splitlines() == ["*.log", ".claude/settings.local.json"]

    def test_claude_config_dir_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        assert claude_config_dir() == tmp_path / "cfg"
        project = tmp_path / "cfg" / "projects" / "-work-repo"
        project.mkdir(parents=True)
        (project / "abc.jsonl").write_text("{}\n")
        assert has_claude_session(Path("/work/repo"))
        assert repo_memory_dir(Path("/work/repo")) == project / "memory"

    def test_claude_config_dir_default(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        assert claude_config_dir() == Path.home() / ".claude"


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


class TestConfigMediumFixes:
    def test_tool_paths_expand_tilde(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        for var in ("REPOS_DIR", "TASKS_DIR", "TASKTREE_THEME", "EDITOR"):
            monkeypatch.delenv(var, raising=False)
        cfg_dir = tmp_path / "tasktree-manager"
        cfg_dir.mkdir()
        (cfg_dir / "config.toml").write_text('[tools]\nclaude_path = "~/.claude/local/claude"\n')
        config = Config.load()
        assert config.claude_path == str(tmp_path / "home" / ".claude" / "local" / "claude")

    def test_save_omits_default_blocklist(self, temp_dirs):
        repos_dir, tasks_dir = temp_dirs
        config_dir = repos_dir.parent / ".config" / "tasktree-manager"
        Config(repos_dir=repos_dir, tasks_dir=tasks_dir, config_dir=config_dir).save()
        text = (config_dir / "config.toml").read_text()
        assert "\nblocklist = " not in text
        assert "# blocklist = " in text

    def test_save_writes_custom_blocklist(self, temp_dirs):
        repos_dir, tasks_dir = temp_dirs
        config_dir = repos_dir.parent / ".config" / "tasktree-manager"
        custom = list(DEFAULT_SYMLINK_BLOCKLIST) + ["secrets/*"]
        Config(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=config_dir,
            symlink_blocklist=custom,
        ).save()
        assert '\nblocklist = ["*.pyc"' in (config_dir / "config.toml").read_text()

    def test_blocklist_scalar_falls_back_to_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        for var in ("REPOS_DIR", "TASKS_DIR", "TASKTREE_THEME", "EDITOR"):
            monkeypatch.delenv(var, raising=False)
        cfg_dir = tmp_path / "tasktree-manager"
        cfg_dir.mkdir()
        (cfg_dir / "config.toml").write_text('[symlinks]\nblocklist = "*.log"\n')
        assert Config.load().symlink_blocklist == DEFAULT_SYMLINK_BLOCKLIST

    async def test_readonly_config_does_not_crash_theme_switch(self, app, tmp_path):
        app.config.config_dir = tmp_path / "ro"
        app.config.config_dir.mkdir()
        app.config.config_dir.chmod(0o500)
        try:
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("t")
                await pilot.pause()
                assert app.is_running
        finally:
            app.config.config_dir.chmod(0o700)


# --------------------------------------------------------------------------
# app
# --------------------------------------------------------------------------


class TestPeriodicRefreshGuard:
    async def test_tick_skips_while_scan_running(self, app, sample_repo, task_manager, monkeypatch):
        _, branch = sample_repo
        task_manager.create_task("SLOW", ["sample-repo"], branch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            monkeypatch.setattr(app, "_worker_running", lambda group: group == "auto_refresh")
            started = []
            monkeypatch.setattr(app, "_run_periodic_refresh", lambda *a, **k: started.append(1))
            app._periodic_git_refresh()
            assert started == []


class TestDeleteTaskSafePath:
    async def test_safe_task_gets_plain_confirm(self, app, repo_with_origin, task_manager):
        base = repo_with_origin
        task_manager.create_task("SAFE-DEL", ["repo-remote"], base)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()
            confirm = [s for s in app.screen_stack if isinstance(s, ConfirmModal)]
            safe = [s for s in app.screen_stack if isinstance(s, SafeDeleteModal)]
            assert len(confirm) == 1 and safe == []

    async def test_merged_via_forge_note_in_confirm(
        self, app, squash_merged_task, task_manager, monkeypatch
    ):
        task, _base = squash_merged_task
        monkeypatch.setattr(forge.Forge, "enabled", True)
        monkeypatch.setattr(
            forge,
            "get_forge_status",
            lambda p, b, max_age=None: ForgeStatus(
                provider="gitlab", mr_state="merged", mr_ref="!7"
            ),
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()
            modal = app.screen_stack[-1]
            assert isinstance(modal, ConfirmModal)
            assert "Merged remotely" in modal.message_text


class TestCreateAndAddRepoHappyPath:
    async def test_create_via_modal(self, app, sample_repos, config):
        _, branch = sample_repos
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            modal = app.screen_stack[-1]
            assert isinstance(modal, CreateTaskModal)
            modal.query_one("#task-name", Input).value = "NEW-VIA-MODAL"
            modal.query_one("#base-branch", Input).value = branch
            modal.selected_repos = {"repo-alpha"}
            modal.query_one("#create-btn", Button).press()
            await app.workers.wait_for_complete()
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert (config.tasks_dir / "NEW-VIA-MODAL" / "repo-alpha" / ".git").exists()
            assert app.current_task and app.current_task.name == "NEW-VIA-MODAL"
            assert app.query_one("#task-list").loading is False

    async def test_add_repo_via_modal(self, app, sample_repos, task_manager, config):
        _, branch = sample_repos
        task_manager.create_task("ADD-VIA-MODAL", ["repo-alpha"], branch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            modal = app.screen_stack[-1]
            assert isinstance(modal, AddRepoModal)
            modal.query_one("#base-branch", Input).value = branch
            modal.selected_repos = {"repo-beta"}
            modal.query_one("#add-btn", Button).press()
            await app.workers.wait_for_complete()
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert (config.tasks_dir / "ADD-VIA-MODAL" / "repo-beta" / ".git").exists()


class TestSetupModalFixes:
    async def test_rejects_file_as_tasks_dir(self, app, tmp_path):
        repos = tmp_path / "wizard-repos"
        repos.mkdir()
        not_a_dir = tmp_path / "tasks-file"
        not_a_dir.write_text("x")
        async with app.run_test() as pilot:
            await pilot.pause()
            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()
            modal.query_one("#repos-dir", Input).value = str(repos)
            modal.query_one("#tasks-dir", Input).value = str(not_a_dir)
            modal._save_config()
            await pilot.pause()
            assert modal in app.screen_stack
            assert "not a directory" in modal.error_message

    async def test_fits_80x24(self, app):
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()
            save = modal.query_one("#save-btn", Button)
            assert save.region.y + save.region.height <= 24
            assert modal.query_one("#tasks-dir", Input).region.y < 24
