"""Regression tests for the review fixes around deletion safety, config
loading and keybinding installation."""

import subprocess

import pytest
from textual.widgets import Input

from tasktree_manager.app import TaskTreeApp
from tasktree_manager.cli import run_cli
from tasktree_manager.services.config import Config, ConfigError
from tasktree_manager.services.task_manager import TaskManager
from tasktree_manager.widgets.create_modal import (
    AddRepoModal,
    ConfirmModal,
    CreateTaskModal,
    SafeDeleteModal,
)
from tasktree_manager.widgets.setup_modal import SetupModal
from tasktree_manager.widgets.task_list import TaskList
from tasktree_manager.widgets.worktree_list import WorktreeList


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def isolated_config_home(tmp_path, monkeypatch):
    """Point XDG_CONFIG_HOME and HOME at tmp_path so Config.load() never
    touches the developer's real config, and clear the env overrides."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    for var in ("REPOS_DIR", "TASKS_DIR", "TASKTREE_THEME", "TASKTREE_DEFAULT_BRANCH", "EDITOR"):
        monkeypatch.delenv(var, raising=False)
    config_dir = tmp_path / "xdg" / "tasktree-manager"
    config_dir.mkdir(parents=True)
    return config_dir


class TestConfigEnvOverrides:
    def test_env_dirs_expand_tilde(self, isolated_config_home, tmp_path, monkeypatch):
        monkeypatch.setenv("REPOS_DIR", "~/my-repos")
        monkeypatch.setenv("TASKS_DIR", "~/my-tasks")
        config = Config.load()
        assert config.repos_dir == tmp_path / "home" / "my-repos"
        assert config.tasks_dir == tmp_path / "home" / "my-tasks"

    def test_empty_env_dir_is_ignored(self, isolated_config_home, tmp_path, monkeypatch):
        """Path("") is the CWD; an unset-but-exported variable must not turn
        the current directory into the tasks dir."""
        monkeypatch.setenv("TASKS_DIR", "")
        monkeypatch.setenv("REPOS_DIR", "")
        config = Config.load()
        assert config.tasks_dir == tmp_path / "home" / "tasks"
        assert config.repos_dir == tmp_path / "home" / "repos"

    def test_save_does_not_persist_env_overrides(self, isolated_config_home, tmp_path, monkeypatch):
        config_file = isolated_config_home / "config.toml"
        config_file.write_text(
            f'repos_dir = "{tmp_path / "file-repos"}"\n[ui]\ntheme = "tasktree"\n'
            '[tools]\neditor = ""\n'
        )
        monkeypatch.setenv("REPOS_DIR", str(tmp_path / "env-repos"))
        monkeypatch.setenv("TASKTREE_THEME", "nord")
        monkeypatch.setenv("EDITOR", "nvim")

        config = Config.load()
        assert config.repos_dir == tmp_path / "env-repos"
        assert config.theme == "nord"
        assert config.editor == "nvim"

        # What watch_theme does on every theme change
        config.theme = "gruvbox"
        config.save()

        for var in ("REPOS_DIR", "TASKTREE_THEME", "EDITOR"):
            monkeypatch.delenv(var)
        reloaded = Config.load()
        assert reloaded.repos_dir == tmp_path / "file-repos"
        assert reloaded.theme == "tasktree"
        assert reloaded.editor == ""

    def test_set_persistent_wins_over_env(self, isolated_config_home, tmp_path, monkeypatch):
        """The setup wizard must be able to persist a directory even when the
        session had an env override for it."""
        monkeypatch.setenv("REPOS_DIR", str(tmp_path / "env-repos"))
        config = Config.load()
        config.set_persistent("repos_dir", tmp_path / "wizard-repos")
        config.save()
        monkeypatch.delenv("REPOS_DIR")
        assert Config.load().repos_dir == tmp_path / "wizard-repos"

    def test_malformed_config_raises(self, isolated_config_home):
        (isolated_config_home / "config.toml").write_text('[keybindings]\nquit = "ctrl+q\n')
        with pytest.raises(ConfigError, match="Invalid config file"):
            Config.load()

    def test_cli_reports_malformed_config(self, isolated_config_home, capsys):
        (isolated_config_home / "config.toml").write_text("repos_dir = [\n")
        assert run_cli(["repos"]) == 1
        assert "Invalid config file" in capsys.readouterr().err


class TestCliDeleteArchives:
    def test_delete_force_writes_archive(self, config, repo_with_origin, capsys):
        base = repo_with_origin
        assert run_cli(["create", "task-a", "--repos", "repo-remote", "--base", base], config) == 0
        (config.tasks_dir / "task-a" / "repo-remote" / "wip.txt").write_text("wip\n")
        capsys.readouterr()

        assert run_cli(["delete", "task-a", "--force"], config) == 0
        out = capsys.readouterr().out
        assert "Archived diff to" in out
        patches = list(config.get_archive_dir().glob("task-a-*.patch"))
        assert len(patches) == 1
        assert "wip.txt" in patches[0].read_text()

    @pytest.mark.parametrize("name", ["..", ".", "/tmp"])
    def test_delete_rejects_unsafe_names(self, config, name, capsys):
        assert run_cli(["delete", name, "--force"], config) == 1
        assert "Task name" in capsys.readouterr().err
        assert config.tasks_dir.exists()


class TestBranchNameRefspecs:
    @pytest.mark.parametrize(
        "base",
        ["+refs/heads/main:refs/heads/develop", "main:develop", "a b", "x..y", "a@{1}", "-b"],
    )
    def test_refspec_like_base_rejected(self, task_manager, sample_repo, base):
        """`git fetch origin <base>` must only ever see a branch name: a
        src:dst refspec would rewrite a local branch in the main checkout."""
        with pytest.raises(ValueError, match="Branch name"):
            task_manager.create_task("REFSPEC", ["sample-repo"], base)

    @pytest.mark.parametrize("base", ["main", "release/1.0", "feature-x.y_z", "v2+build"])
    def test_ordinary_branch_names_accepted(self, base):
        from tasktree_manager.services.task_manager import validate_branch_name

        assert validate_branch_name(base) is None


class TestSafetyCheckTaskBranch:
    def test_detached_worktree_blocks_deletion(self, task_manager, repo_with_origin):
        """HEAD-based checks would call a detached worktree clean and merged
        while `git branch -D <task>` still deletes the branch's commits."""
        base = repo_with_origin
        task = task_manager.create_task("DETACHED", ["repo-remote"], base)
        wt = task.worktrees[0]
        (wt.path / "work.txt").write_text("work\n")
        _git(wt.path, "add", ".")
        _git(wt.path, "commit", "-q", "-m", "unpushed work")
        _git(wt.path, "checkout", "-q", "--detach", f"origin/{base}")

        report = task_manager.check_task_safety(task)
        assert not report.is_safe()
        assert report.errors and "not task branch 'DETACHED'" in report.errors[0].details


@pytest.fixture
def app_from_config(config, monkeypatch):
    """A TaskTreeApp whose __init__ sees the test config (so bindings are
    built from it), rather than the developer's real config file."""
    config.agent_poll_interval = 0
    config.forge_poll_interval = 0
    monkeypatch.setattr(Config, "load", classmethod(lambda cls: config))
    return lambda: TaskTreeApp()


class TestConfigKeybindingsInstalled:
    async def test_remapped_keys_are_live(self, app_from_config, config):
        config.keybindings["toggle_messages"] = "z"
        app = app_from_config()
        keys = app._bindings.key_to_bindings
        assert "z" in keys and "m" not in keys
        # Actions only present in the config-driven set must be app-level too
        assert "R" in keys and "b" in keys
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._show_messages_panel is False
            await pilot.press("z")
            await pilot.pause()
            assert app._show_messages_panel is True
            await pilot.press("m")
            await pilot.pause()
            assert app._show_messages_panel is True  # old key no longer bound


class TestDefaultBaseBranchInTui:
    async def test_modals_prefill_configured_base(self, app, sample_repo, task_manager):
        _, branch = sample_repo
        app.config.default_base_branch = "develop"
        task_manager.create_task("BASE-TASK", ["sample-repo"], branch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            modal = app.screen_stack[-1]
            assert isinstance(modal, CreateTaskModal)
            assert modal.query_one("#base-branch", Input).value == "develop"
            await pilot.press("escape")
            await pilot.pause()

            # add-repo needs a repo not yet in the task
            (app.config.repos_dir / "other-repo").mkdir()
            _git(app.config.repos_dir / "other-repo", "init", "-q")
            await pilot.press("a")
            await pilot.pause()
            modal = app.screen_stack[-1]
            assert isinstance(modal, AddRepoModal)
            assert modal.query_one("#base-branch", Input).value == "develop"


class TestWorktreeSelectionReset:
    async def test_empty_task_clears_current_worktree(self, app, sample_repo, task_manager, config):
        """Highlighting a task without worktrees must not leave the previous
        task's worktree selected: D would delete it under the wrong task."""
        _, branch = sample_repo
        task_a = task_manager.create_task("TASK-A", ["sample-repo"], branch)
        (config.tasks_dir / "TASK-B").mkdir()

        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.current_task and app.current_task.name == "TASK-A"
            assert app.current_worktree is not None

            await pilot.press("j")
            await pilot.pause()
            assert app.current_task.name == "TASK-B"
            assert app.current_worktree is None

            await pilot.press("D")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not any(isinstance(s, ConfirmModal) for s in app.screen_stack)
            assert task_a.worktrees[0].path.exists()


class TestDeleteWorktreeSafety:
    async def test_dirty_worktree_shows_safe_delete_modal(self, app, sample_repo, task_manager):
        _, branch = sample_repo
        task = task_manager.create_task("WT-DIRTY", ["sample-repo"], branch)
        wt = task.worktrees[0]
        (wt.path / "dirty.txt").write_text("x\n")

        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.current_worktree is not None
            await pilot.press("D")
            await app.workers.wait_for_complete()
            await pilot.pause()
            modal = app.screen_stack[-1]
            assert isinstance(modal, SafeDeleteModal)
            assert modal.safety_report.has_dirty()
            await pilot.press("escape")
            await pilot.pause()
            assert wt.path.exists()

    async def test_clean_worktree_confirms_then_removes(
        self, app, repo_with_origin, task_manager, config
    ):
        base = repo_with_origin
        task = task_manager.create_task("WT-CLEAN", ["repo-remote"], base)
        wt = task.worktrees[0]

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("D")
            await app.workers.wait_for_complete()
            await pilot.pause()
            modal = app.screen_stack[-1]
            assert isinstance(modal, ConfirmModal)
            modal.dismiss(True)
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not wt.path.exists()
            branches = subprocess.run(
                ["git", "branch", "--list", "WT-CLEAN"],
                cwd=config.repos_dir / "repo-remote",
                capture_output=True,
                text=True,
            ).stdout
            assert branches.strip() == ""


class TestMarkupSafeLabels:
    async def test_bracketed_alias_renders_verbatim(self, app, sample_repo, task_manager):
        _, branch = sample_repo
        task = task_manager.create_task("ALIAS-TASK", ["sample-repo"], branch)
        task_manager.set_task_display_name(task, "[WIP] fix login")
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert "[WIP] fix login" in str(task_list.get_option("ALIAS-TASK").prompt)

    async def test_bracketed_branch_renders_verbatim(self, app, sample_repo, task_manager):
        _, branch = sample_repo
        task = task_manager.create_task("BR-TASK", ["sample-repo"], branch)
        wt = task.worktrees[0]
        wt.branch = "[hotfix]"
        async with app.run_test() as pilot:
            await pilot.pause()
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            worktree_list.load_worktrees([wt])
            await pilot.pause()
            assert "[hotfix]" in str(worktree_list.get_option("sample-repo").prompt)


class TestSetupModalSeparateDirs:
    async def test_rejects_nested_or_equal_dirs(self, app, tmp_path):
        code = tmp_path / "code"
        code.mkdir()
        async with app.run_test() as pilot:
            await pilot.pause()
            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()
            modal.query_one("#repos-dir", Input).value = str(code)
            modal.query_one("#tasks-dir", Input).value = str(code / "tasks")
            modal._save_config()
            await pilot.pause()
            assert modal in app.screen_stack
            assert "separate" in modal.error_message


class TestTaskManagerWorktreeScan:
    def test_scan_stops_inside_worktree(self, task_manager, sample_repo):
        """A nested .git inside a worktree (submodule, vendored clone) is not
        a second worktree, and the walk must not descend into the checkout."""
        _, branch = sample_repo
        task = task_manager.create_task("SCAN-TASK", ["sample-repo"], branch)
        nested = task.worktrees[0].path / "vendored" / "lib"
        nested.mkdir(parents=True)
        _git(nested, "init", "-q")
        names = [wt.name for wt in TaskManager(task_manager.config).get_task("SCAN-TASK").worktrees]
        assert names == ["sample-repo"]
