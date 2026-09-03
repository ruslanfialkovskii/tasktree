"""Tests for the task manager service."""

import subprocess

import pytest

from tasktree_manager.services.task_manager import RepoIssue, Task, TaskSafetyReport, Worktree


class TestTaskManager:
    """Tests for TaskManager class."""

    def test_list_tasks_empty(self, task_manager):
        """Test listing tasks when none exist."""
        tasks = task_manager.list_tasks()
        assert tasks == []

    def test_create_task(self, task_manager, sample_repo):
        """Test creating a new task."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("TEST-123", ["sample-repo"], branch)

        assert task.name == "TEST-123"
        assert task.path.exists()
        assert len(task.worktrees) == 1
        assert task.worktrees[0].name == "sample-repo"
        assert task.worktrees[0].path.exists()

    def test_create_task_multiple_repos(self, task_manager, sample_repos):
        """Test creating a task with multiple repos."""
        repos, branch = sample_repos
        task = task_manager.create_task("MULTI-REPO", ["repo-alpha", "repo-beta"], branch)

        assert task.name == "MULTI-REPO"
        assert len(task.worktrees) == 2
        worktree_names = [wt.name for wt in task.worktrees]
        assert "repo-alpha" in worktree_names
        assert "repo-beta" in worktree_names

    def test_list_tasks_after_create(self, task_manager, sample_repo):
        """Test listing tasks after creation."""
        repo_path, branch = sample_repo
        task_manager.create_task("TASK-1", ["sample-repo"], branch)

        tasks = task_manager.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "TASK-1"

    def test_get_task(self, task_manager, sample_repo):
        """Test getting a specific task."""
        repo_path, branch = sample_repo
        task_manager.create_task("GET-TEST", ["sample-repo"], branch)

        task = task_manager.get_task("GET-TEST")
        assert task is not None
        assert task.name == "GET-TEST"

    def test_get_task_nonexistent(self, task_manager):
        """Test getting a task that doesn't exist."""
        task = task_manager.get_task("NONEXISTENT")
        assert task is None

    def test_add_repo_to_task(self, task_manager, sample_repos):
        """Test adding a repo to an existing task."""
        repos, branch = sample_repos
        task = task_manager.create_task("ADD-REPO", ["repo-alpha"], branch)
        assert len(task.worktrees) == 1

        task_manager.add_repo_to_task(task, "repo-beta", branch)
        assert len(task.worktrees) == 2

    def test_finish_task(self, task_manager, sample_repo):
        """Test finishing/deleting a task."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("FINISH-ME", ["sample-repo"], branch)
        task_path = task.path
        assert task_path.exists()

        task_manager.finish_task(task)
        assert not task_path.exists()

    def test_get_repos_not_in_task(self, task_manager, sample_repos):
        """Test getting repos not yet in a task."""
        repos, branch = sample_repos
        task = task_manager.create_task("PARTIAL", ["repo-alpha"], branch)

        available = task_manager.get_repos_not_in_task(task)
        assert "repo-alpha" not in available
        assert "repo-beta" in available
        assert "repo-gamma" in available

    def test_create_task_nonexistent_repo(self, task_manager):
        """Test creating a task with a nonexistent repo."""
        with pytest.raises(ValueError, match="Repository not found"):
            task_manager.create_task("FAIL-TASK", ["nonexistent-repo"], "main")


class TestTaskNameValidation:
    """Tests for task name safety validation."""

    @pytest.mark.parametrize(
        "name",
        [
            ".",
            "..",
            "../evil",
            "../../repos/x",
            "a/../b",
            "a/./b",
            "/absolute",
            "a//b",
            "trailing/",
        ],
    )
    def test_rejects_traversal_names(self, task_manager, name):
        """Names with '..', '.' or any path separator must be rejected.

        A task path is rmtree'd on finish, so '..' would delete outside
        TASKS_DIR.
        """
        with pytest.raises(ValueError):
            task_manager.create_task(name, [], "main")

    @pytest.mark.parametrize("name", ["feat/x", "team/DIC-1813"])
    def test_rejects_slash_names(self, task_manager, name):
        """A task is one directory level: list_tasks() would surface 'feat/x'
        as task 'feat' with the wrong branch name, and deleting that would
        leave the real branches behind."""
        with pytest.raises(ValueError, match="can only contain"):
            task_manager.create_task(name, [], "main")

    @pytest.mark.parametrize("name", ["", ".", "..", "../evil", "/absolute", "feat/x"])
    def test_get_task_rejects_unsafe_names(self, task_manager, name):
        """get_task() feeds CLI delete/finish, which rmtree the returned path:
        '' and '.' would resolve to TASKS_DIR itself, '..' to its parent."""
        with pytest.raises(ValueError):
            task_manager.get_task(name)

    def test_rejects_leading_dash(self, task_manager):
        """Names starting with '-' (git-option lookalikes) are rejected."""
        with pytest.raises(ValueError, match="cannot start with '-'"):
            task_manager.create_task("-rf", [], "main")

    def test_rejects_invalid_characters(self, task_manager):
        """Names with markup/shell-significant characters are rejected."""
        with pytest.raises(ValueError, match="can only contain"):
            task_manager.create_task("bad name[1]", [], "main")

    def test_accepts_normal_names(self, task_manager, sample_repo):
        """Ordinary ticket-style names still work."""
        _, branch = sample_repo
        task = task_manager.create_task("DIC-1813.hotfix_v2", ["sample-repo"], branch)
        assert task.path.exists()


class TestBranchNameValidation:
    """Tests for base branch safety validation."""

    def test_rejects_option_like_branch(self, task_manager, sample_repo):
        """A base branch starting with '-' would be parsed as a git option
        (e.g. --upload-pack=<command>), so it must be rejected."""
        _, _branch = sample_repo
        with pytest.raises(ValueError, match="Branch name"):
            task_manager.create_task("INJ-TEST", ["sample-repo"], "--upload-pack=/bin/true")

    def test_rejects_option_like_branch_on_add(self, task_manager, sample_repos):
        """The same validation applies when adding a repo to a task."""
        _, branch = sample_repos
        task = task_manager.create_task("INJ-ADD", ["repo-alpha"], branch)
        with pytest.raises(ValueError, match="Branch name"):
            task_manager.add_repo_to_task(task, "repo-beta", "-b")


class TestTask:
    """Tests for Task dataclass."""

    def test_is_dirty_clean(self):
        """Test is_dirty when all worktrees are clean."""
        task = Task(
            name="test",
            path=None,
            worktrees=[
                Worktree(name="a", path=None, is_dirty=False),
                Worktree(name="b", path=None, is_dirty=False),
            ],
        )
        assert not task.is_dirty

    def test_is_dirty_with_dirty_worktree(self):
        """Test is_dirty when some worktrees are dirty."""
        task = Task(
            name="test",
            path=None,
            worktrees=[
                Worktree(name="a", path=None, is_dirty=False),
                Worktree(name="b", path=None, is_dirty=True),
            ],
        )
        assert task.is_dirty

    def test_dirty_count(self):
        """Test dirty_count property."""
        task = Task(
            name="test",
            path=None,
            worktrees=[
                Worktree(name="a", path=None, is_dirty=True),
                Worktree(name="b", path=None, is_dirty=False),
                Worktree(name="c", path=None, is_dirty=True),
            ],
        )
        assert task.dirty_count == 2


class TestWorktree:
    """Tests for Worktree dataclass."""

    def test_exists_false(self, tmp_path):
        """Test exists property when path doesn't exist."""
        wt = Worktree(name="test", path=tmp_path / "nonexistent")
        assert not wt.exists

    def test_exists_true(self, tmp_path):
        """Test exists property when path exists."""
        path = tmp_path / "exists"
        path.mkdir()
        wt = Worktree(name="test", path=path)
        assert wt.exists

    def test_default_values(self, tmp_path):
        """Test default values for worktree."""
        wt = Worktree(name="test", path=tmp_path)
        assert wt.branch == ""
        assert not wt.is_dirty
        assert wt.changed_files == 0


class TestTaskSafetyReport:
    """Tests for TaskSafetyReport dataclass."""

    def test_is_safe_true(self):
        """Test is_safe returns True when no issues."""
        report = TaskSafetyReport()
        assert report.is_safe()

    def test_is_safe_false_unpushed(self, tmp_path):
        """Test is_safe returns False with unpushed commits."""
        report = TaskSafetyReport(
            unpushed=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="unpushed",
                    details="2 commits ahead",
                )
            ]
        )
        assert not report.is_safe()

    def test_is_safe_false_dirty(self, tmp_path):
        """Test is_safe returns False with dirty worktree."""
        report = TaskSafetyReport(
            dirty=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="dirty",
                    details="3 files changed",
                )
            ]
        )
        assert not report.is_safe()

    def test_is_safe_false_unmerged(self, tmp_path):
        """Test is_safe returns False with unmerged branch."""
        report = TaskSafetyReport(
            unmerged=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="unmerged",
                    details="not merged to main",
                )
            ]
        )
        assert not report.is_safe()

    def test_has_unpushed(self, tmp_path):
        """Test has_unpushed method."""
        empty = TaskSafetyReport()
        assert not empty.has_unpushed()

        with_unpushed = TaskSafetyReport(
            unpushed=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="unpushed",
                    details="1 commit",
                )
            ]
        )
        assert with_unpushed.has_unpushed()

    def test_has_dirty(self, tmp_path):
        """Test has_dirty method."""
        empty = TaskSafetyReport()
        assert not empty.has_dirty()

        with_dirty = TaskSafetyReport(
            dirty=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="dirty",
                    details="1 file",
                )
            ]
        )
        assert with_dirty.has_dirty()

    def test_has_unmerged(self, tmp_path):
        """Test has_unmerged method."""
        empty = TaskSafetyReport()
        assert not empty.has_unmerged()

        with_unmerged = TaskSafetyReport(
            unmerged=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="unmerged",
                    details="not merged",
                )
            ]
        )
        assert with_unmerged.has_unmerged()


class TestRepoIssue:
    """Tests for RepoIssue dataclass."""

    def test_create_repo_issue(self, tmp_path):
        """Test creating a RepoIssue."""
        issue = RepoIssue(
            repo_name="my-repo",
            worktree_path=tmp_path / "my-repo",
            issue_type="unpushed",
            details="5 commits ahead",
        )
        assert issue.repo_name == "my-repo"
        assert issue.issue_type == "unpushed"
        assert "5 commits" in issue.details


class TestSafetyChecks:
    """Tests for safety check methods in TaskManager."""

    def test_check_task_safety_clean(self, task_manager, sample_repo):
        """Test check_task_safety on clean task."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("CLEAN-TASK", ["sample-repo"], branch)

        report = task_manager.check_task_safety(task)

        # Clean task should be safe (though may have unmerged)
        # Just check that it returns a valid report
        assert isinstance(report, TaskSafetyReport)

    def test_check_task_safety_dirty_worktree(self, task_manager, sample_repo):
        """Test check_task_safety with dirty worktree."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("DIRTY-TASK", ["sample-repo"], branch)

        # Make worktree dirty
        worktree_path = task.worktrees[0].path
        test_file = worktree_path / "dirty.txt"
        test_file.write_text("uncommitted changes")

        report = task_manager.check_task_safety(task)

        assert report.has_dirty()
        assert not report.is_safe()

    def test_check_task_safety_nonexistent_worktree(self, task_manager, sample_repo, tmp_path):
        """Test check_task_safety skips nonexistent worktrees."""
        repo_path, branch = sample_repo
        task = Task(
            name="GHOST-TASK",
            path=tmp_path / "ghost",
            worktrees=[Worktree(name="ghost", path=tmp_path / "nonexistent")],
        )

        report = task_manager.check_task_safety(task)
        # Should not crash, just skip the worktree
        assert isinstance(report, TaskSafetyReport)

    def test_check_task_safety_pushed_and_merged(self, task_manager, repo_with_origin):
        """A freshly created task at the pushed base is safe once pushed."""
        base = repo_with_origin
        task = task_manager.create_task("MERGED-TASK", ["repo-remote"], base)
        # The new branch points at base's commit and needs pushing first
        task_manager.push_all_branches(task)

        report = task_manager.check_task_safety(task)
        assert report.is_safe()
        assert not report.unmerged


class TestStatusErrorSafety:
    """A failed git status must block deletion, never pass as clean."""

    def test_status_error_blocks_and_skips_forge(self, task_manager, sample_repo, monkeypatch):
        from tasktree_manager.services import forge
        from tasktree_manager.services.git_ops import GitOps, GitStatus

        repo_path, branch = sample_repo
        task = task_manager.create_task("ERR-TASK", ["sample-repo"], branch)

        monkeypatch.setattr(
            GitOps, "get_status", staticmethod(lambda wt: GitStatus(error="Git status timed out"))
        )

        def forge_must_not_run(path, br, max_age=None):
            raise AssertionError("forge must not be consulted when git status failed")

        monkeypatch.setattr(forge, "get_forge_status", forge_must_not_run)

        report = task_manager.check_task_safety(task)
        assert not report.is_safe()
        assert report.has_errors()
        assert len(report.errors) == 1
        assert "git status failed" in report.errors[0].details
        # No phantom clean/merged verdicts alongside the error
        assert not report.unmerged and not report.dirty and not report.merged_via_forge


class TestTaskBaseRecording:
    """The base branch is recorded at create time and drives archives."""

    def test_task_base_recorded_and_used_by_archive(self, task_manager, repo_with_origin, config):
        from tasktree_manager.services.git_ops import GitOps

        base = repo_with_origin
        task = task_manager.create_task("BASE-TASK", ["repo-remote"], base)
        wt = task.worktrees[0]

        assert GitOps.get_task_base(wt, "BASE-TASK") == base

        (wt.path / "x.txt").write_text("x\n")
        archive_path = task_manager.archive_task(task)
        assert archive_path is not None
        assert f"base: {base}" in archive_path.read_text()

    def test_get_task_base_missing(self, worktree_from_repo):
        from tasktree_manager.services.git_ops import GitOps

        assert GitOps.get_task_base(worktree_from_repo, "no-such-branch") is None


class TestDisplayName:
    """Display alias: TUI label only, folder/branch untouched."""

    def test_set_and_read_alias(self, task_manager, sample_repo):
        repo_path, branch = sample_repo
        task = task_manager.create_task("DIC-1901-argocd-tls", ["sample-repo"], branch)

        task_manager.set_task_display_name(task, "ArgoCD TLS rollout")
        assert task.display_name == "ArgoCD TLS rollout"
        assert task.display_label == "ArgoCD TLS rollout"
        # Real identity untouched
        assert task.name == "DIC-1901-argocd-tls"
        assert task.path.name == "DIC-1901-argocd-tls"
        assert (task.path / ".tasktree_name").exists()
        # A fresh load sees the alias too (read lazily from disk)
        reloaded = task_manager.get_task("DIC-1901-argocd-tls")
        assert reloaded is not None
        assert reloaded.display_label == "ArgoCD TLS rollout"

    def test_clear_alias_with_empty(self, task_manager, sample_repo):
        repo_path, branch = sample_repo
        task = task_manager.create_task("ALIAS-CLEAR", ["sample-repo"], branch)
        task_manager.set_task_display_name(task, "temp label")
        task_manager.set_task_display_name(task, "")
        assert task.display_name is None
        assert task.display_label == "ALIAS-CLEAR"
        assert not (task.path / ".tasktree_name").exists()

    def test_alias_equal_to_real_name_clears(self, task_manager, sample_repo):
        repo_path, branch = sample_repo
        task = task_manager.create_task("ALIAS-SAME", ["sample-repo"], branch)
        task_manager.set_task_display_name(task, "ALIAS-SAME")
        assert not (task.path / ".tasktree_name").exists()
        assert task.display_label == "ALIAS-SAME"

    def test_no_alias_by_default(self, task_manager, sample_repo):
        repo_path, branch = sample_repo
        task = task_manager.create_task("ALIAS-NONE", ["sample-repo"], branch)
        assert task.display_name is None
        assert task.display_label == "ALIAS-NONE"


class TestForgeAwareSafety:
    """Squash/rebase merges detected via the forge (glab/gh) MR state."""

    def test_squash_merge_reported_safe(self, task_manager, squash_merged_task, monkeypatch):
        from tasktree_manager.services import forge
        from tasktree_manager.services.forge import ForgeStatus

        task, base = squash_merged_task
        monkeypatch.setattr(
            forge,
            "get_forge_status",
            lambda path, branch, max_age=None: ForgeStatus(
                provider="gitlab",
                mr_state="merged",
                mr_url="https://gitlab.example.com/g/p/-/merge_requests/42",
                mr_ref="!42",
            ),
        )

        report = task_manager.check_task_safety(task)
        assert report.is_safe()
        assert not report.unmerged
        assert len(report.merged_via_forge) == 1
        issue = report.merged_via_forge[0]
        assert issue.issue_type == "merged"
        assert "!42" in issue.details
        assert issue.mr_url == "https://gitlab.example.com/g/p/-/merge_requests/42"
        assert issue.branch == "TASK-squash"

    def test_squash_merge_without_forge_stays_unmerged(self, task_manager, squash_merged_task):
        """Regression: local-path origin means no forge info — unmerged stands."""
        task, base = squash_merged_task

        report = task_manager.check_task_safety(task)
        assert not report.is_safe()
        assert len(report.unmerged) == 1
        assert f"not merged to {base}" in report.unmerged[0].details
        assert not report.merged_via_forge

    def test_open_mr_enriches_unmerged_details(self, task_manager, squash_merged_task, monkeypatch):
        from tasktree_manager.services import forge
        from tasktree_manager.services.forge import ForgeStatus

        task, base = squash_merged_task
        monkeypatch.setattr(
            forge,
            "get_forge_status",
            lambda path, branch, max_age=None: ForgeStatus(
                provider="gitlab",
                mr_state="open",
                mr_url="https://gitlab.example.com/g/p/-/merge_requests/7",
                mr_ref="!7",
                ci_state="running",
            ),
        )

        report = task_manager.check_task_safety(task)
        assert not report.is_safe()
        assert len(report.unmerged) == 1
        issue = report.unmerged[0]
        assert "(!7 open, CI running)" in issue.details
        assert issue.mr_state == "open"
        assert issue.mr_url is not None


class TestArchiveTask:
    """Tests for archive_task (finished-task diff archives)."""

    def test_archive_committed_and_uncommitted(self, config, task_manager, repo_with_origin):
        base = repo_with_origin
        task = task_manager.create_task("ARCH-TASK", ["repo-remote"], base)
        wt = task.worktrees[0]

        (wt.path / "committed.txt").write_text("committed change\n")
        subprocess.run(["git", "add", "."], cwd=wt.path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "work"], cwd=wt.path, capture_output=True, check=True
        )
        (wt.path / "uncommitted.txt").write_text("uncommitted change\n")

        archive_path = task_manager.archive_task(task, notes=["mr: !42 merged"])
        assert archive_path is not None
        assert archive_path.parent == config.get_archive_dir()
        assert archive_path.name.startswith("ARCH-TASK-")
        assert archive_path.suffix == ".patch"

        content = archive_path.read_text()
        assert "# tasktree-manager archive: ARCH-TASK" in content
        assert "# repo: repo-remote" in content
        assert "# mr: !42 merged" in content
        assert "committed change" in content
        assert "uncommitted change" in content
        # Repo-labelled diff prefixes for multi-repo concatenation
        assert "a/repo-remote/" in content

    def test_archive_clean_task_returns_none(self, config, task_manager, repo_with_origin):
        base = repo_with_origin
        task = task_manager.create_task("CLEAN-ARCH", ["repo-remote"], base)

        assert task_manager.archive_task(task) is None
        # No empty archive files left behind
        archive_dir = config.get_archive_dir()
        assert not archive_dir.exists() or not list(archive_dir.iterdir())

    def test_archive_uses_task_branch_not_head(self, config, task_manager, repo_with_origin):
        """A detached worktree must still archive the task branch's commits.

        finish_task deletes refs/heads/<task>; if the archive followed HEAD
        instead, switching the worktree away from the task branch would
        silently drop those commits from the safety net.
        """
        base = repo_with_origin
        task = task_manager.create_task("ARCHIVE-HEAD", ["repo-remote"], base)
        wt = task.worktrees[0]
        (wt.path / "committed.txt").write_text("work\n")
        subprocess.run(["git", "add", "."], cwd=wt.path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "task work"], cwd=wt.path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "checkout", "-q", "--detach", f"origin/{base}"],
            cwd=wt.path,
            check=True,
            capture_output=True,
        )

        archive_path = task_manager.archive_task(task)
        assert archive_path is not None
        assert "committed.txt" in archive_path.read_text()

    def test_list_tasks_ignores_archive_dir(self, config, task_manager, repo_with_origin):
        base = repo_with_origin
        task = task_manager.create_task("VISIBLE-TASK", ["repo-remote"], base)
        wt = task.worktrees[0]
        (wt.path / "x.txt").write_text("x\n")
        task_manager.archive_task(task)

        names = [t.name for t in task_manager.list_tasks()]
        assert "VISIBLE-TASK" in names
        assert all(not name.startswith(".") for name in names)


class TestPushAllBranches:
    """Tests for push_all_branches method."""

    def test_push_all_branches_no_worktrees(self, task_manager, tmp_path):
        """Test push_all_branches with no worktrees."""
        task = Task(name="EMPTY", path=tmp_path / "empty", worktrees=[])

        success_repos, failed_repos = task_manager.push_all_branches(task)

        assert success_repos == []
        assert failed_repos == []

    def test_push_all_branches_nonexistent_worktree(self, task_manager, tmp_path):
        """Test push_all_branches with nonexistent worktree."""
        task = Task(
            name="GHOST",
            path=tmp_path / "ghost",
            worktrees=[Worktree(name="ghost", path=tmp_path / "nonexistent")],
        )

        success_repos, failed_repos = task_manager.push_all_branches(task)

        assert "ghost" in failed_repos
        assert success_repos == []


class TestTaskManagerEdgeCases:
    """Edge case tests for TaskManager."""

    def test_list_tasks_nonexistent_dir(self, config):
        """Test list_tasks when tasks_dir doesn't exist."""
        import shutil

        from tasktree_manager.services.task_manager import TaskManager

        # Remove tasks dir
        shutil.rmtree(config.tasks_dir)

        manager = TaskManager(config)
        tasks = manager.list_tasks()

        assert tasks == []

    def test_get_task_nonexistent(self, task_manager):
        """Test get_task returns None for nonexistent task."""
        task = task_manager.get_task("DOES-NOT-EXIST")
        assert task is None

    def test_create_task_existing_branch(self, task_manager, sample_repo):
        """Test creating task when branch already exists."""
        repo_path, branch = sample_repo

        # Leave a branch with its own commit behind (as if a task was
        # removed by hand, or the branch was created outside tasktree)
        subprocess.run(
            ["git", "branch", "BRANCH-TEST", branch], cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "checkout", "-q", "BRANCH-TEST"], cwd=repo_path, check=True, capture_output=True
        )
        (repo_path / "kept.txt").write_text("keep me\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "prior work"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-q", branch], cwd=repo_path, check=True, capture_output=True
        )

        # Creating the task reuses the branch as-is instead of resetting it
        # to the base (-B), which would orphan the prior commit
        task = task_manager.create_task("BRANCH-TEST", ["sample-repo"], branch)
        assert task.name == "BRANCH-TEST"
        assert (task.worktrees[0].path / "kept.txt").exists()

    def test_add_existing_repo_to_task(self, task_manager, sample_repos):
        """Test adding a repo that already exists in task."""
        repos, branch = sample_repos
        task = task_manager.create_task("DUP-TEST", ["repo-alpha"], branch)

        # Adding same repo should not create duplicate
        initial_count = len(task.worktrees)
        task_manager.add_repo_to_task(task, "repo-alpha", branch)

        # Should still have same number (already exists)
        assert len(task.worktrees) == initial_count

    def test_finish_task_cleans_worktrees(self, task_manager, sample_repos):
        """Test that finish_task removes worktrees properly."""
        repos, branch = sample_repos
        task = task_manager.create_task("FINISH-TEST", ["repo-alpha", "repo-beta"], branch)

        # Verify worktrees exist
        for wt in task.worktrees:
            assert wt.path.exists()

        # Finish task
        task_manager.finish_task(task)

        # Verify task directory is gone
        assert not task.path.exists()

    def test_get_repos_not_in_task_all_used(self, task_manager, sample_repo):
        """Test get_repos_not_in_task when all repos are used."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("FULL", ["sample-repo"], branch)

        available = task_manager.get_repos_not_in_task(task)
        assert "sample-repo" not in available


class TestGitignoreSymlinks:
    """Tests for gitignore symlink functionality."""

    def test_create_symlinks_for_gitignored_files(self, task_manager, sample_repo):
        """Test that gitignored files are symlinked to worktree."""
        repo_path, branch = sample_repo

        # Create .gitignore and a file to be ignored
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n")

        env_file = repo_path / ".env"
        env_file.write_text("SECRET=value\n")

        # Create task (worktree)
        task = task_manager.create_task("SYMLINK-TEST", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # Verify symlink was created
        worktree_env = worktree_path / ".env"
        assert worktree_env.exists()
        assert worktree_env.is_symlink()
        assert worktree_env.resolve() == env_file.resolve()
        assert worktree_env.read_text() == "SECRET=value\n"

    def test_no_symlinks_when_no_gitignore(self, task_manager, sample_repo):
        """Test that no symlinks are created when .gitignore doesn't exist."""
        repo_path, branch = sample_repo

        # Remove .gitignore if it exists
        gitignore = repo_path / ".gitignore"
        if gitignore.exists():
            gitignore.unlink()

        # Create a random file
        some_file = repo_path / "some_file.txt"
        some_file.write_text("content\n")

        # Create task (worktree)
        task = task_manager.create_task("NO-GITIGNORE", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # Verify no symlinks were created for the file
        worktree_file = worktree_path / "some_file.txt"
        # The file may or may not exist depending on git behavior,
        # but if it exists it should not be a symlink
        if worktree_file.exists():
            assert not worktree_file.is_symlink()

    def test_symlinks_for_multiple_gitignored_files(self, task_manager, sample_repo):
        """Test that multiple gitignored files are symlinked."""
        repo_path, branch = sample_repo

        # Create .gitignore with multiple patterns
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\nconfig.local.json\n*.secret\n")

        # Create matching files
        (repo_path / ".env").write_text("ENV=value\n")
        (repo_path / "config.local.json").write_text('{"key": "value"}\n')
        (repo_path / "api.secret").write_text("api_key=123\n")

        # Create task (worktree)
        task = task_manager.create_task("MULTI-SYMLINK", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # Verify all symlinks were created
        for filename in [".env", "config.local.json", "api.secret"]:
            worktree_file = worktree_path / filename
            assert worktree_file.exists(), f"{filename} should exist"
            assert worktree_file.is_symlink(), f"{filename} should be a symlink"

    def test_skip_directory_patterns(self, task_manager, sample_repo):
        """Test that directory patterns (ending with /) are skipped."""
        repo_path, branch = sample_repo

        # Create .gitignore with directory pattern
        gitignore = repo_path / ".gitignore"
        gitignore.write_text("node_modules/\nbuild/\n.env\n")

        # Create the directories and a file
        (repo_path / "node_modules").mkdir()
        (repo_path / "node_modules" / "package.json").write_text("{}\n")
        (repo_path / ".env").write_text("test\n")

        # Create task (worktree)
        task = task_manager.create_task("DIR-SKIP", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # .env should be symlinked
        assert (worktree_path / ".env").is_symlink()

        # node_modules directory should not be symlinked (we only symlink files)
        # and directory patterns are skipped
        if (worktree_path / "node_modules").exists():
            assert not (worktree_path / "node_modules").is_symlink()

    def test_skip_negation_patterns(self, task_manager, sample_repo):
        """Test that negation patterns (starting with !) are skipped."""
        repo_path, branch = sample_repo

        # Create .gitignore with negation pattern
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n!.env.example\n")

        # Create .env
        (repo_path / ".env").write_text("SECRET\n")

        # Create task (worktree)
        task = task_manager.create_task("NEG-SKIP", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # Only .env should be symlinked (negation patterns are ignored)
        assert (worktree_path / ".env").is_symlink()

    def test_skip_comments_and_empty_lines(self, task_manager, sample_repo):
        """Test that comments and empty lines in .gitignore are skipped."""
        repo_path, branch = sample_repo

        # Create .gitignore with comments and empty lines
        gitignore = repo_path / ".gitignore"
        gitignore.write_text("# This is a comment\n\n.env\n   # indented comment\n\n")

        # Create .env
        (repo_path / ".env").write_text("test\n")

        # Create task (worktree)
        task = task_manager.create_task("COMMENTS", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # .env should be symlinked
        assert (worktree_path / ".env").is_symlink()

    def test_list_gitignored_files(self, task_manager, sample_repo):
        """Test the _list_gitignored_files helper directly."""
        repo_path, branch = sample_repo

        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\nnode_modules/\n*.secret\n")

        (repo_path / ".env").write_text("SECRET\n")
        (repo_path / "node_modules").mkdir()
        (repo_path / "node_modules" / "package.json").write_text("{}\n")
        conf_dir = repo_path / "conf"
        conf_dir.mkdir()
        (conf_dir / "api.secret").write_text("key\n")

        files = task_manager._list_gitignored_files(repo_path)

        # Individual ignored files are listed, including nested ones;
        # ignored directories are collapsed and skipped, not walked
        assert ".env" in files
        assert "conf/api.secret" in files
        assert all("node_modules" not in f for f in files)

    def test_symlinks_nested_gitignored_files(self, task_manager, sample_repo):
        """A root pattern like *.secret matches in subdirectories (gitignore
        semantics), so nested ignored files are symlinked too."""
        repo_path, branch = sample_repo

        gitignore = repo_path / ".gitignore"
        gitignore.write_text("*.secret\n")

        conf_dir = repo_path / "conf"
        conf_dir.mkdir()
        (conf_dir / "api.secret").write_text("key\n")

        task = task_manager.create_task("NESTED-SYMLINK", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        assert (worktree_path / "conf" / "api.secret").is_symlink()

    def test_symlinks_skip_claude_settings(self, task_manager, sample_repo):
        """Files under .claude are never symlinked: tasktree writes its own
        worktree settings there, and a symlink would redirect those writes
        into the main checkout."""
        repo_path, branch = sample_repo

        (repo_path / ".gitignore").write_text(".claude/\n.env\n")
        claude_dir = repo_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.local.json").write_text("{}\n")
        (repo_path / ".env").write_text("SECRET\n")

        task = task_manager.create_task("CLAUDE-SKIP", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        assert (worktree_path / ".env").is_symlink()
        assert not (worktree_path / ".claude" / "settings.local.json").is_symlink()

    def test_blocklist_matches_relative_paths(self, temp_dirs, sample_repo):
        """Blocklist patterns match repo-relative paths, not just filenames."""
        from tasktree_manager.services.config import Config
        from tasktree_manager.services.task_manager import TaskManager

        repos_dir, tasks_dir = temp_dirs
        repo_path, branch = sample_repo

        config = Config(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=repos_dir.parent / ".config" / "tasktree-manager",
            symlink_blocklist=["secrets/*"],  # path-shaped pattern
        )
        manager = TaskManager(config)

        (repo_path / ".gitignore").write_text("*.env\n")
        secrets_dir = repo_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "prod.env").write_text("blocked\n")
        (repo_path / "dev.env").write_text("allowed\n")

        task = manager.create_task("PATH-BLOCK", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        assert (worktree_path / "dev.env").is_symlink()
        assert not (worktree_path / "secrets" / "prod.env").exists()

    def test_symlinks_skip_key_material(self, task_manager, sample_repo):
        """Private keys and certificates are blocklisted by default."""
        repo_path, branch = sample_repo

        (repo_path / ".gitignore").write_text("*.pem\n*.key\nid_rsa\n.env\n")
        (repo_path / "server.pem").write_text("cert\n")
        (repo_path / "private.key").write_text("key\n")
        (repo_path / "id_rsa").write_text("ssh\n")
        (repo_path / ".env").write_text("SECRET\n")

        task = task_manager.create_task("KEYS-SKIP", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        assert (worktree_path / ".env").is_symlink()
        assert not (worktree_path / "server.pem").exists()
        assert not (worktree_path / "private.key").exists()
        assert not (worktree_path / "id_rsa").exists()

    def test_symlinks_skip_blocklisted_files(self, task_manager, sample_repo):
        """Test that files matching blocklist patterns are not symlinked."""
        repo_path, branch = sample_repo

        # Create .gitignore with both wanted and blocklisted patterns
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n*.pyc\n.coverage\n*.log\n")

        # Create files - some should be linked, some blocked
        (repo_path / ".env").write_text("SECRET=value\n")
        (repo_path / "test.pyc").write_text("compiled\n")
        (repo_path / ".coverage").write_text("coverage data\n")
        (repo_path / "app.log").write_text("log content\n")

        # Create task (worktree)
        task = task_manager.create_task("BLOCKLIST-TEST", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # .env should be symlinked (not in default blocklist)
        assert (worktree_path / ".env").exists()
        assert (worktree_path / ".env").is_symlink()

        # Blocklisted files should NOT be symlinked
        assert not (worktree_path / "test.pyc").exists()
        assert not (worktree_path / ".coverage").exists()
        assert not (worktree_path / "app.log").exists()

    def test_symlinks_with_empty_blocklist(self, temp_dirs, sample_repo):
        """Test that empty blocklist allows all files to be symlinked."""
        from tasktree_manager.services.config import Config
        from tasktree_manager.services.task_manager import TaskManager

        repos_dir, tasks_dir = temp_dirs
        repo_path, branch = sample_repo

        # Create config with empty blocklist
        config = Config(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=repos_dir.parent / ".config" / "tasktree-manager",
            symlink_blocklist=[],  # Empty blocklist
        )
        manager = TaskManager(config)

        # Create .gitignore with patterns that would normally be blocked
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n*.pyc\n.coverage\n")

        # Create files
        (repo_path / ".env").write_text("SECRET=value\n")
        (repo_path / "test.pyc").write_text("compiled\n")
        (repo_path / ".coverage").write_text("coverage data\n")

        # Create task (worktree)
        task = manager.create_task("EMPTY-BLOCKLIST", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # All files should be symlinked with empty blocklist
        assert (worktree_path / ".env").is_symlink()
        assert (worktree_path / "test.pyc").is_symlink()
        assert (worktree_path / ".coverage").is_symlink()

    def test_symlinks_custom_blocklist(self, temp_dirs, sample_repo):
        """Test that custom blocklist patterns are respected."""
        from tasktree_manager.services.config import Config
        from tasktree_manager.services.task_manager import TaskManager

        repos_dir, tasks_dir = temp_dirs
        repo_path, branch = sample_repo

        # Create config with custom blocklist (block .env but allow *.pyc)
        config = Config(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=repos_dir.parent / ".config" / "tasktree-manager",
            symlink_blocklist=[".env*", "*.secret"],  # Custom blocklist
        )
        manager = TaskManager(config)

        # Create .gitignore
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n.env.local\ntest.pyc\napi.secret\n")

        # Create files
        (repo_path / ".env").write_text("blocked\n")
        (repo_path / ".env.local").write_text("also blocked\n")
        (repo_path / "test.pyc").write_text("allowed now\n")
        (repo_path / "api.secret").write_text("blocked\n")

        # Create task (worktree)
        task = manager.create_task("CUSTOM-BLOCKLIST", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # .env files should be blocked
        assert not (worktree_path / ".env").exists()
        assert not (worktree_path / ".env.local").exists()
        assert not (worktree_path / "api.secret").exists()

        # .pyc should be allowed with this custom blocklist
        assert (worktree_path / "test.pyc").is_symlink()

    def test_matches_blocklist_method(self, task_manager):
        """Test the _matches_blocklist helper method."""
        blocklist = ["*.pyc", ".coverage", "__pycache__", "*.log"]

        # These should match
        assert task_manager._matches_blocklist("test.pyc", blocklist)
        assert task_manager._matches_blocklist(".coverage", blocklist)
        assert task_manager._matches_blocklist("__pycache__", blocklist)
        assert task_manager._matches_blocklist("app.log", blocklist)
        assert task_manager._matches_blocklist("debug.log", blocklist)

        # These should not match
        assert not task_manager._matches_blocklist(".env", blocklist)
        assert not task_manager._matches_blocklist("config.json", blocklist)
        assert not task_manager._matches_blocklist(".mise.toml", blocklist)
        assert not task_manager._matches_blocklist("README.md", blocklist)


class TestWorktreeBaseFreshness:
    """Worktrees must start from the up-to-date remote base branch."""

    @staticmethod
    def _git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    def _make_commit(self, repo, filename, message):
        (repo / filename).write_text(f"{filename}\n")
        self._git("add", ".", cwd=repo)
        self._git("commit", "-q", "-m", message, cwd=repo)

    def test_worktree_uses_remote_base_when_local_is_stale(self, config, task_manager):
        """Stale local master + checkout on another branch: worktree must
        still contain the latest origin/master commit (regression: worktrees
        were created from the stale local base branch)."""
        upstream = config.repos_dir.parent / "upstream-repo"
        upstream.mkdir()
        self._git("init", "-q", "-b", "master", cwd=upstream)
        self._git("config", "user.email", "test@example.com", cwd=upstream)
        self._git("config", "user.name", "Test", cwd=upstream)
        self._make_commit(upstream, "base.txt", "base")

        # Clone into repos_dir, then move the clone onto an unrelated branch
        # so its local master ref goes stale relative to origin
        clone = config.repos_dir / "cloned-repo"
        self._git("clone", "-q", str(upstream), str(clone), cwd=config.repos_dir)
        self._git("config", "user.email", "test@example.com", cwd=clone)
        self._git("config", "user.name", "Test", cwd=clone)
        self._git("checkout", "-q", "-b", "unrelated-feature", cwd=clone)

        # Upstream master moves ahead of the clone
        self._make_commit(upstream, "newer.txt", "newer")

        task = task_manager.create_task("FRESH-1", ["cloned-repo"], "master")

        worktree = task.path / "cloned-repo"
        assert (worktree / "base.txt").exists()
        assert (worktree / "newer.txt").exists(), (
            "worktree must be based on origin/master, not the stale local master"
        )

    def test_worktree_falls_back_to_local_base_without_remote(
        self, config, task_manager, sample_repo
    ):
        """Repos without an origin remote still work (offline fallback)."""
        repo_path, branch = sample_repo

        task = task_manager.create_task("FRESH-2", ["sample-repo"], branch)

        worktree = task.path / "sample-repo"
        assert (worktree / "README.md").exists()


class TestEnsureClaudeMdFiles:
    """Worktree CLAUDE.md comes from the repo itself, never from a stub."""

    def test_no_stub_when_repo_has_no_claude_md(self, task_manager, sample_repo):
        """Repos without CLAUDE.md get no generated worktree stub."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("CMD-1", ["sample-repo"], branch)

        task_manager.ensure_claude_md_files(task)

        assert (task.path / "CLAUDE.md").exists()  # task-level file is generated
        assert not (task.path / "sample-repo" / "CLAUDE.md").exists()

    def test_backfills_from_repo_checkout(self, task_manager, sample_repo):
        """A repo CLAUDE.md added after the branch was cut is copied in."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("CMD-2", ["sample-repo"], branch)
        worktree_md = task.path / "sample-repo" / "CLAUDE.md"
        assert not worktree_md.exists()

        (repo_path / "CLAUDE.md").write_text("# Repo guidance\n")
        task_manager.ensure_claude_md_files(task)

        assert worktree_md.read_text() == "# Repo guidance\n"

    def test_prefers_remote_default_branch_content(self, task_manager, config):
        """With an origin remote, the committed CLAUDE.md wins over the checkout file."""
        upstream = config.repos_dir.parent / "claude-upstream"
        upstream.mkdir()
        for args in (
            ["init", "-q", "-b", "master"],
            ["config", "user.email", "t@example.com"],
            ["config", "user.name", "t"],
        ):
            subprocess.run(["git", *args], cwd=upstream, check=True, capture_output=True)
        (upstream / "README.md").write_text("readme\n")
        subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"], cwd=upstream, check=True, capture_output=True
        )

        clone = config.repos_dir / "claude-repo"
        subprocess.run(
            ["git", "clone", "-q", str(upstream), str(clone)], check=True, capture_output=True
        )
        task = task_manager.create_task("CMD-3", ["claude-repo"], "master")
        worktree_md = task.path / "claude-repo" / "CLAUDE.md"
        assert not worktree_md.exists()

        # Commit CLAUDE.md upstream (after the branch was cut) and fetch it;
        # also plant a different file in the clone checkout
        (upstream / "CLAUDE.md").write_text("# committed guidance\n")
        subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "add claude md"],
            cwd=upstream,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "fetch", "-q", "origin"], cwd=clone, check=True, capture_output=True)
        (clone / "CLAUDE.md").write_text("# local checkout file\n")

        task_manager.ensure_claude_md_files(task)

        assert worktree_md.read_text() == "# committed guidance\n"

    def test_never_overwrites_existing_worktree_claude_md(self, task_manager, sample_repo):
        """An existing worktree CLAUDE.md is left untouched."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("CMD-4", ["sample-repo"], branch)
        worktree_md = task.path / "sample-repo" / "CLAUDE.md"
        worktree_md.write_text("# my notes\n")
        (repo_path / "CLAUDE.md").write_text("# repo guidance\n")

        task_manager.ensure_claude_md_files(task)

        assert worktree_md.read_text() == "# my notes\n"


class TestWorktreeClaudeSettings:
    """Tests for per-repo Claude memory settings in worktrees."""

    def test_create_task_writes_worktree_settings(self, task_manager, sample_repo):
        """New worktrees get settings pointing memory at the repo's memory dir."""
        import json

        from tasktree_manager.services.claude_hooks import repo_memory_dir

        repo_path, branch = sample_repo
        task = task_manager.create_task("MEM-1", ["sample-repo"], branch)

        settings_file = task.path / "sample-repo" / ".claude" / "settings.local.json"
        assert settings_file.exists()
        settings = json.loads(settings_file.read_text())
        assert settings["autoMemoryDirectory"] == str(repo_memory_dir(repo_path))
        assert str(task.path / ".claude_status") in json.dumps(settings["hooks"])

    def test_worktree_stays_clean(self, task_manager, sample_repo):
        """The generated settings file must not show up as a dirty worktree."""
        from tasktree_manager.services.git_ops import GitOps

        _, branch = sample_repo
        task = task_manager.create_task("MEM-2", ["sample-repo"], branch)

        status = GitOps.get_status(task.worktrees[0])
        assert status.is_dirty is False

    def test_disabled_by_config(self, task_manager, sample_repo):
        """No settings file is written when claude_repo_memory is off."""
        task_manager.config.claude_repo_memory = False
        _, branch = sample_repo
        task = task_manager.create_task("MEM-3", ["sample-repo"], branch)

        assert not (task.path / "sample-repo" / ".claude").exists()

    def test_ensure_worktree_settings_backfills(self, task_manager, sample_repo):
        """Existing worktrees without settings get them backfilled."""
        task_manager.config.claude_repo_memory = False
        _, branch = sample_repo
        task = task_manager.create_task("MEM-4", ["sample-repo"], branch)
        assert not (task.path / "sample-repo" / ".claude").exists()

        task_manager.config.claude_repo_memory = True
        task_manager.ensure_worktree_settings(task)

        assert (task.path / "sample-repo" / ".claude" / "settings.local.json").exists()
