# Installation Guide

Complete installation instructions for tasktree-manager across all platforms.

## Table of Contents

- [System Requirements](#system-requirements)
- [Installation Methods](#installation-methods)
  - [pipx (Recommended)](#pipx-recommended)
  - [pip (User Install)](#pip-user-install)
  - [pip (Virtual Environment)](#pip-virtual-environment)
  - [From Source](#from-source)
- [Platform-Specific Instructions](#platform-specific-instructions)
  - [macOS](#macos)
  - [Linux](#linux)
  - [Windows (WSL2)](#windows-wsl2)
- [Post-Installation](#post-installation)
- [Verification](#verification)
- [Upgrading](#upgrading)
- [Uninstalling](#uninstalling)

## System Requirements

Before installing tasktree-manager, ensure your system meets these requirements:

- **Python**: 3.10 or higher (3.13+ recommended for best performance)
- **Git**: 2.0 or higher
- **Terminal**: 256-color support required
- **Operating System**: Unix-like system (macOS, Linux, or WSL2 on Windows)

## Installation Methods

### pipx (Recommended)

[pipx](https://pipx.pypa.io/) installs Python applications in isolated environments, preventing dependency conflicts.

```bash
# Install pipx if not already installed
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install tasktree-manager
pipx install tasktree-manager
```

**Benefits:**
- Isolated from system Python packages
- Easy upgrades and uninstalls
- Automatic PATH configuration

### pip (User Install)

Install tasktree-manager for your user account only:

```bash
pip install --user tasktree-manager
```

**Note:** Ensure `~/.local/bin` (Linux) or `~/Library/Python/3.x/bin` (macOS) is in your PATH.

### pip (Virtual Environment)

For project-specific installations:

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install tasktree-manager
pip install tasktree-manager
```

### From Source

For development or to use the latest unreleased features:

```bash
# Clone the repository
git clone https://github.com/yourusername/tasktree-manager.git
cd tasktree-manager

# Option 1: Using mise (recommended for development)
curl https://mise.run | sh
mise install
mise run install

# Option 2: Using pip
pip install -e .
```

## Platform-Specific Instructions

### macOS

#### Prerequisites

1. **Install Homebrew** (if not already installed):
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **Install Python**:
   ```bash
   brew install python@3.13
   ```

3. **Install Git** (if not already installed):
   ```bash
   brew install git
   ```

#### Terminal Configuration

macOS Terminal.app and iTerm2 both support 256 colors by default. To verify:

```bash
echo $TERM
# Should show: xterm-256color or similar
```

If colors aren't working:
- **Terminal.app**: Preferences → Profiles → Advanced → Declare terminal as: `xterm-256color`
- **iTerm2**: Preferences → Profiles → Terminal → Report Terminal Type: `xterm-256color`

#### Install tasktree-manager

```bash
# Using pipx (recommended)
brew install pipx
pipx ensurepath
pipx install tasktree-manager
```

### Linux

#### Debian/Ubuntu

```bash
# Update package list
sudo apt update

# Install Python 3.10+ and pip
sudo apt install python3 python3-pip git

# Install pipx
sudo apt install pipx
pipx ensurepath

# Install tasktree-manager
pipx install tasktree-manager
```

#### Fedora/RHEL/CentOS

```bash
# Install Python and Git
sudo dnf install python3 python3-pip git

# Install pipx
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install tasktree-manager
pipx install tasktree-manager
```

#### Arch Linux

```bash
# Install Python and Git
sudo pacman -S python python-pip git

# Install pipx
sudo pacman -S python-pipx

# Install tasktree-manager
pipx install tasktree-manager
```

#### Terminal Configuration

Most Linux terminals support 256 colors. Verify with:

```bash
echo $TERM
# Should include "256color"
```

If needed, add to `~/.bashrc` or `~/.zshrc`:

```bash
export TERM=xterm-256color
```

### Windows (WSL2)

tasktree-manager requires a Unix-like environment. On Windows, use WSL2:

#### 1. Install WSL2

Open PowerShell as Administrator:

```powershell
wsl --install
```

Restart your computer when prompted.

#### 2. Set Up Ubuntu

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install Python and Git
sudo apt install python3 python3-pip git

# Install pipx
sudo apt install pipx
pipx ensurepath
```

#### 3. Install tasktree-manager

```bash
pipx install tasktree-manager
```

#### Windows Terminal Configuration

For best results, use [Windows Terminal](https://aka.ms/terminal):

1. Install from Microsoft Store
2. Set default profile to Ubuntu (WSL2)
3. Configure fonts: Settings → Profiles → Ubuntu → Appearance → Font face: "Cascadia Code"

#### Git Considerations

If using repositories on Windows filesystem (`/mnt/c/...`), Git operations may be slow. For best performance:

1. Store repositories in WSL2 filesystem (`~/repos`)
2. If you must use Windows paths, exclude from Windows Defender:
   ```powershell
   # In PowerShell (as Administrator)
   Add-MpPreference -ExclusionPath "C:\Users\YourName\repos"
   ```

## Post-Installation

### First Run

Launch tasktree-manager:

```bash
tasktree-manager
```

On first run, you'll see a configuration wizard (it appears when the repositories
directory, `~/repos` by default, does not exist yet; with `~/repos` already present
the defaults apply and no `config.toml` is written until you change a setting, such
as the theme):

#### Configuration Wizard

1. **Repositories Directory**:
   - Enter the path where your git repositories are located
   - Example: `~/repos` or `/Users/username/code`
   - This directory should contain subdirectories with `.git` folders

2. **Tasks Directory**:
   - Enter the path where task worktrees will be created
   - Example: `~/tasks` or `/Users/username/worktrees`
   - Will be created if it doesn't exist

3. **Confirmation**:
   - Configuration is saved to `~/.config/tasktree-manager/config.toml`
   - You can edit this file later (see [Configuration Reference](configuration.md))

### Directory Structure

After configuration, tasktree-manager expects:

```
~/repos/                    # Your git repositories (REPOS_DIR)
  ├── backend/.git
  ├── frontend/.git
  └── infrastructure/.git

~/tasks/                    # Task worktrees (TASKS_DIR)
  └── (created by tasktree-manager)

~/.config/tasktree-manager/ # Configuration
  └── config.toml
```

### Creating Your First Task

1. Press `n` (new task)
2. Enter task name (e.g., `FEAT-123`)
3. Enter base branch (e.g., `main` or `master`)
4. Filter and select repositories (use arrow keys and space)
5. Press "Create"

tasktree-manager will create worktrees in `~/tasks/FEAT-123/{repo-name}/` on branch `FEAT-123`.

## Verification

Verify your installation:

```bash
# Check tasktree-manager is installed
tasktree-manager --version
# Should output: tasktree-manager 0.1.0 (or later)

# Check tasktree-manager is in PATH
which tasktree-manager
# Should show path like: /Users/username/.local/bin/tasktree-manager

# Check Python version
python3 --version
# Should be 3.10 or higher

# Check Git version
git --version
# Should be 2.0 or higher

# Check terminal colors
tput colors
# Should output: 256
```

### Troubleshooting Verification

If `tasktree-manager --version` fails:

**"command not found":**
- pipx: Run `pipx ensurepath` and restart your terminal
- pip: Add to PATH (see [Troubleshooting Guide](troubleshooting.md))

**"No module named 'textual'":**
- Reinstall: `pipx reinstall tasktree-manager` or `pip install --force-reinstall tasktree-manager`

**Terminal doesn't support colors:**
- See platform-specific terminal configuration above

## Upgrading

### pipx

```bash
pipx upgrade tasktree-manager
```

### pip

```bash
pip install --upgrade tasktree-manager
```

### From Source

```bash
cd tasktree-manager
git pull
mise install  # or: pip install -e .
```

### Migration Notes

When upgrading between major versions, check [CHANGELOG.md](../CHANGELOG.md) for breaking changes.

Configuration files are backward compatible within minor versions (0.x.y).

## Uninstalling

### pipx

```bash
pipx uninstall tasktree-manager
```

### pip

```bash
pip uninstall tasktree-manager
```

### Cleanup

Optionally remove configuration and tasks:

```bash
# Remove configuration
rm -rf ~/.config/tasktree-manager

# WARNING: This deletes all task worktrees
# Back up any uncommitted work first!
rm -rf ~/tasks  # or your TASKS_DIR

# Note: Your original repositories in REPOS_DIR are NOT affected
```

### Preserving Data

To uninstall but keep your tasks:

1. Finish all tasks normally (press `d` in tasktree-manager)
2. Or manually push all branches:
   ```bash
   cd ~/tasks/TASK-NAME/repo-name
   git push origin TASK-NAME
   ```
3. Then uninstall

Your original repositories in `REPOS_DIR` are never modified by tasktree-manager and remain intact after uninstallation.

## Next Steps

- [User Guide](user-guide.md) - Learn tasktree-manager workflows and features
- [Configuration Reference](configuration.md) - Customize keybindings, themes, and settings
- [Troubleshooting Guide](troubleshooting.md) - Common issues and solutions
