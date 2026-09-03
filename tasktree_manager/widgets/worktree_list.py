"""Worktree list widget for tasktree-manager."""

from typing import TYPE_CHECKING

from textual.content import Content
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option, OptionDoesNotExist

from ..services.models import Worktree

if TYPE_CHECKING:
    from ..services.forge import ForgeStatus

# One-cell badges as (glyph, style) pairs (single-cell BMP glyphs only —
# emoji break Rich cell-width math). Session vocabulary matches the TaskList
# hook indicators; ▣ avoids colliding with the git-clean ✓.
SESSION_BADGES = {
    "working": ("⟳", "magenta"),
    "needs_input": ("!", "yellow"),
    "ready": ("▣", "green"),
}
MR_BADGES = {
    "open": ("○", "green"),
    "merged": ("●", "magenta"),
    "closed": ("×", "red"),
}
CI_BADGES = {
    "running": ("◐", "yellow"),
    "success": ("✔", "green"),
    "failed": ("✘", "red"),
}


class WorktreeList(OptionList):
    """List of worktrees widget."""

    class WorktreeSelected(Message):
        """Message sent when a worktree is selected."""

        def __init__(self, worktree: Worktree | None):
            self.worktree = worktree
            super().__init__()

    class WorktreeHighlighted(Message):
        """Message sent when a worktree is highlighted."""

        def __init__(self, worktree: Worktree | None):
            self.worktree = worktree
            super().__init__()

    class GroupingChanged(Message):
        """Message sent when the grouping mode changes."""

        def __init__(self, enabled: bool):
            self.enabled = enabled
            super().__init__()

    def __init__(
        self,
        *args,
        context_bindings: list[tuple[str, str, str]] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.worktrees: list[Worktree] = []
        self._grouping_enabled: bool = False
        # Maps option index to worktree index (for handling headers)
        self._option_to_worktree: dict[int, int] = {}
        # Badge state keyed by str(worktree.path) — survives load_worktrees
        # reloads (same pattern as TaskList._claude_statuses)
        self._session_states: dict[str, str] = {}
        self._forge_statuses: dict[str, "ForgeStatus"] = {}
        # Column widths stored at load time so in-place prompt rebuilds align
        self._max_name_len: int = 0
        self._max_branch_len: int = 0
        # Footer-visible (key, app action, description) bindings shown while
        # this panel has focus; the keys also exist app-level (hidden) so
        # they keep working regardless of focus. Keys are popped first so a
        # context binding can override an OptionList default for that key.
        for key, action, description in context_bindings or []:
            self._bindings.key_to_bindings.pop(key, None)
            self._bindings.bind(key, f"app.{action}", description, show=True)

    @property
    def index(self) -> int | None:
        """Compatibility property - returns highlighted index."""
        return self.highlighted

    @index.setter
    def index(self, value: int | None) -> None:
        """Compatibility property - sets highlighted index."""
        self.highlighted = value

    def load_worktrees(
        self, worktrees: list[Worktree], preserve_selection: str | None = None
    ) -> None:
        """Load worktrees into the list.

        Args:
            worktrees: List of worktrees to load
            preserve_selection: Optional worktree name to preserve selection for
        """
        self.worktrees = worktrees
        self._option_to_worktree.clear()
        self.clear_options()

        if not worktrees:
            # Tell listeners the previous selection is gone; otherwise the
            # app keeps acting on a worktree that belongs to another task
            self._emit_highlighted()
            return

        # Calculate column widths for alignment
        self._max_name_len = max(len(wt.name) for wt in worktrees)
        self._max_branch_len = max(len(wt.branch or "unknown") for wt in worktrees)

        if self._grouping_enabled:
            self._load_grouped_worktrees(worktrees)
        else:
            self._load_flat_worktrees(worktrees)

        # Select item - preserve previous selection if specified
        if self.worktrees and self.option_count > 0:
            if preserve_selection:
                try:
                    # Use option ID to find the correct index
                    idx = self.get_option_index(preserve_selection)

                    # Defer highlight setting to next event loop cycle.
                    # Setting `highlighted` fires OptionHighlighted, whose
                    # handler emits WorktreeHighlighted exactly once.
                    def set_highlight():
                        self.highlighted = idx
                        self.scroll_to_highlight()

                    self.call_later(set_highlight)
                    return
                except OptionDoesNotExist:
                    self.action_first()
            else:
                self.action_first()

    def _load_flat_worktrees(self, worktrees: list[Worktree]) -> None:
        """Load worktrees without grouping."""
        for idx, worktree in enumerate(worktrees):
            option_idx = self.option_count
            self._option_to_worktree[option_idx] = idx
            self._add_worktree_option(worktree)

    def _load_grouped_worktrees(self, worktrees: list[Worktree]) -> None:
        """Load worktrees grouped by dirty/clean status."""
        dirty = [(i, wt) for i, wt in enumerate(worktrees) if wt.is_dirty]
        clean = [(i, wt) for i, wt in enumerate(worktrees) if not wt.is_dirty]

        # Add dirty section
        if dirty:
            self.add_option(Option("[bold red]Dirty[/]", disabled=True))
            for orig_idx, worktree in dirty:
                option_idx = self.option_count
                self._option_to_worktree[option_idx] = orig_idx
                self._add_worktree_option(worktree)

        # Add separator between groups if both exist
        if dirty and clean:
            self.add_option(None)  # None creates a separator

        # Add clean section
        if clean:
            self.add_option(Option("[bold green]Clean[/]", disabled=True))
            for orig_idx, worktree in clean:
                option_idx = self.option_count
                self._option_to_worktree[option_idx] = orig_idx
                self._add_worktree_option(worktree)

    def _build_prompt(self, worktree: Worktree) -> Content:
        """Compose one worktree row with badge cells and aligned columns.

        Built as Content rather than a markup string: git allows brackets in
        branch names, and Textual's markup parser would consume them.
        """
        branch = worktree.branch or "unknown"
        name_col = f"{worktree.name:<{self._max_name_len}}"
        branch_col = (f"{branch:<{self._max_branch_len}}", "dim")
        claude_indicator = ("◆", "blue") if worktree.has_claude_md else " "

        path_key = str(worktree.path)
        session = SESSION_BADGES.get(self._session_states.get(path_key, ""), " ")
        forge_status = self._forge_statuses.get(path_key)
        mr = MR_BADGES.get(forge_status.mr_state, " ") if forge_status else " "
        ci = CI_BADGES.get(forge_status.ci_state, " ") if forge_status else " "

        if worktree.is_dirty:
            git_status = (f"✗ {worktree.changed_files} files", "red")
        else:
            git_status = ("✓", "green")
        return Content.assemble(
            " ",
            session,
            claude_indicator,
            name_col,
            "  ",
            branch_col,
            "  ",
            mr,
            ci,
            "  ",
            git_status,
        )

    def _add_worktree_option(self, worktree: Worktree) -> None:
        """Add a single worktree option to the list."""
        self.add_option(Option(self._build_prompt(worktree), id=worktree.name))

    def refresh_status_badges(
        self,
        session_states: dict[str, str],
        forge_statuses: dict[str, "ForgeStatus"],
    ) -> None:
        """Update badge state and rebuild row prompts in place.

        Both dicts are keyed by str(worktree.path). Replacing prompts by
        option id works identically in flat and grouped modes (group headers
        and separators have no ids).
        """
        self._session_states = dict(session_states)
        self._forge_statuses = dict(forge_statuses)
        for worktree in self.worktrees:
            try:
                self.replace_option_prompt(worktree.name, self._build_prompt(worktree))
            except OptionDoesNotExist:
                pass

    def _emit_highlighted(self) -> None:
        """Emit a WorktreeHighlighted message for the current item."""
        worktree = self.get_selected_worktree()
        self.post_message(self.WorktreeHighlighted(worktree))

    def get_selected_worktree(self) -> Worktree | None:
        """Get the currently selected worktree."""
        if self.highlighted is None:
            return None

        # Use mapping if grouping is enabled
        if self._grouping_enabled:
            worktree_idx = self._option_to_worktree.get(self.highlighted)
            if worktree_idx is not None and 0 <= worktree_idx < len(self.worktrees):
                return self.worktrees[worktree_idx]
            return None

        # Flat mode - direct index mapping
        if 0 <= self.highlighted < len(self.worktrees):
            return self.worktrees[self.highlighted]
        return None

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Handle item highlight."""
        self._emit_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle item selection."""
        worktree = self.get_selected_worktree()
        self.post_message(self.WorktreeSelected(worktree))

    def clear_worktrees(self) -> None:
        """Clear the worktree list."""
        self.worktrees = []
        self._option_to_worktree.clear()
        self.clear_options()

    def toggle_grouping(self) -> None:
        """Toggle grouping mode and reload worktrees."""
        self._grouping_enabled = not self._grouping_enabled

        # Reload with current worktrees
        if self.worktrees:
            self.load_worktrees(list(self.worktrees))

        self.post_message(self.GroupingChanged(self._grouping_enabled))
