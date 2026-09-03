# Troubleshooting Guide

Solutions for common issues, error messages, and platform-specific problems.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Installation Issues](#installation-issues)
- [Configuration Issues](#configuration-issues)
- [Runtime Issues](#runtime-issues)
- [Display Issues](#display-issues)
- [Platform-Specific Issues](#platform-specific-issues)
- [Git-Specific Issues](#git-specific-issues)
- [Advanced Diagnostics](#advanced-diagnostics)
- [Getting Help](#getting-help)
- [FAQ](#faq)
- [Recovery Procedures](#recovery-procedures)

## Quick Diagnostics

Run these commands to gather diagnostic information:

```bash
# Check tasktree-manager installation
tasktree-manager --version
which tasktree-manager

# Check Python and Git
python3 --version
git --version

# Check configuration
cat ~/.config/tasktree-manager/config.toml

# Check environment variables
env | grep -E '(REPOS_DIR|TASKS_DIR|TASKTREE_|EDITOR|SHELL)'

# Check terminal capabilities
echo $TERM
tput colors

# Run in dev mode with debug console
mise run dev  # If installed from source
```

## Installation Issues

### "tasktree-manager: command not found"

**Cause:** tasktree-manager is not in your PATH.

**Solutions:**

**If installed with pipx:**
```bash
# Ensure PATH is configured
pipx ensurepath

# Restart terminal or reload shell
source ~/.bashrc    # Bash
source ~/.zshrc     # Zsh

# Verify pipx bin directory is in PATH
echo $PATH | grep -o "[^:]*pipx[^:]*"

# If still not working, manually add to PATH
# Add to ~/.bashrc or ~/.zshrc:
export PATH="$HOME/.local/bin:$PATH"
```

**If installed with pip:**
```bash
# Find where pip installed it
pip show tasktree-manager | grep Location

# For user install, add to PATH
# Add to ~/.bashrc or ~/.zshrc:
export PATH="$HOME/.local/bin:$PATH"

# For macOS with Homebrew Python
export PATH="$HOME/Library/Python/3.13/bin:$PATH"
```

**If installed from source:**
```bash
# Ensure development installation worked
cd /path/to/tasktree-manager
pip install -e .

# Or use mise directly
mise run run
```

### "Python version not supported"

**Error message:**
```
tasktree-manager requires Python 3.10 or higher
```

**Solutions:**

**macOS (Homebrew):**
```bash
brew install python@3.13
brew link python@3.13

# Verify version
python3 --version
```

**Ubuntu/Debian:**
```bash
# Ubuntu 22.04+ has Python 3.10+
sudo apt update
sudo apt install python3.13 python3.13-pip

# For older Ubuntu, use deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-pip
```

**Using pyenv:**
```bash
# Install pyenv
curl https://pyenv.run | bash

# Install Python 3.13
pyenv install 3.13.0
pyenv global 3.13.0

# Reinstall tasktree-manager
pipx install tasktree-manager --python $(pyenv which python)
```

### "Permission denied"

**Error when installing:**
```
ERROR: Could not install packages due to an EnvironmentError: [Errno 13] Permission denied
```

**Solutions:**

**Don't use sudo with pip/pipx** - Install for your user:
```bash
# Remove any sudo-installed version
sudo pip uninstall tasktree-manager

# Install correctly
pipx install tasktree-manager
# or
pip install --user tasktree-manager
```

**If file permissions are wrong:**
```bash
# Fix ownership of Python directories
sudo chown -R $(whoami) ~/.local
sudo chown -R $(whoami) ~/.config
```

### "No module named 'textual'"

**Cause:** Dependencies not installed correctly.

**Solutions:**

```bash
# Reinstall with pipx (recommended)
pipx uninstall tasktree-manager
pipx install tasktree-manager

# Or reinstall with pip
pip uninstall tasktree-manager
pip install --user tasktree-manager

# Verify installation
pip show tasktree-manager
pip show textual
```

## Configuration Issues

### "No repositories found"

**Error message:**
```
No repositories found in REPOS_DIR
```

**Diagnosis:**
```bash
# Check REPOS_DIR setting
cat ~/.config/tasktree-manager/config.toml | grep repos_dir

# Check directory exists
ls -la ~/repos

# Check for .git directories
find ~/repos -name .git -type d
```

**Solutions:**

1. **Verify repos_dir exists and contains git repositories:**
   ```bash
   # Each repo should have a .git directory
   ls ~/repos/*/​.git
   ```

2. **Check configuration:**
   ```bash
   # Edit config.toml
   vim ~/.config/tasktree-manager/config.toml

   # Ensure repos_dir points to correct location
   repos_dir = "/Users/username/repos"
   ```

3. **Use environment variable override:**
   ```bash
   REPOS_DIR=~/code tasktree-manager
   ```

4. **Clone some repositories:**
   ```bash
   mkdir -p ~/repos
   cd ~/repos
   git clone https://github.com/user/repo.git
   ```

### "Worktree creation failed"

**Error message:**
```
Failed to create worktree: fatal: invalid reference: main
```

**Causes:**
- Base branch doesn't exist
- Repository is empty or corrupted
- Permission issues

**Solutions:**

1. **Verify base branch exists:**
   ```bash
   cd ~/repos/repo-name
   git branch -a | grep main
   ```

2. **Use correct base branch name:**
   - Change `git.default_base_branch` in config.toml
   - Or specify when creating task

3. **Check repository is not empty:**
   ```bash
   cd ~/repos/repo-name
   git log
   # Should show commits
   ```

4. **Fix permissions:**
   ```bash
   # Ensure you own the repos directory
   ls -la ~/repos
   # If owned by root or other user:
   sudo chown -R $(whoami) ~/repos
   ```

### "Config file not loaded"

**Symptoms:**
- Configuration changes not taking effect
- Setup wizard shows every time

**Diagnosis:**
```bash
# Check if config file exists
ls -la ~/.config/tasktree-manager/config.toml

# Check contents
cat ~/.config/tasktree-manager/config.toml

# Check for TOML syntax errors
python3 -c "import tomllib; tomllib.load(open('$HOME/.config/tasktree-manager/config.toml', 'rb'))"
```

**Solutions:**

1. **Environment variables override config file:**
   ```bash
   # Check for env vars
   env | grep REPOS_DIR
   env | grep TASKS_DIR

   # Unset if needed
   unset REPOS_DIR
   unset TASKS_DIR
   ```

2. **Fix TOML syntax:**
   ```bash
   # Common mistakes:
   # - Missing quotes around paths with spaces
   # - Incorrect section headers
   # - Typos in option names

   # Validate TOML online:
   # https://www.toml-lint.com/
   ```

3. **Regenerate config:**
   ```bash
   rm ~/.config/tasktree-manager/config.toml
   tasktree-manager  # Will show setup wizard
   ```

## Runtime Issues

### "Theme not changing"

**Symptoms:**
- Press Ctrl+P and select theme, but nothing changes
- Theme resets on restart

**Solutions:**

1. **Check config is being saved:**
   ```bash
   # Try changing theme via Ctrl+P
   # Then check config
   cat ~/.config/tasktree-manager/config.toml | grep theme
   ```

2. **Check file permissions:**
   ```bash
   ls -la ~/.config/tasktree-manager/config.toml
   # Should be writable by you

   # Fix if needed
   chmod 644 ~/.config/tasktree-manager/config.toml
   ```

3. **Check for environment variable override:**
   ```bash
   env | grep TASKTREE_THEME
   # If set, it overrides config file

   # Unset if needed
   unset TASKTREE_THEME
   ```

4. **Manually edit config:**
   ```bash
   vim ~/.config/tasktree-manager/config.toml

   # Add or update:
   [ui]
   theme = "nord"
   ```

### "Slow startup"

**Symptoms:**
- tasktree-manager takes 5+ seconds to start
- Long delay before UI appears

**Causes:**
- Many repositories (100+)
- Slow disk (network mount, HDD)
- Large git repositories

**Solutions:**

1. **Reduce repository count:**
   ```bash
   # Move inactive repos out of REPOS_DIR
   mkdir ~/repos-archive
   mv ~/repos/old-project ~/repos-archive/
   ```

2. **Use subdirectories:**
   ```bash
   # Organize repos into subdirectories
   ~/repos/
     ├── active/
     └── archive/

   # Point REPOS_DIR to active only
   repos_dir = "/Users/username/repos/active"
   ```

3. **Check disk performance:**
   ```bash
   # Test read speed
   dd if=~/repos/somefile of=/dev/null bs=1M count=100

   # If on network mount, move to local disk
   ```

4. **Avoid network mounts:**
   ```bash
   # Don't use REPOS_DIR on:
   # - NFS mounts
   # - SMB/CIFS shares
   # - Cloud storage (Dropbox, iCloud)
   ```

### "Git operations timeout"

**Error message:**
```
Git operation timed out after 30 seconds
```

**Solutions:**

1. **Increase timeout:**
   ```bash
   # Edit config.toml
   [git]
   timeout = 60  # or higher
   ```

2. **Check network connectivity:**
   ```bash
   # Test git fetch
   cd ~/repos/repo-name
   time git fetch origin

   # If slow, check:
   # - Internet connection
   # - VPN settings
   # - Proxy configuration
   ```

3. **Use manual operations:**
   ```bash
   # Instead of 'p' (push all), use lazygit per-repo
   # Press 'g' on each worktree
   ```

## Display Issues

### "Colors not showing"

**Symptoms:**
- Interface is all white/gray
- No syntax highlighting

**Diagnosis:**
```bash
# Check terminal color support
echo $TERM
tput colors  # Should output 256

# Test colors
curl -s https://gist.githubusercontent.com/HaleTom/89ffe32783f89f403bba96bd7bcd1263/raw/ | bash
```

**Solutions:**

1. **Set TERM correctly:**
   ```bash
   # Add to ~/.bashrc or ~/.zshrc
   export TERM=xterm-256color

   # Reload shell
   source ~/.bashrc
   ```

2. **Terminal app configuration:**

   **iTerm2 (macOS):**
   - Preferences → Profiles → Terminal
   - Report Terminal Type: `xterm-256color`

   **Terminal.app (macOS):**
   - Preferences → Profiles → Advanced
   - Declare terminal as: `xterm-256color`

   **GNOME Terminal (Linux):**
   - Usually works out of the box
   - If not, try: `TERM=xterm-256color tasktree-manager`

3. **Try different terminal:**
   ```bash
   # Modern terminals with good color support:
   # - Alacritty
   # - Kitty
   # - WezTerm
   # - iTerm2 (macOS)
   # - Windows Terminal (Windows/WSL)
   ```

### "Layout broken"

**Symptoms:**
- Panels overlap
- Text wrapping incorrectly
- Scrollbars in wrong place

**Solutions:**

1. **Increase terminal size:**
   ```bash
   # tasktree-manager requires minimum terminal size
   # Recommended: 80x24 minimum, 120x40 for comfort

   # Check current size
   tput cols  # Width
   tput lines # Height
   ```

2. **Resize terminal window:**
   - Make terminal window larger
   - Press Ctrl+L or 'r' to refresh

3. **Font issues:**
   - Use monospace font
   - Avoid fonts with variable widths
   - Recommended: Cascadia Code, Fira Code, JetBrains Mono

### "Unicode characters broken"

**Symptoms:**
- Box drawing characters show as `?` or `â`
- Arrows show incorrectly

**Solutions:**

1. **Check locale:**
   ```bash
   locale
   # Should show UTF-8
   # e.g., LANG=en_US.UTF-8

   # If not, add to ~/.bashrc or ~/.zshrc
   export LANG=en_US.UTF-8
   export LC_ALL=en_US.UTF-8
   ```

2. **Install UTF-8 locale:**
   ```bash
   # Ubuntu/Debian
   sudo locale-gen en_US.UTF-8
   sudo update-locale LANG=en_US.UTF-8
   ```

3. **Use font with Unicode support:**
   - Install Nerd Fonts or similar
   - Configure terminal to use that font

## Platform-Specific Issues

### macOS

#### "Python not found"

**Solution:**
```bash
# Install Xcode Command Line Tools
xcode-select --install

# Install Python via Homebrew
brew install python@3.13
```

#### "Operation not permitted"

**Error:**
```
Operation not permitted
```

**Cause:** macOS security restrictions.

**Solution:**
1. System Preferences → Security & Privacy
2. Privacy tab → Full Disk Access
3. Add Terminal.app or iTerm2

#### "Lazygit not found"

```bash
# Install with Homebrew
brew install lazygit

# Verify
which lazygit
lazygit --version
```

### Linux

#### "DBus error"

**Error:**
```
Failed to connect to DBus
```

**Cause:** Running in minimal environment without X11/Wayland.

**Solution:**
```bash
# Usually safe to ignore for TUI apps
# If it causes crashes, try:
export NO_AT_BRIDGE=1

# Or run in tmux/screen
tmux
tasktree-manager
```

#### "Terminal not recognized"

**Error:**
```
Terminal type not recognized
```

**Solution:**
```bash
# Install ncurses terminfo
sudo apt install ncurses-term  # Debian/Ubuntu
sudo dnf install ncurses-term  # Fedora

# Or set TERM manually
export TERM=xterm-256color
```

### Windows (WSL2)

#### "Path translation errors"

**Symptoms:**
- Paths like `/mnt/c/...` cause issues
- "Directory not found" errors

**Solution:**
```bash
# Use WSL filesystem, not Windows drives
# Good: ~/repos → /home/username/repos
# Bad: /mnt/c/Users/username/repos

# Move repos to WSL
mkdir -p ~/repos
mv /mnt/c/Users/username/code/* ~/repos/

# Update config
repos_dir = "/home/username/repos"
```

#### "Git operations slow"

**Cause:** Accessing Windows filesystem from WSL2.

**Solution:**
```bash
# Store repos in WSL filesystem
# Access Windows files only when necessary

# If must use Windows paths:
# 1. Exclude from Windows Defender (PowerShell as Admin):
Add-MpPreference -ExclusionPath "C:\Users\YourName\repos"

# 2. Use WSL2's /etc/wsl.conf for better mounting
sudo vim /etc/wsl.conf
# Add:
[automount]
options = "metadata,umask=22,fmask=11"

# Restart WSL
wsl --shutdown
```

#### "Terminal colors wrong"

**Solution:**
```bash
# Use Windows Terminal (not CMD or PowerShell)
# Download from Microsoft Store

# Configure Windows Terminal:
# Settings → Profiles → Ubuntu → Appearance
# Color scheme: Campbell / One Half Dark / Tango Dark
```

## Git-Specific Issues

### Task branch already exists

Creating a task whose branch already exists in a repo (left behind by an earlier
task, or created by hand) is not an error: the worktree is created **on the existing
branch as-is**, keeping every commit on it. The base branch you enter is ignored for
that repo.

**Error you can still hit:**
```
fatal: 'FEAT-123' is already checked out at '/Users/you/repos/repo-name'
```

**Cause:** the branch is checked out in the main repository (or another worktree);
git allows a branch in only one worktree at a time.

**Solution:**
```bash
cd ~/repos/repo-name
git switch main            # move the main checkout off the task branch
# then retry the task creation / add-repo
```

To start the task fresh from the base branch instead, delete the old branch first:
```bash
git branch -d FEAT-123  # If merged
git branch -D FEAT-123  # Force delete (loses its unmerged commits)
```

### "Detached HEAD state"

**Error in status panel:**
```
HEAD detached at abc1234
```

**Cause:** Worktree is not on a branch.

**Solution:**
```bash
# Open worktree in a new terminal tab
Press o

# Create/checkout branch
git checkout -b FEAT-123
# or
git checkout FEAT-123

exit
```

### "Worktree locked"

**Error:**
```
fatal: 'worktree' is locked
```

**Cause:** Git lock file from crashed operation.

**Solution:**
```bash
# Find the worktree
cd ~/repos/repo-name
git worktree list

# Remove lock
rm ~/tasks/TASK-NAME/repo-name/.git/worktrees/*/locked

# Or remove entire worktree
git worktree remove ~/tasks/TASK-NAME/repo-name

# Then recreate task in tasktree-manager
```

## Advanced Diagnostics

### Debug Mode with Dev Console

If installed from source:

```bash
cd /path/to/tasktree-manager
mise run dev
```

This opens tasktree-manager with Textual DevTools console showing:
- Widget tree
- CSS inspection
- Log messages
- Error details

### Manual Git Status Check

```bash
# Check git status for a worktree
cd ~/tasks/TASK-NAME/repo-name
git status
git branch -vv  # Show tracking info

# Check worktree list
cd ~/repos/repo-name
git worktree list
```

### Directory Permissions

```bash
# Check ownership and permissions
ls -la ~/.config/tasktree-manager
ls -la ~/repos
ls -la ~/tasks

# Fix ownership
sudo chown -R $(whoami):$(id -gn) ~/.config/tasktree-manager
sudo chown -R $(whoami):$(id -gn) ~/tasks

# Fix permissions
chmod -R u+rw ~/.config/tasktree-manager
chmod -R u+rwx ~/tasks
```

### Configuration Validation

```bash
# Check TOML syntax
python3 -c "
import tomllib
with open('$HOME/.config/tasktree-manager/config.toml', 'rb') as f:
    print(tomllib.load(f))
"

# Check for environment variable overrides
env | grep -E '(REPOS|TASKS|TASKTREE)' | sort
```

## Getting Help

### Before Asking for Help

Gather this information:

1. **System info:**
   ```bash
   uname -a
   python3 --version
   git --version
   tasktree-manager --version
   echo $TERM
   ```

2. **Configuration:**
   ```bash
   cat ~/.config/tasktree-manager/config.toml
   env | grep -E '(REPOS|TASKS|TASKTREE|EDITOR|SHELL)'
   ```

3. **Error message:**
   - Full error text
   - Steps to reproduce
   - What you expected vs. what happened

### Where to Ask

- **Bug reports:** [GitHub Issues](https://github.com/yourusername/tasktree-manager/issues)
- **Questions:** [GitHub Discussions](https://github.com/yourusername/tasktree-manager/discussions)
- **Documentation issues:** File an issue with "docs:" prefix

### Bug Report Template

```markdown
**Environment:**
- OS: macOS 14.1 / Ubuntu 22.04 / Windows 11 WSL2
- Python: 3.13.0
- Git: 2.42.0
- tasktree-manager: 0.1.0

**Expected behavior:**
[What you expected to happen]

**Actual behavior:**
[What actually happened]

**Steps to reproduce:**
1. [First step]
2. [Second step]
3. [...]

**Error message:**
```
[Paste full error message]
```

**Configuration:**
```toml
[Paste relevant config.toml sections]
```
```

## FAQ

### Can I use tasktree-manager with existing worktrees?

No, tasktree-manager manages worktrees in `TASKS_DIR` only. Existing worktrees created with `git worktree` directly won't appear in tasktree-manager.

**Workaround:** Create tasks in tasktree-manager and manually copy your work to the new worktrees.

### Does tasktree-manager modify my main repositories?

No. Repositories in `REPOS_DIR` are never modified. tasktree-manager only:
- Reads repository information
- Creates new branches (in worktrees, not main repo)
- The branches exist in main repo only after you push from worktrees

### Can I have multiple tasks for the same repository?

Yes! Each task creates its own worktree and branch:

```
~/tasks/
  ├── FEAT-123/
  │   └── backend/  (on branch FEAT-123)
  └── BUG-456/
      └── backend/  (on branch BUG-456)
```

### What happens to branches when I delete a task?

- Worktrees are removed from `TASKS_DIR`
- The local task branch is deleted from the main repository (`git branch -D`);
  the remaining diff is archived under `archive_dir` first
- Remote branches remain on GitHub/GitLab (if pushed)

**Manual cleanup (only for branches created outside tasktree):**
```bash
cd ~/repos/repo-name
git branch -d FEAT-123  # Delete local branch
```

### Can I use relative paths in config.toml?

No, use absolute paths or `~` expansion:

```toml
# Good
repos_dir = "/Users/username/repos"
repos_dir = "~/repos"

# Bad
repos_dir = "../repos"
repos_dir = "repos"
```

### Can I share my config with my team?

Yes, commit a template to your dotfiles:

```bash
# Create template
cp ~/.config/tasktree-manager/config.toml ~/dotfiles/tasktree-manager.toml

# Edit to use variables
repos_dir = "/Users/YOUR_USERNAME/repos"

# Each team member customizes their copy
```

**Note:** Don't share actual `REPOS_DIR` or `TASKS_DIR` between users.

## Recovery Procedures

### Corrupted Config File

```bash
# Backup current config
cp ~/.config/tasktree-manager/config.toml ~/.config/tasktree-manager/config.toml.backup

# Remove and regenerate
rm ~/.config/tasktree-manager/config.toml
tasktree-manager  # Setup wizard appears
```

### Stuck Worktrees

If worktrees can't be deleted via tasktree-manager:

```bash
# Find all worktrees for a repo
cd ~/repos/repo-name
git worktree list

# Remove specific worktree
git worktree remove ~/tasks/TASK-NAME/repo-name --force

# Clean up directory
rm -rf ~/tasks/TASK-NAME
```

### Lost Tasks

If `TASKS_DIR` was deleted but branches exist:

```bash
# See remote branches
cd ~/repos/repo-name
git branch -r

# Recreate task in tasktree-manager
tasktree-manager
Press n
Task name: FEAT-123
Base branch: FEAT-123  # Use existing branch
Select repos
Create

# Your work is in the remote branch
# Pull it down in the new worktree
Press o (new terminal tab)
git pull origin FEAT-123
```

### Complete Reset

Nuclear option - start fresh:

```bash
# WARNING: This removes all configuration and tasks
# Back up any uncommitted work first!

# Remove config
rm -rf ~/.config/tasktree-manager

# Remove all tasks (DANGEROUS - backs up recommended)
mv ~/tasks ~/tasks.backup

# Restart tasktree-manager
tasktree-manager  # Setup wizard
```

**Recovery:**
```bash
# If you made a mistake, restore
mv ~/tasks.backup ~/tasks
cp ~/tasks.backup/.config/tasktree-manager/config.toml ~/.config/tasktree-manager/
```

## Next Steps

- [User Guide](user-guide.md) - Learn workflows and features
- [Configuration Reference](configuration.md) - Customize settings
- [Installation Guide](installation.md) - Reinstall or upgrade
- [GitHub Issues](https://github.com/yourusername/tasktree-manager/issues) - Report bugs
