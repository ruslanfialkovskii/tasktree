"""Setup wizard for first-time configuration."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class SetupModal(ModalScreen[tuple[Path, Path] | None]):
    """Modal for first-time setup configuration.

    Dismisses with: (repos_dir, tasks_dir) tuple or None if cancelled.
    Escape cancels like the Cancel button (the app exits without setup).
    """

    BINDINGS = [Binding("escape", "cancel", "Close", show=False)]

    def action_cancel(self) -> None:
        """Dismiss the wizard as cancelled."""
        self.dismiss(None)

    DEFAULT_CSS = """
    SetupModal {
        align: center middle;
    }

    SetupModal > Container {
        width: 80;
        height: auto;
        max-height: 100%;
        overflow-y: auto;
        border: round $border;
        background: $panel;
        padding: 1 2;
    }

    SetupModal .modal-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    SetupModal .welcome-text {
        color: $text;
        margin-bottom: 1;
    }

    SetupModal .section-label {
        color: $foreground-muted;
        margin-top: 1;
        margin-bottom: 0;
    }

    SetupModal .help-text {
        color: $foreground-muted;
        margin-bottom: 1;
        text-style: italic;
    }

    SetupModal Input {
        background: $surface;
        border: round $border-blurred;
        color: $text;
        margin-bottom: 1;
    }

    SetupModal Input:focus {
        border: round $border;
    }

    SetupModal .button-row {
        align: center middle;
        margin-top: 1;
    }

    SetupModal Button {
        margin: 0 1;
        min-width: 12;
    }

    SetupModal .error-message {
        color: $text-error;
        text-align: center;
        margin-top: 1;
    }
    """

    # Kept short so the whole wizard (two inputs + buttons) fits an 80x24
    # terminal; the container scrolls if it still does not
    WELCOME_TEXT = (
        "Welcome! Pick where your git repositories live (REPOS_DIR) and where "
        "task worktrees go (TASKS_DIR). Saved to ~/.config/tasktree-manager/config.toml."
    )

    def __init__(self, *args, error_message: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.error_message = error_message

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("tasktree-manager Setup", classes="modal-title")
            yield Static(self.WELCOME_TEXT, classes="welcome-text")

            yield Label("Repositories Directory (e.g., ~/repos):", classes="section-label")
            yield Input(
                placeholder="e.g., /Users/username/repos",
                value=str(Path.home() / "repos"),
                id="repos-dir",
            )

            yield Label("Tasks Directory (e.g., ~/tasks):", classes="section-label")
            yield Input(
                placeholder="e.g., /Users/username/tasks",
                value=str(Path.home() / "tasks"),
                id="tasks-dir",
            )

            if self.error_message:
                yield Static(self.error_message, classes="error-message")

            with Horizontal(classes="button-row"):
                yield Button("Save & Continue", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "save-btn":
            self._save_config()

    def _save_config(self) -> None:
        """Validate and save configuration."""
        repos_input = self.query_one("#repos-dir", Input)
        tasks_input = self.query_one("#tasks-dir", Input)

        repos_dir = Path(repos_input.value.strip()).expanduser()
        tasks_dir = Path(tasks_input.value.strip()).expanduser()

        # Validate
        errors = []

        if not repos_dir.exists():
            errors.append(f"Repositories directory does not exist: {repos_dir}")
        elif not repos_dir.is_dir():
            errors.append(f"Repositories path is not a directory: {repos_dir}")

        if not repos_input.value.strip() or not tasks_input.value.strip():
            errors.append("Both directories are required")
        if not tasks_dir.parent.exists():
            errors.append(f"Parent directory does not exist: {tasks_dir.parent}")
        elif tasks_dir.exists() and not tasks_dir.is_dir():
            # Saving this would make every later launch crash in ensure_dirs()
            errors.append(f"Tasks path is not a directory: {tasks_dir}")

        # The task list treats every subdirectory of tasks_dir as a deletable
        # task, so the repos must never live inside it (or be it)
        repos_resolved, tasks_resolved = repos_dir.resolve(), tasks_dir.resolve()
        if (
            repos_resolved == tasks_resolved
            or repos_resolved.is_relative_to(tasks_resolved)
            or tasks_resolved.is_relative_to(repos_resolved)
        ):
            errors.append("Repositories and tasks directories must be separate (not nested)")

        if errors:
            self.error_message = "\n".join(errors)
            self.refresh(recompose=True)
            return

        # Save and dismiss
        self.dismiss((repos_dir, tasks_dir))
