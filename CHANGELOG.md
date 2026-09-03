# Changelog

All notable changes to tasktree-manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Search and filter functionality
- Task templates
- Task archiving
- JIRA/Linear integration
- Git hooks support
- Custom task metadata

## [2.12.1] - 2026-09-03

### Changed
- Align guides with deletion, config and platform behaviour
- **release**: Gate tag on lint and tests, derive version from tags

### Fixed
- **tui**: Install configured keybindings, safe worktree delete, markup-safe rows
- **config**: Keep env overrides out of config.toml and fail on bad TOML
- **services**: Harden task deletion, creation and archive safety


## [2.12.0] - 2026-07-31

### Added
- **tui**: Rename task display label with R


## [2.11.1] - 2026-07-31

### Fixed
- **tui**: Open editor in new terminal tab, drop Enter shell binding


## [2.11.0] - 2026-07-30

### Added
- Add agent dashboard, forge-aware safety, finish/status CLI

### Changed
- **cli**: Collapse multi-line f-string per ruff format


## [2.10.0] - 2026-07-23

### Added
- **cli**: Add headless CLI for task management


## [2.9.0] - 2026-07-14

### Added
- **app**: Move blocking git work off the UI thread

### Changed
- Format worktree settings call with ruff
- **app**: Extract Claude session preparation helper

### Fixed
- Address review findings in async refresh and hook merging
- Harden task/branch validation, hook merging, markup rendering


## [2.8.0] - 2026-07-14

### Added
- **claude**: Per-repo Claude memory for worktree sessions

### Changed
- Release only when semantic-release bumps the version


## [2.7.2] - 2026-07-13

### Changed
- Ignore uv.lock


## [2.7.1] - 2026-07-13

### Changed
- **tests**: Format new test classes with ruff


## [2.7.0] - 2026-07-13

### Added
- **ui**: Design-system themes, layered panels, theme cycling

### Fixed
- **claude**: Copy repo CLAUDE.md into worktrees instead of stub
- **worktree**: Base new worktrees on origin base branch


## [2.6.0] - 2026-07-13

### Changed
- Hunk diff viewer, shared Claude memory pool, repo filter fix (#8)


## [2.5.0] - 2026-06-10

### Added
- Searchable app actions in the command palette (#7)


## [2.4.0] - 2026-06-10

### Added
- Context-sensitive footer showing the focused panel's keys (#6)


## [2.3.0] - 2026-06-10

### Added
- Add task cloning, worktree deletion, and non-blocking git ops (#4)

### Fixed
- Honor git timeout, real status codes, non-blocking delete (#5)


## [2.2.0] - 2026-03-06

### Added
- Add periodic auto-refresh for git status with selection preserv… (#3)


## [2.1.0] - 2026-02-10

### Added
- Add context-aware info panel with task summary and focus-driven updates
- Add Claude session status monitoring with Ghostty integration

### Changed
- Update example task names in README and user guide


## [2.0.1] - 2026-02-07

### Fixed
- Auto-generate changelog from conventional commits


## [2.0.0] - 2026-02-07

### Changed
- **BREAKING**: CLI command renamed from `tasktree` to `tasktree-manager`
- **BREAKING**: Config directory moved from `~/.config/tasktree/` to `~/.config/tasktree-manager/`
- Renamed Python module from `tasktree` to `tasktree_manager` for PyPI consistency
- Renamed GitHub repository to `tasktree-manager`
- Updated all documentation, CI workflows, and build configuration


## [1.0.0] - 2026-02-07

### Added
- 

### Changed
- 

### Fixed
- 


## [0.2.0] - TBD

### Added
- Config file support (`~/.config/tasktree-manager/config.toml`)
- Custom keybindings configuration (14 customizable actions)
- Selection state preservation when returning from lazygit or shell
- Parallel git operations (push/pull all worktrees simultaneously)
- Loading indicators for async operations
- 7 built-in themes (textual-dark, textual-light, nord, gruvbox, tokyo-night, monokai, dracula)
- Theme switcher via Command Palette (Ctrl+P)
- Environment variable overrides for configuration
- XDG Base Directory support for config location
- Comprehensive documentation:
  - Installation guide with platform-specific instructions
  - Configuration reference with all options documented
  - User guide with workflows and best practices
  - Troubleshooting guide with common issues and solutions
- CHANGELOG.md for version history tracking

### Changed
- Migrated from custom theming to Textual's built-in design tokens
- Improved modal animations with entrance effects
- Enhanced safety checks before task deletion
- Better error handling and user feedback
- Recursive repository scanning in REPOS_DIR

### Fixed
- Theme persistence across sessions
- Configuration precedence (env vars → config file → defaults)
- Modal rendering performance

## [0.1.0] - 2026-01-XX

### Added
- Initial release
- Task-based worktree management
- 3-panel TUI interface (tasks, worktrees, status)
- Create/delete tasks with multiple repositories
- Add repositories to existing tasks
- Git status display for worktrees
- Integration with lazygit
- Shell access in worktrees
- Push/pull operations
- Safety checks for task deletion
- Dirty task indicators
- Real-time status updates
- Basic configuration (REPOS_DIR, TASKS_DIR)
- Setup wizard for first-time configuration
- 228 tests with pytest

### Technical
- Built with Textual 7.0+
- Python 3.10+ support
- Git 2.0+ integration
- Cross-platform (macOS, Linux, WSL2)

---

## Version History

- **0.2.0** - Configuration system, custom keybindings, themes, comprehensive documentation
- **0.1.0** - Initial release with core functionality

## Upgrade Notes

### From 0.1.0 to 0.2.0

**Configuration:**
- Old: Configuration via environment variables only
- New: Config file at `~/.config/tasktree-manager/config.toml` (auto-created on first run)
- Migration: Environment variables still work and override config file

**Themes:**
- Old: Single default theme
- New: 7 themes available via Ctrl+P
- Theme preference saved to config file

**Keybindings:**
- Old: Hardcoded keybindings
- New: Customizable via `[keybindings]` section in config.toml
- Default keybindings unchanged

**No breaking changes** - 0.1.0 workflows continue to work in 0.2.0.

## Links

- [Repository](https://github.com/yourusername/tasktree-manager)
- [Documentation](docs/)
- [Issue Tracker](https://github.com/yourusername/tasktree-manager/issues)
- [Roadmap](ROADMAP.md)
