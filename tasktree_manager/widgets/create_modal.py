"""Modal widgets for creating tasks and adding repos."""

from typing import Any, ClassVar, TypeVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection

from ..services.task_manager import validate_branch_name, validate_task_name

T = TypeVar("T")


class ThemedModalScreen(ModalScreen[T]):
    """Base class for themed modal screens with typed dismiss results.

    Escape dismisses with ``CANCEL_RESULT`` — the same result the modal's
    Cancel/Close button produces.
    """

    BINDINGS = [Binding("escape", "cancel", "Close", show=False)]

    # Result returned when the modal is cancelled via Escape
    CANCEL_RESULT: ClassVar[Any] = None

    def action_cancel(self) -> None:
        """Dismiss the modal as cancelled."""
        self.dismiss(self.CANCEL_RESULT)

    DEFAULT_CSS = """
    ThemedModalScreen {
        align: center middle;
    }

    ThemedModalScreen > Container {
        width: 70;
        height: auto;
        max-height: 80%;
        border: round $border;
        background: $panel;
        padding: 1 2;
        offset: 0 3;
        opacity: 0;
    }

    ThemedModalScreen > Container.-visible {
        offset: 0 0;
        opacity: 1;
        transition: offset 200ms out_cubic, opacity 200ms out_cubic;
    }

    ThemedModalScreen .modal-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ThemedModalScreen .section-label {
        color: $foreground-muted;
        margin-top: 1;
        margin-bottom: 0;
    }

    ThemedModalScreen Input {
        background: $surface;
        border: round $border-blurred;
        color: $text;
        margin-bottom: 1;
    }

    ThemedModalScreen Input:focus {
        border: round $border;
    }

    ThemedModalScreen SelectionList {
        height: 12;
        margin-bottom: 1;
        background: $surface;
        border: round $border-blurred;
    }

    ThemedModalScreen SelectionList:focus {
        border: round $border;
    }

    ThemedModalScreen .button-row {
        align: center middle;
        margin-top: 1;
    }

    ThemedModalScreen Button {
        margin: 0 1;
        min-width: 12;
    }

    ThemedModalScreen .help-text {
        color: $text;
        margin-bottom: 1;
    }

    ThemedModalScreen .modal-message {
        text-align: center;
        color: $text;
        margin-bottom: 1;
    }
    """

    def on_mount(self) -> None:
        """Trigger entrance animation."""
        container = self.query_one(Container)
        container.add_class("-visible")


class RepoFilterMixin:
    """Search-filter + selection tracking for a repo ``SelectionList``.

    The repo list is rebuilt from scratch on every search keystroke, so the
    selected state cannot live solely in the widget. ``selected_repos`` is the
    source of truth and this mixin keeps it in sync as the visible options
    change, so selections made before (or under) a previous search survive.
    """

    available_repos: list[str]
    selected_repos: set[str]

    def _reset_visible_repos(self) -> None:
        """Mark every available repo as visible (no active filter)."""
        self._visible_repos: set[str] = set(self.available_repos)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "repo-search":
            self._filter_repos(event.value)

    def _filter_repos(self, search_term: str) -> None:
        """Rebuild the repo list to show only repos matching ``search_term``."""
        repo_list = self.query_one("#repo-list", SelectionList)

        # Case-insensitive substring match against the full repo path, so typing
        # a folder name like "mdp" shows every repo under that folder.
        search_lower = search_term.strip().lower()
        if search_lower:
            filtered = [repo for repo in self.available_repos if search_lower in repo.lower()]
        else:
            filtered = list(self.available_repos)
        self._visible_repos = set(filtered)

        # Clear and rebuild the list, restoring selection state from the
        # source-of-truth set.
        repo_list.clear_options()
        for repo in filtered:
            repo_list.add_option(
                Selection(escape(repo), repo, initial_state=repo in self.selected_repos)
            )

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        """Reconcile selection changes, scoped to the currently visible repos.

        Only repos in the active filter can have their state toggled here, so
        selections outside the filter are preserved untouched.
        """
        if event.selection_list.id != "repo-list":
            return
        selected_now = set(event.selection_list.selected)
        self.selected_repos = (self.selected_repos - self._visible_repos) | selected_now


class CreateTaskModal(RepoFilterMixin, ThemedModalScreen[tuple[str, list[str], str] | None]):
    """Modal for creating a new task.

    Dismisses with: (name, repos, branch) tuple or None if cancelled.
    """

    class TaskCreated(Message):
        """Message sent when a task is created."""

        def __init__(self, name: str, repos: list[str], base_branch: str):
            self.name = name
            self.repos = repos
            self.base_branch = base_branch
            super().__init__()

    def __init__(
        self,
        available_repos: list[str],
        *args,
        initial_repos: list[str] | None = None,
        initial_base_branch: str = "main",
        title: str = "Create New Task",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.available_repos = available_repos
        self.selected_repos: set[str] = set(initial_repos or [])
        self.initial_base_branch = initial_base_branch
        self.title_text = title
        self._reset_visible_repos()

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(escape(self.title_text), classes="modal-title")
            yield Label("Task Name:", classes="section-label")
            yield Input(placeholder="e.g., FEAT-123-new-feature", id="task-name")
            yield Label("Base Branch:", classes="section-label")
            yield Input(
                value=self.initial_base_branch,
                placeholder=self.initial_base_branch,
                id="base-branch",
            )
            yield Label("Search Repositories:", classes="section-label")
            yield Input(placeholder="Type to filter (e.g., ansible, postgres)...", id="repo-search")
            yield Label("Select Repositories:", classes="section-label")
            yield SelectionList[str](
                *[
                    Selection(escape(repo), repo, initial_state=repo in self.selected_repos)
                    for repo in self.available_repos
                ],
                id="repo-list",
            )
            with Horizontal(classes="button-row"):
                yield Button("Create", variant="primary", id="create-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "create-btn":
            self._create_task()

    def _create_task(self) -> None:
        """Create the task and dismiss modal."""
        name_input = self.query_one("#task-name", Input)
        branch_input = self.query_one("#base-branch", Input)

        name = name_input.value.strip()
        base_branch = branch_input.value.strip() or self.initial_base_branch
        selected_repos = list(self.selected_repos)

        # Same validation the TaskManager enforces, surfaced early in the UI
        error = validate_task_name(name) or validate_branch_name(base_branch)
        if error:
            self.notify(error, severity="error")
            return

        if not selected_repos:
            self.notify("Select at least one repository", severity="error")
            return

        self.dismiss((name, selected_repos, base_branch))


class AddRepoModal(RepoFilterMixin, ThemedModalScreen[tuple[list[str], str] | None]):
    """Modal for adding repos to an existing task.

    Dismisses with: (repos, branch) tuple or None if cancelled.
    """

    def __init__(
        self,
        task_name: str,
        available_repos: list[str],
        *args,
        initial_base_branch: str = "main",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.task_name = task_name
        self.available_repos = available_repos
        self.initial_base_branch = initial_base_branch
        self.selected_repos: set[str] = set()
        self._reset_visible_repos()

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(escape(f"Add Repos to: {self.task_name}"), classes="modal-title")
            yield Label("Base Branch:", classes="section-label")
            yield Input(
                value=self.initial_base_branch,
                placeholder=self.initial_base_branch,
                id="base-branch",
            )
            if self.available_repos:
                yield Label("Search Repositories:", classes="section-label")
                yield Input(
                    placeholder="Type to filter (e.g., ansible, postgres)...", id="repo-search"
                )
                yield Label("Select Repositories to Add:", classes="section-label")
                yield SelectionList[str](
                    *[Selection(escape(repo), repo) for repo in self.available_repos],
                    id="repo-list",
                )
            else:
                yield Static("No more repositories available to add")
            with Horizontal(classes="button-row"):
                yield Button("Add", variant="primary", id="add-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "add-btn":
            self._add_repos()

    def _add_repos(self) -> None:
        """Add repos and dismiss modal."""
        if not self.available_repos:
            self.dismiss(None)
            return

        branch_input = self.query_one("#base-branch", Input)

        base_branch = branch_input.value.strip() or self.initial_base_branch
        selected_repos = list(self.selected_repos)

        error = validate_branch_name(base_branch)
        if error:
            self.notify(error, severity="error")
            return

        if not selected_repos:
            self.notify("Select at least one repository", severity="error")
            return

        self.dismiss((selected_repos, base_branch))


class ConfirmModal(ThemedModalScreen[bool]):
    """Modal for confirming an action.

    Dismisses with: True if confirmed, False if cancelled.
    """

    CANCEL_RESULT: ClassVar[bool] = False

    DEFAULT_CSS = (
        ThemedModalScreen.DEFAULT_CSS
        + """
    ConfirmModal > Container {
        width: 60;
        border: round $error;
    }

    ConfirmModal .modal-title {
        color: $text-error;
    }
    """
    )

    def __init__(self, title: str, message: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_text = title
        self.message_text = message

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.title_text, classes="modal-title")
            yield Static(self.message_text, classes="modal-message")
            with Horizontal(classes="button-row"):
                yield Button("Confirm", variant="error", id="confirm-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(False)
        elif event.button.id == "confirm-btn":
            self.dismiss(True)


class SafeDeleteModal(ThemedModalScreen[str | None]):
    """Modal for safely deleting a task with safety warnings.

    Dismisses with: "push", "lazygit", "force", or None if cancelled.
    """

    DEFAULT_CSS = (
        ThemedModalScreen.DEFAULT_CSS
        + """
    SafeDeleteModal > Container {
        width: 70;
        height: auto;
        max-height: 90%;
        border: round $error;
    }

    SafeDeleteModal .modal-title {
        color: $text-error;
    }

    SafeDeleteModal .warning-section {
        margin-top: 1;
        margin-bottom: 1;
    }

    SafeDeleteModal .warning-header {
        color: $text-error;
        text-style: bold;
        margin-bottom: 0;
    }

    SafeDeleteModal .warning-item {
        color: $text;
        margin-left: 2;
    }

    SafeDeleteModal .scrollable-content {
        height: auto;
        max-height: 30;
        overflow-y: auto;
    }
    """
    )

    def __init__(self, task_name: str, safety_report, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_name = task_name
        self.safety_report = safety_report

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(escape(f"Delete Task: {self.task_name}"), classes="modal-title")
            yield Static("WARNING: Issues detected", classes="modal-message")

            # Build warnings content (repo names are escaped: they come from
            # the filesystem and may contain markup-significant brackets)
            warnings_content = ""

            if getattr(self.safety_report, "errors", None):
                warnings_content += "\n[bold red]Status unreadable (state unknown):[/]\n"
                for issue in self.safety_report.errors:
                    warnings_content += escape(f"  * {issue.repo_name} ({issue.details})") + "\n"

            if self.safety_report.has_unpushed():
                warnings_content += "\n[bold red]Unpushed commits:[/]\n"
                for issue in self.safety_report.unpushed:
                    warnings_content += escape(f"  * {issue.repo_name} ({issue.details})") + "\n"

            if self.safety_report.has_unmerged():
                warnings_content += "\n[bold red]Unmerged branches:[/]\n"
                for issue in self.safety_report.unmerged:
                    warnings_content += escape(f"  * {issue.repo_name} ({issue.details})") + "\n"

            if self.safety_report.has_dirty():
                warnings_content += "\n[bold red]Uncommitted changes:[/]\n"
                for issue in self.safety_report.dirty:
                    warnings_content += escape(f"  * {issue.repo_name} ({issue.details})") + "\n"

            if getattr(self.safety_report, "merged_via_forge", None):
                warnings_content += "\n[bold green]Merged remotely (squash/rebase):[/]\n"
                for issue in self.safety_report.merged_via_forge:
                    warnings_content += escape(f"  * {issue.repo_name} ({issue.details})") + "\n"

            yield Static(warnings_content.strip(), classes="scrollable-content")

            with Horizontal(classes="button-row"):
                yield Button("Push All", variant="primary", id="push-btn")
                yield Button("Open Lazygit", variant="default", id="lazygit-btn")
                yield Button("Force Delete", variant="error", id="force-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "push-btn":
            self.dismiss("push")
        elif event.button.id == "lazygit-btn":
            self.dismiss("lazygit")
        elif event.button.id == "force-btn":
            self.dismiss("force")


class RenameTaskModal(ThemedModalScreen[str | None]):
    """Prompt for a task's display alias (TUI label only).

    Dismisses with the new alias, "" to revert to the real name, or None
    when cancelled.
    """

    CANCEL_RESULT: ClassVar[None] = None

    def __init__(self, task_name: str, current_alias: str | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_name = task_name
        self.current_alias = current_alias

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Rename Task (display only)", classes="modal-title")
            yield Static(
                escape(f"Folder/branch stay '{self.task_name}'; empty input reverts."),
                classes="modal-message",
            )
            yield Input(
                value=self.current_alias or "",
                placeholder=self.task_name,
                id="rename-input",
            )
            with Horizontal(classes="button-row"):
                yield Button("Rename", variant="primary", id="rename-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#rename-input", Input).focus()

    def _submit(self) -> None:
        self.dismiss(self.query_one("#rename-input", Input).value.strip())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rename-btn":
            self._submit()
        elif event.button.id == "cancel-btn":
            self.dismiss(None)


class DispatchAgentModal(ThemedModalScreen[str | None]):
    """Prompt for dispatching a background Claude agent into a worktree.

    Dismisses with the prompt text, or None when cancelled/empty.
    """

    CANCEL_RESULT: ClassVar[None] = None

    def __init__(self, worktree_label: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worktree_label = worktree_label

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Dispatch Claude Agent", classes="modal-title")
            yield Static(escape(f"Target: {self.worktree_label}"), classes="modal-message")
            yield Input(placeholder="Prompt for the background session…", id="agent-prompt")
            with Horizontal(classes="button-row"):
                yield Button("Dispatch", variant="primary", id="dispatch-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#agent-prompt", Input).focus()

    def _submit(self) -> None:
        prompt = self.query_one("#agent-prompt", Input).value.strip()
        self.dismiss(prompt or None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dispatch-btn":
            self._submit()
        elif event.button.id == "cancel-btn":
            self.dismiss(None)


class PushResultModal(ThemedModalScreen[None]):
    """Modal showing results of push operation.

    Dismisses with: None (informational only).
    """

    DEFAULT_CSS = (
        ThemedModalScreen.DEFAULT_CSS
        + """
    PushResultModal > Container {
        width: 60;
    }
    """
    )

    def __init__(self, success_repos: list[str], failed_repos: list[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.success_repos = success_repos
        self.failed_repos = failed_repos

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Push Results", classes="modal-title")

            result_text = ""
            if self.success_repos:
                result_text += "[bold green]Successfully pushed:[/]\n"
                for repo in self.success_repos:
                    result_text += f"  [green]✓[/] {escape(repo)}\n"

            if self.failed_repos:
                if result_text:
                    result_text += "\n"
                result_text += "[bold red]Failed to push:[/]\n"
                for repo in self.failed_repos:
                    result_text += f"  [red]✗[/] {escape(repo)}\n"

            yield Static(result_text.strip(), classes="modal-message")

            with Horizontal(classes="button-row"):
                yield Button("Close", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss()


class HelpModal(ThemedModalScreen[None]):
    """Modal showing keybindings help and application info.

    Dismisses with: None (informational only).
    """

    DEFAULT_CSS = (
        ThemedModalScreen.DEFAULT_CSS
        + """
    HelpModal > Container {
        width: 70;
        max-height: 90%;
    }

    HelpModal .help-section {
        margin-bottom: 1;
    }

    HelpModal .help-section-title {
        color: $primary;
        text-style: bold;
        margin-bottom: 0;
    }

    HelpModal .help-content {
        color: $text;
        margin-left: 2;
    }

    HelpModal .help-key {
        color: $accent;
        text-style: bold;
    }

    HelpModal .help-desc {
        color: $text-muted;
    }

    HelpModal .help-info {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
        border-top: solid $primary;
        padding-top: 1;
    }

    HelpModal .scrollable-help {
        height: auto;
        max-height: 35;
        overflow-y: auto;
    }
    """
    )

    def __init__(
        self, keybindings: dict[str, str] | None = None, config_path: str = "", *args, **kwargs
    ):
        """Initialize help modal.

        Args:
            keybindings: Dictionary of action -> key mappings from config
            config_path: Path to config file for display
        """
        super().__init__(*args, **kwargs)
        self.keybindings = keybindings or {}
        self.config_path = config_path

    def _get_key(self, action: str, default: str) -> str:
        """Get the keybinding for an action, with formatting."""
        key = self.keybindings.get(action, default)
        # Format special keys for display
        key = key.replace("ctrl+", "Ctrl+").replace("shift+", "Shift+").replace("alt+", "Alt+")
        return key

    def _format_binding(self, action: str, default: str, description: str) -> str:
        """Format a single keybinding line."""
        key = self._get_key(action, default)
        # Pad key to align descriptions
        return f"  [bold cyan]{key:<12}[/] {description}"

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("tasktree-manager Help", classes="modal-title")

            # Build help content with actual keybindings
            help_content = self._build_help_content()

            with Container(classes="scrollable-help"):
                yield Static(help_content, classes="help-text")

            # Show config info at bottom
            info_text = self._build_info_text()
            yield Static(info_text, classes="help-info")

            with Horizontal(classes="button-row"):
                yield Button("Close", variant="primary", id="close-btn")

    def _build_help_content(self) -> str:
        """Build the help content with current keybindings."""
        sections = []

        # Navigation section
        nav_section = "[bold $primary]Navigation[/]\n"
        nav_section += self._format_binding("cursor_down", "j", "Move cursor down") + "\n"
        nav_section += self._format_binding("cursor_up", "k", "Move cursor up") + "\n"
        nav_section += self._format_binding("focus_next", "tab", "Switch to next panel") + "\n"
        nav_section += self._format_binding(
            "focus_previous", "shift+tab", "Switch to previous panel"
        )
        sections.append(nav_section)

        # Task management section
        task_section = "[bold $primary]Task Management[/]\n"
        task_section += self._format_binding("new_task", "n", "Create a new task") + "\n"
        task_section += (
            self._format_binding("clone_task", "y", "Clone current task (same repos, new name)")
            + "\n"
        )
        task_section += (
            self._format_binding("add_repo", "a", "Add repository to current task") + "\n"
        )
        task_section += (
            self._format_binding("delete_task", "d", "Delete/finish current task") + "\n"
        )
        task_section += self._format_binding(
            "rename_task", "R", "Rename task display label (folder/branch unchanged)"
        )
        sections.append(task_section)

        # Tools section
        tools_section = "[bold $primary]Tools[/]\n"
        tools_section += (
            self._format_binding("open_lazygit", "g", "Open lazygit in worktree") + "\n"
        )
        tools_section += (
            self._format_binding(
                "show_diff", "h", "Open hunk diff (task = all repos, worktree = one)"
            )
            + "\n"
        )
        tools_section += (
            self._format_binding("open_editor", "e", "Open editor in new terminal tab") + "\n"
        )
        tools_section += (
            self._format_binding(
                "open_claude_resume", "c", "Open Claude CLI (resume if session exists, else new)"
            )
            + "\n"
        )
        tools_section += (
            self._format_binding("open_claude_gui_code", "C", "Open Claude desktop on Code page")
            + "\n"
        )
        tools_section += self._format_binding(
            "dispatch_agent", "b", "Dispatch background Claude agent in worktree"
        )
        sections.append(tools_section)

        # Git operations section
        git_section = "[bold $primary]Git Operations[/]\n"
        git_section += self._format_binding("push_all", "p", "Push all worktrees in task") + "\n"
        git_section += self._format_binding("pull_all", "P", "Pull all worktrees in task") + "\n"
        git_section += self._format_binding("refresh", "r", "Refresh git status")
        sections.append(git_section)

        # General section
        general_section = "[bold $primary]General[/]\n"
        general_section += "  [bold cyan]Ctrl+P      [/] Open command palette (themes)\n"
        general_section += (
            self._format_binding("open_folder", "o", "Open folder in terminal") + "\n"
        )
        general_section += (
            self._format_binding("toggle_messages", "m", "Toggle activity log") + "\n"
        )
        general_section += self._format_binding("cycle_sort", "s", "Cycle task sort mode") + "\n"
        general_section += (
            self._format_binding("toggle_grouping", "S", "Toggle worktree grouping") + "\n"
        )
        general_section += self._format_binding("cycle_theme", "t", "Cycle color theme") + "\n"
        general_section += self._format_binding("help", "?", "Show this help") + "\n"
        general_section += self._format_binding("quit", "q", "Quit tasktree-manager")
        sections.append(general_section)

        # Tips section
        tips_section = "[bold $primary]Tips[/]\n"
        tips_section += "  • Use [bold]Ctrl+P[/] to quickly switch themes\n"
        tips_section += "  • Keybindings can be customized in config.toml\n"
        tips_section += "  • Press [bold]g[/] to resolve conflicts with lazygit\n"
        tips_section += "  • Tasks are stored in your tasks directory"
        sections.append(tips_section)

        return "\n\n".join(sections)

    def _build_info_text(self) -> str:
        """Build the info text showing config location."""
        info = "Config: "
        if self.config_path:
            info += f"{self.config_path}"
        else:
            info += "~/.config/tasktree-manager/config.toml"
        return info

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss()
