"""Tests for Claude Code hook and settings configuration."""

import json
from pathlib import Path

from tasktree_manager.services.claude_hooks import (
    ensure_claude_hooks,
    ensure_worktree_claude_settings,
    has_claude_session,
    repo_memory_dir,
)


class TestEnsureClaudeHooks:
    """Tests for ensure_claude_hooks."""

    def test_creates_settings_with_hooks(self, tmp_path):
        """Test that settings.local.json is created with status hooks."""
        ensure_claude_hooks(tmp_path)

        settings_file = tmp_path / ".claude" / "settings.local.json"
        assert settings_file.exists()

        settings = json.loads(settings_file.read_text())
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            assert event in settings["hooks"]
        assert str(tmp_path / ".claude_status") in json.dumps(settings["hooks"])

    def test_no_memory_dir_by_default(self, tmp_path):
        """Test that autoMemoryDirectory is not written when memory_dir is empty."""
        ensure_claude_hooks(tmp_path)

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        assert "autoMemoryDirectory" not in settings

    def test_memory_dir_written_expanded(self, tmp_path):
        """Test that memory_dir is written as an expanded absolute path."""
        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        assert settings["autoMemoryDirectory"] == str(Path.home() / ".claude" / "tasktree-memory")

    def test_preserves_existing_settings(self, tmp_path):
        """Test that unrelated existing settings keys survive a rewrite."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}))

        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings = json.loads(settings_file.read_text())
        assert settings["permissions"] == {"allow": ["Bash(ls *)"]}
        assert "hooks" in settings
        assert "autoMemoryDirectory" in settings

    def test_empty_memory_dir_leaves_existing_value(self, tmp_path):
        """Test that an existing autoMemoryDirectory is kept when memory_dir is empty."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text(json.dumps({"autoMemoryDirectory": "/custom/memory"}))

        ensure_claude_hooks(tmp_path, "")

        settings = json.loads(settings_file.read_text())
        assert settings["autoMemoryDirectory"] == "/custom/memory"

    def test_memory_dir_overrides_existing_value(self, tmp_path):
        """Test that a configured memory_dir replaces a previously written one."""
        ensure_claude_hooks(tmp_path, "/old/memory")
        ensure_claude_hooks(tmp_path, "/new/memory")

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        assert settings["autoMemoryDirectory"] == "/new/memory"

    def test_recovers_from_corrupt_settings(self, tmp_path):
        """Invalid JSON is moved aside (it may hold the user's permissions),
        then a fresh settings file is written."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text("{not json")

        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings = json.loads(settings_file.read_text())
        assert "hooks" in settings
        assert "autoMemoryDirectory" in settings
        backups = list(claude_dir.glob("settings.local.json.broken-*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "{not json"

    def test_preserves_user_hooks(self, tmp_path):
        """User-written hook groups survive: settings.local.json holds
        executable config the user may have added by hand."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        user_stop_hook = {"hooks": [{"type": "command", "command": "echo user-stop"}]}
        user_post_tool = {"hooks": [{"type": "command", "command": "echo post-tool"}]}
        settings_file.write_text(
            json.dumps({"hooks": {"Stop": [user_stop_hook], "PostToolUse": [user_post_tool]}})
        )

        ensure_claude_hooks(tmp_path)

        settings = json.loads(settings_file.read_text())
        # Untouched event survives entirely
        assert settings["hooks"]["PostToolUse"] == [user_post_tool]
        # Shared event keeps the user group and gains the tasktree group
        stop_commands = json.dumps(settings["hooks"]["Stop"])
        assert "echo user-stop" in stop_commands
        assert ".claude_status" in stop_commands

    def test_rerun_does_not_duplicate_hooks(self, tmp_path):
        """Repeated calls replace tasktree's own groups instead of stacking."""
        ensure_claude_hooks(tmp_path)
        ensure_claude_hooks(tmp_path)

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            assert len(settings["hooks"][event]) == 1

    def test_tolerates_non_string_hook_command(self, tmp_path):
        """A user hook whose command is not a string must not crash merging."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        weird_group = {"hooks": [{"type": "command", "command": None}]}
        settings_file.write_text(json.dumps({"hooks": {"Stop": [weird_group]}}))

        ensure_claude_hooks(tmp_path)

        settings = json.loads(settings_file.read_text())
        # The malformed group is treated as user-owned and preserved
        assert weird_group in settings["hooks"]["Stop"]
        assert ".claude_status" in json.dumps(settings["hooks"]["Stop"])


class TestRepoMemoryDir:
    """Tests for repo_memory_dir."""

    def test_encodes_repo_path(self, tmp_path, monkeypatch):
        """Test that the repo path is encoded like Claude project dirs."""
        monkeypatch.setenv("HOME", str(tmp_path))
        result = repo_memory_dir(Path("/repos/work.3"))
        assert result == tmp_path / ".claude" / "projects" / "-repos-work-3" / "memory"


class TestEnsureWorktreeClaudeSettings:
    """Tests for ensure_worktree_claude_settings."""

    @staticmethod
    def _make_repo_and_worktree(tmp_path):
        repo_path = tmp_path / "repos" / "work3"
        (repo_path / ".git" / "info").mkdir(parents=True)
        worktree_path = tmp_path / "tasks" / "TASK-1" / "work3"
        worktree_path.mkdir(parents=True)
        status_file = tmp_path / "tasks" / "TASK-1" / ".claude_status"
        return repo_path, worktree_path, status_file

    def test_points_memory_at_repo(self, tmp_path, monkeypatch):
        """Test that autoMemoryDirectory targets the main repo's memory dir."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        settings = json.loads((worktree_path / ".claude" / "settings.local.json").read_text())
        assert settings["autoMemoryDirectory"] == str(repo_memory_dir(repo_path))

    def test_writes_status_hooks(self, tmp_path, monkeypatch):
        """Test that status hooks write to the task's status file."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        settings = json.loads((worktree_path / ".claude" / "settings.local.json").read_text())
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            assert event in settings["hooks"]
        assert str(status_file) in json.dumps(settings["hooks"])

    def test_preserves_existing_settings(self, tmp_path, monkeypatch):
        """Test that unrelated existing settings keys survive a rewrite."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)
        claude_dir = worktree_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}))

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        settings = json.loads(settings_file.read_text())
        assert settings["permissions"] == {"allow": ["Bash(ls *)"]}
        assert "autoMemoryDirectory" in settings

    def test_excludes_settings_from_git(self, tmp_path, monkeypatch):
        """Test that the settings file is added to the repo's git exclude."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        exclude = (repo_path / ".git" / "info" / "exclude").read_text()
        assert ".claude/settings.local.json" in exclude

    def test_exclude_entry_is_idempotent(self, tmp_path, monkeypatch):
        """Test that repeated calls do not duplicate the exclude entry."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)
        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        lines = (repo_path / ".git" / "info" / "exclude").read_text().splitlines()
        assert lines.count(".claude/settings.local.json") == 1

    def test_preserves_user_hooks(self, tmp_path, monkeypatch):
        """User-written hook groups in a worktree's settings survive, and
        reruns do not stack duplicate tasktree groups."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)
        claude_dir = worktree_path / ".claude"
        claude_dir.mkdir()
        user_stop_hook = {"hooks": [{"type": "command", "command": "echo user-stop"}]}
        (claude_dir / "settings.local.json").write_text(
            json.dumps({"hooks": {"Stop": [user_stop_hook]}})
        )

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)
        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        settings = json.loads((claude_dir / "settings.local.json").read_text())
        stop_groups = settings["hooks"]["Stop"]
        assert user_stop_hook in stop_groups
        assert len(stop_groups) == 2  # user group + one tasktree group, no dupes

    def test_git_file_instead_of_dir(self, tmp_path, monkeypatch):
        """Test that a .git file (linked worktree/submodule) is skipped safely."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path = tmp_path / "repos" / "work3"
        repo_path.mkdir(parents=True)
        (repo_path / ".git").write_text("gitdir: /elsewhere\n")
        worktree_path = tmp_path / "tasks" / "TASK-1" / "work3"
        worktree_path.mkdir(parents=True)

        ensure_worktree_claude_settings(
            worktree_path, repo_path, tmp_path / "tasks" / "TASK-1" / ".claude_status"
        )

        assert (worktree_path / ".claude" / "settings.local.json").exists()


class TestHasClaudeSession:
    """Tests for has_claude_session."""

    def test_no_project_dir(self, tmp_path, monkeypatch):
        """Test False when no project directory exists."""
        monkeypatch.setenv("HOME", str(tmp_path))
        assert has_claude_session(Path("/some/task")) is False

    def test_project_dir_with_transcript(self, tmp_path, monkeypatch):
        """Test True when the encoded project directory holds a transcript."""
        monkeypatch.setenv("HOME", str(tmp_path))
        task_path = Path("/some/task.dir")
        encoded = "-some-task-dir"
        project_dir = tmp_path / ".claude" / "projects" / encoded
        project_dir.mkdir(parents=True)
        (project_dir / "abc.jsonl").touch()

        assert has_claude_session(task_path) is True
