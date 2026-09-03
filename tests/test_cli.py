"""Tests for the headless CLI (tasktree_manager/cli.py)."""

import json
import subprocess

import pytest

from tasktree_manager.cli import run_cli


def cli(config, *argv):
    """Run the CLI against the test config."""
    return run_cli(list(argv), config=config)


@pytest.fixture
def cli_config(config, sample_repos):
    """Config whose default base branch matches the sample repos' actual branch.

    CI runners have no init.defaultBranch configured, so fixture repos may be
    on master while the config default is main; tests that rely on the default
    base branch must line the two up.
    """
    _, branch = sample_repos
    config.default_base_branch = branch
    return config


class TestCreate:
    def test_create_task(self, cli_config, capsys):
        code = cli(cli_config, "create", "DIC-1901-argocd-tls", "--repos", "repo-alpha,repo-beta")
        assert code == 0
        out = capsys.readouterr().out
        assert "Created task DIC-1901-argocd-tls" in out
        assert "2 repo(s)" in out

        task_path = cli_config.tasks_dir / "DIC-1901-argocd-tls"
        assert (task_path / "repo-alpha" / ".git").exists()
        assert (task_path / "repo-beta" / ".git").exists()
        # Branch name matches task name
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=task_path / "repo-alpha",
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "DIC-1901-argocd-tls"
        # Task CLAUDE.md is materialized at create time (no TUI lazy prep)
        assert (task_path / "CLAUDE.md").exists()

    def test_create_with_base(self, config, sample_repos, capsys):
        _, branch = sample_repos
        code = cli(config, "create", "task-x", "--repos", "repo-alpha", "--base", branch)
        assert code == 0

    def test_create_unknown_repo(self, config, sample_repos, capsys):
        code = cli(config, "create", "task-x", "--repos", "no-such-repo")
        assert code == 1
        err = capsys.readouterr().err
        assert "unknown repo(s): no-such-repo" in err
        assert "repo-alpha" in err  # lists available repos
        assert not (config.tasks_dir / "task-x").exists()

    def test_create_duplicate(self, cli_config, capsys):
        assert cli(cli_config, "create", "task-x", "--repos", "repo-alpha") == 0
        capsys.readouterr()
        code = cli(cli_config, "create", "task-x", "--repos", "repo-beta")
        assert code == 1
        assert "task already exists" in capsys.readouterr().err

    def test_create_invalid_name(self, config, sample_repos, capsys):
        code = cli(config, "create", "../escape", "--repos", "repo-alpha")
        assert code == 1
        assert "error:" in capsys.readouterr().err

    def test_create_empty_repos(self, config, sample_repos, capsys):
        code = cli(config, "create", "task-x", "--repos", " , ")
        assert code == 1
        assert "at least one repo" in capsys.readouterr().err


class TestList:
    def test_list_empty(self, config, capsys):
        assert cli(config, "list") == 0
        assert "No tasks" in capsys.readouterr().out

    def test_list_plain(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha,repo-beta")
        capsys.readouterr()
        assert cli(cli_config, "list") == 0
        out = capsys.readouterr().out
        assert "task-x" in out
        assert "clean" in out
        assert "repo-alpha, repo-beta" in out

    def test_list_json(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "list", "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 1
        assert payload[0]["name"] == "task-x"
        assert payload[0]["repos"] == ["repo-alpha"]
        assert payload[0]["dirty"] is False
        assert payload[0]["path"] == str(cli_config.tasks_dir / "task-x")

    def test_list_json_empty(self, config, capsys):
        assert cli(config, "list", "--json") == 0
        assert json.loads(capsys.readouterr().out) == []

    def test_list_dirty(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        (cli_config.tasks_dir / "task-x" / "repo-alpha" / "dirty.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(cli_config, "list", "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["dirty"] is True


class TestDelete:
    def test_delete_clean(self, config, repo_with_origin, capsys):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        capsys.readouterr()
        assert cli(config, "delete", "task-x") == 0
        assert "Deleted task task-x" in capsys.readouterr().out
        assert not (config.tasks_dir / "task-x").exists()

    def test_delete_unmerged_refuses(self, cli_config, capsys):
        # Repos without a remote can never verify a merge -> treated as unmerged
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "delete", "task-x") == 1
        assert "unfinished work" in capsys.readouterr().err
        assert (cli_config.tasks_dir / "task-x").exists()

    def test_delete_missing(self, config, capsys):
        assert cli(config, "delete", "nope") == 1
        assert "no such task" in capsys.readouterr().err

    def test_delete_dirty_refuses(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        (cli_config.tasks_dir / "task-x" / "repo-alpha" / "dirty.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(cli_config, "delete", "task-x") == 1
        err = capsys.readouterr().err
        assert "unfinished work" in err
        assert "--force" in err
        assert (cli_config.tasks_dir / "task-x").exists()

    def test_delete_dirty_force(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        (cli_config.tasks_dir / "task-x" / "repo-alpha" / "dirty.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(cli_config, "delete", "task-x", "--force") == 0
        assert not (cli_config.tasks_dir / "task-x").exists()

    def test_delete_squash_merged_via_forge(self, config, squash_merged_task, monkeypatch, capsys):
        """A squash-merged branch (per the forge) deletes without --force."""
        from tasktree_manager.services import forge
        from tasktree_manager.services.forge import ForgeStatus

        monkeypatch.setattr(
            forge,
            "get_forge_status",
            lambda path, branch, max_age=None: ForgeStatus(
                provider="gitlab", mr_state="merged", mr_ref="!42"
            ),
        )
        capsys.readouterr()
        assert cli(config, "delete", "TASK-squash") == 0
        assert "Deleted task TASK-squash" in capsys.readouterr().out
        assert not (config.tasks_dir / "TASK-squash").exists()

    def test_delete_squash_merged_without_forge_refuses(self, config, squash_merged_task, capsys):
        """Regression: without forge info the squash merge is invisible."""
        capsys.readouterr()
        assert cli(config, "delete", "TASK-squash") == 1
        assert "not merged" in capsys.readouterr().err


class TestFinish:
    def test_finish_clean(self, config, repo_with_origin, capsys):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        capsys.readouterr()
        assert cli(config, "finish", "task-x") == 0
        out = capsys.readouterr().out
        assert "Nothing to archive" in out
        assert "Finished task task-x" in out
        assert not (config.tasks_dir / "task-x").exists()

    def test_finish_missing(self, config, capsys):
        assert cli(config, "finish", "nope") == 1
        assert "no such task" in capsys.readouterr().err

    def test_finish_refuses_with_hints(self, cli_config, capsys):
        # No remote -> the branch can never verify as merged
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "finish", "task-x") == 1
        err = capsys.readouterr().err
        assert "unfinished work" in err
        assert "use --force to finish anyway" in err
        assert (cli_config.tasks_dir / "task-x").exists()

    def test_finish_force_archives_dirty_work(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        (cli_config.tasks_dir / "task-x" / "repo-alpha" / "wip.txt").write_text("precious wip\n")
        capsys.readouterr()
        assert cli(cli_config, "finish", "task-x", "--force") == 0
        out = capsys.readouterr().out
        assert "Archived diff to" in out
        assert not (cli_config.tasks_dir / "task-x").exists()

        archives = list(cli_config.get_archive_dir().iterdir())
        assert len(archives) == 1
        assert "precious wip" in archives[0].read_text()

    def test_finish_force_no_archive(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        (cli_config.tasks_dir / "task-x" / "repo-alpha" / "wip.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(cli_config, "finish", "task-x", "--force", "--no-archive") == 0
        assert "Archived" not in capsys.readouterr().out
        archive_dir = cli_config.get_archive_dir()
        assert not archive_dir.exists() or not list(archive_dir.iterdir())

    def test_finish_unpushed_hint_mentions_push(self, config, squash_merged_task, capsys):
        """An unpushed commit triggers the --push hint."""
        task, base = squash_merged_task
        wt = task.worktrees[0]
        (wt.path / "more.txt").write_text("more\n")
        subprocess.run(["git", "add", "."], cwd=wt.path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "more"], cwd=wt.path, capture_output=True, check=True
        )
        capsys.readouterr()
        assert cli(config, "finish", "TASK-squash") == 1
        err = capsys.readouterr().err
        assert "use --push to push branches first" in err

    def test_finish_push_covers_never_pushed_branch(
        self, config, repo_with_origin, monkeypatch, capsys
    ):
        """--push must push even when ahead reads 0 (no upstream on --no-track)."""
        import subprocess as sp

        from tasktree_manager.services import forge
        from tasktree_manager.services.forge import ForgeStatus

        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        wt = config.tasks_dir / "task-x" / "repo-remote"
        (wt / "work.txt").write_text("work\n")
        sp.run(["git", "add", "."], cwd=wt, capture_output=True, check=True)
        sp.run(["git", "commit", "-m", "work"], cwd=wt, capture_output=True, check=True)
        # Never pushed: no upstream, so report.has_unpushed() is False
        monkeypatch.setattr(
            forge,
            "get_forge_status",
            lambda path, branch, max_age=None: ForgeStatus(
                provider="gitlab", mr_state="merged", mr_ref="!1"
            ),
        )
        capsys.readouterr()
        assert cli(config, "finish", "task-x", "--push") == 0
        out = capsys.readouterr().out
        assert "Pushed repo-remote" in out
        assert "Finished task task-x" in out
        # The commit must survive on the remote after the local branch dies
        result = sp.run(
            ["git", "ls-remote", "--heads", "origin", "task-x"],
            cwd=config.repos_dir / "repo-remote",
            capture_output=True,
            text=True,
        )
        assert "task-x" in result.stdout

    def test_finish_push_and_forge_merged(self, config, squash_merged_task, monkeypatch, capsys):
        """--push clears unpushed work; the forge clears the squash-merged branch."""
        from tasktree_manager.services import forge
        from tasktree_manager.services.forge import ForgeStatus

        task, base = squash_merged_task
        wt = task.worktrees[0]
        (wt.path / "more.txt").write_text("more\n")
        subprocess.run(["git", "add", "."], cwd=wt.path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "more"], cwd=wt.path, capture_output=True, check=True
        )
        monkeypatch.setattr(
            forge,
            "get_forge_status",
            lambda path, branch, max_age=None: ForgeStatus(
                provider="gitlab", mr_state="merged", mr_ref="!42"
            ),
        )
        capsys.readouterr()
        assert cli(config, "finish", "TASK-squash", "--push") == 0
        out = capsys.readouterr().out
        assert "Pushed repo-remote" in out
        assert "merged remotely via !42" in out
        assert "Archived diff to" in out
        assert "Finished task TASK-squash" in out
        assert not (config.tasks_dir / "TASK-squash").exists()


class TestStatus:
    def test_status_json_schema(self, config, repo_with_origin, capsys):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        (config.tasks_dir / "task-x" / "repo-remote" / "wip.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(config, "status", "task-x", "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["task"] == "task-x"
        assert payload["claude"] is None
        wt = payload["worktrees"][0]
        assert wt["repo"] == "repo-remote"
        assert wt["branch"] == "task-x"
        assert wt["dirty"] is True
        assert wt["untracked"] == 1
        assert wt["merged"] is True  # branch still points at the pushed base
        assert wt["merged_via"] == "ancestor"
        assert wt["forge"] is None  # no --forge flag
        assert wt["error"] is None

    def test_status_plain(self, config, repo_with_origin, capsys):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        capsys.readouterr()
        assert cli(config, "status", "task-x") == 0
        out = capsys.readouterr().out
        assert "Task: task-x" in out
        assert "repo-remote" in out
        assert "clean" in out
        assert "merged (ancestor)" in out

    def test_status_oneline(self, config, repo_with_origin, capsys):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        capsys.readouterr()
        assert cli(config, "status", "task-x", "--oneline") == 0
        assert capsys.readouterr().out.strip() == "task-x repo-remote✓"

    def test_status_oneline_dirty_flags(self, config, repo_with_origin, capsys):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        (config.tasks_dir / "task-x" / "repo-remote" / "wip.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(config, "status", "task-x", "--oneline") == 0
        assert capsys.readouterr().out.strip() == "task-x repo-remote●1"

    def test_status_oneline_clean_unmerged_marker(self, cli_config, capsys):
        """Clean but unmerged must render ○, not an invisible bare name."""
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "status", "task-x", "--oneline") == 0
        assert capsys.readouterr().out.strip() == "task-x repo-alpha○"

    def test_status_infers_task_from_pwd(self, config, repo_with_origin, capsys, monkeypatch):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        capsys.readouterr()
        monkeypatch.chdir(config.tasks_dir / "task-x" / "repo-remote")
        assert cli(config, "status") == 0
        assert "Task: task-x" in capsys.readouterr().out

    def test_status_outside_task_dir(self, config, sample_repos, capsys, monkeypatch, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        assert cli(config, "status") == 1
        assert "not inside a task directory" in capsys.readouterr().err

    def test_status_missing_task(self, config, capsys):
        assert cli(config, "status", "nope") == 1
        assert "no such task" in capsys.readouterr().err

    def test_status_reads_claude_state(self, config, repo_with_origin, capsys):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        (config.tasks_dir / "task-x" / ".claude_status").write_text(
            '{"status": "waiting", "ts": 1753900000}'
        )
        capsys.readouterr()
        assert cli(config, "status", "task-x", "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["claude"] == {"status": "waiting", "ts": 1753900000}

    def test_status_forge_merged(self, config, squash_merged_task, monkeypatch, capsys):
        """--forge marks a squash-merged branch as merged_via forge."""
        from tasktree_manager.services import forge as forge_module
        from tasktree_manager.services.forge import ForgeStatus

        monkeypatch.setattr(
            forge_module,
            "get_forge_status",
            lambda path, branch, max_age=None: ForgeStatus(
                provider="gitlab",
                mr_state="merged",
                mr_url="https://gitlab.example.com/g/p/-/merge_requests/42",
                mr_ref="!42",
                ci_state="success",
            ),
        )
        capsys.readouterr()
        assert cli(config, "status", "TASK-squash", "--json", "--forge") == 0
        payload = json.loads(capsys.readouterr().out)
        wt = payload["worktrees"][0]
        assert wt["merged"] is True
        assert wt["merged_via"] == "forge"
        assert wt["forge"]["mr_ref"] == "!42"
        assert wt["forge"]["ci_state"] == "success"

    def test_status_json_oneline_exclusive(self, config, capsys):
        try:
            code = cli(config, "status", "x", "--json", "--oneline")
        except SystemExit as e:
            code = e.code
        assert code == 2


class TestAddRepo:
    def test_add_repo(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "add-repo", "task-x", "repo-beta") == 0
        assert "Added repo-beta to task task-x" in capsys.readouterr().out
        assert (cli_config.tasks_dir / "task-x" / "repo-beta" / ".git").exists()

    def test_add_repo_already_present(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "add-repo", "task-x", "repo-alpha") == 0
        assert "already in task" in capsys.readouterr().out

    def test_add_repo_missing_task(self, config, sample_repos, capsys):
        assert cli(config, "add-repo", "nope", "repo-alpha") == 1
        assert "no such task" in capsys.readouterr().err

    def test_add_repo_unknown_repo(self, cli_config, capsys):
        cli(cli_config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "add-repo", "task-x", "no-such-repo") == 1
        assert "unknown repo(s)" in capsys.readouterr().err


class TestRepos:
    def test_repos(self, config, sample_repos, capsys):
        assert cli(config, "repos") == 0
        assert capsys.readouterr().out.splitlines() == ["repo-alpha", "repo-beta", "repo-gamma"]

    def test_repos_empty(self, config, capsys):
        assert cli(config, "repos") == 0
        assert capsys.readouterr().out == ""


class TestParser:
    def test_no_command_exits(self, config):
        with pytest.raises(SystemExit):
            run_cli([], config=config)

    def test_version_exits(self, config, capsys):
        with pytest.raises(SystemExit) as exc_info:
            run_cli(["--version"], config=config)
        assert exc_info.value.code == 0
