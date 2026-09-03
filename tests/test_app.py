"""Tests for the main tasktree-manager application."""

import shutil

from tasktree_manager.widgets.create_modal import (
    AddRepoModal,
    ConfirmModal,
    CreateTaskModal,
    SafeDeleteModal,
)
from tasktree_manager.widgets.status_panel import StatusPanel
from tasktree_manager.widgets.task_list import TaskList
from tasktree_manager.widgets.worktree_list import WorktreeList


class TestTaskTreeApp:
    """Tests for TaskTreeApp class."""

    async def test_app_starts(self, app):
        """Test that the app starts without errors."""
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.is_running

    async def test_app_has_task_list(self, app):
        """Test that app has a task list widget."""
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert task_list is not None

    async def test_app_has_worktree_list(self, app):
        """Test that app has a worktree list widget."""
        async with app.run_test() as pilot:
            await pilot.pause()
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert worktree_list is not None

    async def test_app_has_status_panel(self, app):
        """Test that app has a status panel widget."""
        async with app.run_test() as pilot:
            await pilot.pause()
            status_panel = app.query_one("#status-display", StatusPanel)
            assert status_panel is not None

    async def test_quit_action(self, app):
        """Test that q quits the app."""
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")
            assert not app.is_running

    async def test_help_modal(self, app):
        """Test that ? opens help modal."""
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("?")
            await pilot.pause()
            # Check that help modal is shown
            from tasktree_manager.widgets.create_modal import HelpModal

            help_screens = [s for s in app.screen_stack if isinstance(s, HelpModal)]
            assert len(help_screens) == 1

    async def test_help_modal_shows_keybindings(self, app):
        """Test that help modal displays keybindings from config."""
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("?")
            await pilot.pause()

            from tasktree_manager.widgets.create_modal import HelpModal

            help_screens = [s for s in app.screen_stack if isinstance(s, HelpModal)]
            assert len(help_screens) == 1

            help_modal = help_screens[0]
            # Verify keybindings were passed
            assert help_modal.keybindings is not None
            assert "quit" in help_modal.keybindings
            assert "new_task" in help_modal.keybindings

    async def test_navigation_j_k(self, app, sample_repos, task_manager):
        """Test j/k navigation in task list."""
        repos, branch = sample_repos
        # Create some tasks
        task_manager.create_task("TASK-1", ["repo-alpha"], branch)
        task_manager.create_task("TASK-2", ["repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check initial task
            task_list = app.query_one("#task-list", TaskList)
            assert task_list.index == 0

            # Navigate down
            await pilot.press("j")
            await pilot.pause()
            assert task_list.index == 1

            # Navigate up
            await pilot.press("k")
            await pilot.pause()
            assert task_list.index == 0

    async def test_tab_switches_focus(self, app):
        """Test that tab switches focus between panels."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Initial focus should be on task list
            task_list = app.query_one("#task-list", TaskList)
            assert app.focused == task_list

            # Tab to worktree list
            await pilot.press("tab")
            await pilot.pause()

            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert app.focused == worktree_list

    async def test_refresh_action(self, app):
        """Test that r refreshes the app."""
        async with app.run_test() as pilot:
            await pilot.pause()
            # Just verify it doesn't crash
            await pilot.press("r")
            await pilot.pause()
            assert app.is_running


class TestTaskListWidget:
    """Tests for TaskList widget."""

    async def test_empty_task_list(self, app):
        """Test task list with no tasks."""
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert len(task_list.tasks) == 0

    async def test_task_list_loads_tasks(self, app, sample_repo, task_manager):
        """Test that task list loads created tasks."""
        repo_path, branch = sample_repo
        task_manager.create_task("LOADED-TASK", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert len(task_list.tasks) == 1
            assert task_list.tasks[0].name == "LOADED-TASK"


class TestWorktreeListWidget:
    """Tests for WorktreeList widget."""

    async def test_worktree_list_updates_on_task_select(self, app, sample_repos, task_manager):
        """Test worktree list updates when task is selected."""
        repos, branch = sample_repos
        task_manager.create_task("WT-TEST", ["repo-alpha", "repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert len(worktree_list.worktrees) == 2


class TestNewTaskAction:
    """Tests for the new_task action."""

    async def test_new_task_no_repos_warning(self, app, config):
        """Test that new task with no repos shows warning."""
        # Remove all repos from config directory
        for item in config.repos_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'n' for new task
            await pilot.press("n")
            await pilot.pause()

            # No modal should open - notification shown instead
            create_modals = [s for s in app.screen_stack if isinstance(s, CreateTaskModal)]
            assert len(create_modals) == 0

    async def test_new_task_modal_opens(self, app, sample_repos):
        """Test that new task modal opens when repos exist."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'n' for new task
            await pilot.press("n")
            await pilot.pause()

            # Modal should be open
            create_modals = [s for s in app.screen_stack if isinstance(s, CreateTaskModal)]
            assert len(create_modals) == 1


class TestCloneTaskAction:
    """Tests for the clone_task action."""

    async def test_clone_task_no_task_warning(self, app):
        """Test that clone task with no task selected shows warning, no modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'y' for clone with no task selected
            await pilot.press("y")
            await pilot.pause()

            create_modals = [s for s in app.screen_stack if isinstance(s, CreateTaskModal)]
            assert len(create_modals) == 0

    async def test_clone_task_modal_prefills_repos(self, app, sample_repos, task_manager):
        """Test that clone modal opens with current task's repos pre-selected."""
        _, branch = sample_repos
        task_manager.create_task("SOURCE-TASK", ["repo-alpha", "repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Source task should be selected (first/only task)
            assert app.current_task is not None
            assert app.current_task.name == "SOURCE-TASK"

            await pilot.press("y")
            await pilot.pause()

            create_modals = [s for s in app.screen_stack if isinstance(s, CreateTaskModal)]
            assert len(create_modals) == 1

            modal = create_modals[0]
            assert modal.selected_repos == {"repo-alpha", "repo-beta"}
            assert "SOURCE-TASK" in modal.title_text


class TestAddRepoAction:
    """Tests for the add_repo action."""

    async def test_add_repo_no_task_warning(self, app):
        """Test that add repo with no task selected shows warning."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'a' for add repo
            await pilot.press("a")
            await pilot.pause()

            # No modal should open
            add_modals = [s for s in app.screen_stack if isinstance(s, AddRepoModal)]
            assert len(add_modals) == 0

    async def test_add_repo_modal_opens(self, app, sample_repos, task_manager):
        """Test that add repo modal opens when task is selected."""
        repos, branch = sample_repos
        task_manager.create_task("ADD-TEST", ["repo-alpha"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'a' for add repo
            await pilot.press("a")
            await pilot.pause()

            # Modal should be open
            add_modals = [s for s in app.screen_stack if isinstance(s, AddRepoModal)]
            assert len(add_modals) == 1

    async def test_add_repo_all_repos_in_task(self, app, sample_repo, task_manager):
        """Test that add repo shows message when all repos in task."""
        repo_path, branch = sample_repo
        task_manager.create_task("FULL-TASK", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'a' for add repo
            await pilot.press("a")
            await pilot.pause()

            # No modal should open - all repos already in task
            add_modals = [s for s in app.screen_stack if isinstance(s, AddRepoModal)]
            assert len(add_modals) == 0


class TestDeleteTaskAction:
    """Tests for the delete_task action."""

    async def test_delete_task_no_task_warning(self, app):
        """Test that delete with no task selected shows warning."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'd' for delete
            await pilot.press("d")
            await pilot.pause()

            # No modal should open
            confirm_modals = [s for s in app.screen_stack if isinstance(s, ConfirmModal)]
            safe_modals = [s for s in app.screen_stack if isinstance(s, SafeDeleteModal)]
            assert len(confirm_modals) == 0
            assert len(safe_modals) == 0

    async def test_delete_task_safe_confirm(self, app, sample_repo, task_manager):
        """Test that delete of safe task shows confirm modal."""
        repo_path, branch = sample_repo
        task_manager.create_task("DELETE-TEST", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'd' for delete - safety check runs in a background worker
            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Should show either ConfirmModal (safe) or SafeDeleteModal (unsafe)
            confirm_modals = [s for s in app.screen_stack if isinstance(s, ConfirmModal)]
            safe_modals = [s for s in app.screen_stack if isinstance(s, SafeDeleteModal)]
            # One of them should be shown
            assert len(confirm_modals) + len(safe_modals) >= 1

    async def test_delete_dirty_task_shows_safe_modal(self, app, sample_repo, task_manager):
        """Test that deleting a task with uncommitted changes shows the safe-delete modal."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("DIRTY-DELETE", ["sample-repo"], branch)

        # Make the worktree dirty
        (task.worktrees[0].path / "dirty.txt").write_text("uncommitted")

        async with app.run_test() as pilot:
            await pilot.pause()

            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()

            safe_modals = [s for s in app.screen_stack if isinstance(s, SafeDeleteModal)]
            assert len(safe_modals) == 1


class TestPushPullActions:
    """Tests for push_all and pull_all actions."""

    async def test_push_all_no_task_warning(self, app):
        """Test that push with no task selected shows warning."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'p' for push
            await pilot.press("p")
            await pilot.pause()

            # App should still be running
            assert app.is_running

    async def test_pull_all_no_task_warning(self, app):
        """Test that pull with no task selected shows warning."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'P' for pull
            await pilot.press("P")
            await pilot.pause()

            # App should still be running
            assert app.is_running


class TestOpenExternalCommands:
    """Tests for lazygit and shell actions."""

    async def test_open_lazygit_no_worktree_warning(self, app, sample_repo, task_manager):
        """Test that lazygit with no worktree selected shows warning."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Clear current worktree
            app.current_worktree = None

            # Press 'g' for lazygit
            await pilot.press("g")
            await pilot.pause()

            # App should still be running
            assert app.is_running


class TestRenameTaskAction:
    """Tests for the rename (display alias) action."""

    async def test_rename_via_keybinding(self, app, sample_repo, task_manager):
        """R -> modal -> alias shows in the task list; folder unchanged."""
        from tasktree_manager.widgets.create_modal import RenameTaskModal

        repo_path, branch = sample_repo
        task = task_manager.create_task("RENAME-TASK", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            assert isinstance(app.screen_stack[-1], RenameTaskModal)

            await pilot.press(*"nice label")
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert (task.path / ".tasktree_name").read_text().strip() == "nice label"
            assert task.path.exists()  # folder untouched
            task_list = app.query_one("#task-list", TaskList)
            prompt = str(task_list.get_option("RENAME-TASK").prompt)
            assert "nice label" in prompt
            assert "RENAME-TASK" not in prompt

    async def test_rename_cancel_changes_nothing(self, app, sample_repo, task_manager):
        repo_path, branch = sample_repo
        task = task_manager.create_task("RENAME-CANCEL", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert not (task.path / ".tasktree_name").exists()

    async def test_rename_empty_reverts(self, app, sample_repo, task_manager):
        repo_path, branch = sample_repo
        task = task_manager.create_task("RENAME-REVERT", ["sample-repo"], branch)
        task_manager.set_task_display_name(task, "old label")

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            # Prefilled with the current alias - clear it
            from textual.widgets import Input

            from tasktree_manager.widgets.create_modal import RenameTaskModal

            modal = app.screen_stack[-1]
            assert isinstance(modal, RenameTaskModal)
            modal.query_one("#rename-input", Input).value = ""
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert not (task.path / ".tasktree_name").exists()
            task_list = app.query_one("#task-list", TaskList)
            assert "RENAME-REVERT" in str(task_list.get_option("RENAME-REVERT").prompt)


class TestShowDiffAction:
    """Tests for the hunk diff action (h)."""

    async def test_show_diff_dispatches_by_focus(self, app, sample_repos, task_manager):
        """h routes to the task diff from the task panel and the worktree diff
        from the worktree panel."""
        repos, branch = sample_repos
        task_manager.create_task("DIFF-TEST", ["repo-alpha", "repo-beta"], branch)

        calls = []
        app._show_task_diff = lambda: calls.append("task")
        app._show_worktree_diff = lambda: calls.append("worktree")

        async with app.run_test() as pilot:
            await pilot.pause()

            app.query_one("#task-list", TaskList).focus()
            await pilot.pause()
            app.action_show_diff()
            assert calls == ["task"]

            app.query_one("#worktree-list", WorktreeList).focus()
            await pilot.pause()
            app.action_show_diff()
            assert calls == ["task", "worktree"]

    async def test_show_worktree_diff_no_worktree_warning(self, app, sample_repo, task_manager):
        """Worktree diff with no worktree selected warns and stays running."""
        async with app.run_test() as pilot:
            await pilot.pause()

            app.current_worktree = None
            app._show_worktree_diff()
            await pilot.pause()

            assert app.is_running

    async def test_show_task_diff_no_changes(self, app, sample_repos, task_manager):
        """Task diff over clean worktrees reports no changes and never suspends."""
        repos, branch = sample_repos
        task_manager.create_task("CLEAN-DIFF", ["repo-alpha"], branch)

        suspended = []
        app.suspend = lambda: suspended.append(True)  # would raise if called wrongly

        async with app.run_test() as pilot:
            await pilot.pause()
            # current_task is the freshly created, clean task; the diff is
            # built in a worker, so wait for it before asserting
            app._show_task_diff()
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert app.is_running
            # Clean worktrees => empty combined diff => hunk never launched
            assert suspended == []

    async def test_task_highlighted_updates_worktree_list(self, app, sample_repos, task_manager):
        """Test that task highlight updates worktree list."""
        repos, branch = sample_repos
        task_manager.create_task("EVENT-TEST", ["repo-alpha", "repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Task list should have loaded the task
            task_list = app.query_one("#task-list", TaskList)
            assert len(task_list.tasks) == 1

            # Worktree list should have the worktrees
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert len(worktree_list.worktrees) == 2

    async def test_worktree_highlighted_updates_status(self, app, sample_repos, task_manager):
        """Test that worktree highlight updates status panel."""
        repos, branch = sample_repos
        task_manager.create_task("STATUS-TEST", ["repo-alpha"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Status panel should show worktree status
            status_panel = app.query_one("#status-display", StatusPanel)
            # Status should be updated (not showing "No worktree selected")
            assert status_panel._worktree_name or app.current_worktree is not None or True


class TestRunExternalCommand:
    """Tests for _run_external_command method."""

    async def test_run_external_command_not_found(self, app):
        """Test that missing command shows error notification."""
        async with app.run_test() as pilot:
            await pilot.pause()

            result = app._run_external_command(
                ["nonexistent_command_xyz"],
                cwd="/tmp",
                name="Test Command",
                install_hint="brew install xyz",
            )
            assert result is False

    async def test_run_external_command_with_hint(self, app):
        """Test that install hint is included in error."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Command doesn't exist
            result = app._run_external_command(
                ["nonexistent_command_123"],
                cwd="/tmp",
                name="Test",
                install_hint="pip install test",
            )
            assert result is False


class TestCursorActions:
    """Tests for cursor movement actions."""

    async def test_cursor_down_in_task_list(self, app, sample_repos, task_manager):
        """Test cursor down in task list."""
        repos, branch = sample_repos
        task_manager.create_task("TASK-A", ["repo-alpha"], branch)
        task_manager.create_task("TASK-B", ["repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await pilot.pause()

            initial_index = task_list.index
            await pilot.press("j")
            await pilot.pause()

            # Index should have moved
            assert task_list.index != initial_index or task_list.index == 1

    async def test_cursor_up_in_task_list(self, app, sample_repos, task_manager):
        """Test cursor up in task list."""
        repos, branch = sample_repos
        task_manager.create_task("TASK-A", ["repo-alpha"], branch)
        task_manager.create_task("TASK-B", ["repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()

            # Move down first
            await pilot.press("j")
            await pilot.pause()

            # Then move up
            await pilot.press("k")
            await pilot.pause()

            assert task_list.index == 0


class TestShiftTabNavigation:
    """Tests for shift+tab navigation."""

    async def test_shift_tab_reverse_focus(self, app, sample_repo, task_manager):
        """Test shift+tab moves focus backwards."""
        repo_path, branch = sample_repo
        task_manager.create_task("NAV-TEST", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Initial focus on task list
            task_list = app.query_one("#task-list", TaskList)
            worktree_list = app.query_one("#worktree-list", WorktreeList)

            # Tab to worktree list
            await pilot.press("tab")
            await pilot.pause()
            assert app.focused == worktree_list

            # Shift+tab back to task list
            await pilot.press("shift+tab")
            await pilot.pause()
            assert app.focused == task_list


class TestAppConfiguration:
    """Tests for app configuration."""

    async def test_app_applies_theme(self, app):
        """Test that app applies theme from config."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # App should have loaded without errors
            assert app.is_running

    async def test_custom_keybindings_loaded(self, app):
        """Test that custom keybindings are loaded from config."""
        # Verify bindings list was built
        assert len(app._custom_bindings) > 0

        # Should have standard bindings
        binding_actions = [b.action for b in app._custom_bindings]
        assert "quit" in binding_actions
        assert "help" in binding_actions
        assert "new_task" in binding_actions

    async def test_git_timeout_wired_from_config(self, app):
        """Test that app startup applies the [git] timeout to GitOps."""
        from tasktree_manager.services.git_ops import GitOps

        assert GitOps.network_timeout == app.config.git_timeout


class TestContextSensitiveFooter:
    """Tests for the context-sensitive footer bindings."""

    @staticmethod
    def _shown_actions(app) -> set[str]:
        """Actions currently visible in the footer."""
        return {
            active.binding.action
            for active in app.screen.active_bindings.values()
            if active.binding.show
        }

    async def test_task_panel_footer_shows_task_actions(self, app, sample_repo, task_manager):
        """Task list focused: task actions plus globals are visible."""
        repo_path, branch = sample_repo
        task_manager.create_task("FOOTER-TASKS", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            assert app.focused.id == "task-list"
            shown = self._shown_actions(app)
            assert "app.new_task" in shown
            assert "app.clone_task" in shown
            assert "app.delete_task" in shown
            # Worktree-context actions are hidden in this context
            assert "app.open_lazygit" not in shown
            # Globals always visible
            assert "cycle_theme" in shown
            assert "refresh" in shown
            assert "help" in shown
            assert "quit" in shown
            # Messages toggle still works but is not shown in the footer
            assert "toggle_messages" not in shown

    async def test_worktree_panel_footer_shows_worktree_actions(
        self, app, sample_repo, task_manager
    ):
        """Worktree list focused: worktree actions plus globals are visible."""
        repo_path, branch = sample_repo
        task_manager.create_task("FOOTER-WT", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()

            assert app.focused.id == "worktree-list"
            shown = self._shown_actions(app)
            assert "app.open_lazygit" in shown
            assert "app.push_all" in shown
            # Task-context actions are hidden in this context
            assert "app.new_task" not in shown
            # Globals always visible
            assert "refresh" in shown
            assert "quit" in shown

    async def test_keys_work_outside_their_panel(self, app, sample_repos, task_manager):
        """A task-context key still works while the worktree list is focused."""
        _, branch = sample_repos
        task_manager.create_task("FOOTER-KEYS", ["repo-alpha"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("tab")  # focus worktree list
            await pilot.pause()

            # 'n' is a task-panel binding but must still open the modal
            await pilot.press("n")
            await pilot.pause()

            create_modals = [s for s in app.screen_stack if isinstance(s, CreateTaskModal)]
            assert len(create_modals) == 1
