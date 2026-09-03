#!/usr/bin/env python3
"""
Version bumping script for tasktree-manager.

Reads the current version from pyproject.toml [tool.semantic_release] version,
calculates the new version, and updates pyproject.toml and CHANGELOG.md.
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"


def parse_args():
    parser = argparse.ArgumentParser(description="Bump version for tasktree-manager")
    parser.add_argument(
        "bump_type",
        nargs="?",
        choices=["patch", "minor", "major"],
        help="The type of version bump to perform (omit when using --set)",
    )
    parser.add_argument(
        "--set",
        dest="set_version",
        metavar="X.Y.Z",
        help="Write this exact version instead of bumping (used by the release "
        "workflow, which takes the version from semantic-release)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    parser.add_argument(
        "--auto-commit",
        action="store_true",
        help="Automatically commit changes after version bump",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push changes to remote after commit (implies --auto-commit)",
    )
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Create git tag for the new version (implies --auto-commit)",
    )
    parser.add_argument(
        "--changelog-message",
        type=str,
        help="Message to add to changelog (optional)",
        default="",
    )
    return parser.parse_args()


def get_current_version() -> str:
    """Get the current version from pyproject.toml [tool.semantic_release] version."""
    if not PYPROJECT_PATH.exists():
        raise FileNotFoundError(f"Could not find {PYPROJECT_PATH}")

    content = PYPROJECT_PATH.read_text()
    # Match version under [tool.semantic_release]
    in_section = False
    for line in content.splitlines():
        if line.strip() == "[tool.semantic_release]":
            in_section = True
            continue
        if in_section and line.strip().startswith("["):
            break
        if in_section:
            match = re.match(r'^version\s*=\s*"([^"]+)"', line.strip())
            if match:
                return match.group(1)

    raise ValueError("Could not find version in [tool.semantic_release] section of pyproject.toml")


def calculate_new_version(current_version: str, bump_type: str) -> str:
    """Calculate the new version based on bump type."""
    major, minor, patch = map(int, current_version.split("."))

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Unknown bump type: {bump_type}")


def update_pyproject_version(current_version: str, new_version: str, dry_run: bool = False) -> bool:
    """Update the version in pyproject.toml [tool.semantic_release] section."""
    content = PYPROJECT_PATH.read_text()
    lines = content.splitlines(keepends=True)

    in_section = False
    updated_lines = []
    changed = False

    for line in lines:
        stripped = line.strip()
        if stripped == "[tool.semantic_release]":
            in_section = True
        elif stripped.startswith("[") and in_section:
            in_section = False

        if in_section and re.match(
            r'^version\s*=\s*"' + re.escape(current_version) + '"', stripped
        ):
            line = line.replace(f'"{current_version}"', f'"{new_version}"')
            changed = True

        updated_lines.append(line)

    if not changed:
        print(f"No changes needed in {PYPROJECT_PATH}")
        return False

    if dry_run:
        print(f"Would update version in {PYPROJECT_PATH} from {current_version} to {new_version}")
    else:
        PYPROJECT_PATH.write_text("".join(updated_lines))
        print(f"Updated version in {PYPROJECT_PATH} from {current_version} to {new_version}")

    return True


def get_changelog_from_commits() -> str:
    """Generate changelog content from conventional commits since the last tag.

    Parses git log for conventional commit messages and groups them into
    Added, Changed, and Fixed sections.
    """
    # Find the last tag
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        last_tag = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        last_tag = ""

    # Get commits since last tag (or all commits if no tag)
    git_log_cmd = ["git", "log", "--pretty=format:%s"]
    if last_tag:
        git_log_cmd.append(f"{last_tag}..HEAD")

    try:
        result = subprocess.run(
            git_log_cmd,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        commits = result.stdout.strip().splitlines() if result.returncode == 0 else []
    except Exception:
        commits = []

    if not commits:
        return ""

    # Conventional commit type -> changelog section mapping
    added_types = {"feat"}
    fixed_types = {"fix"}
    changed_types = {"refactor", "perf", "style", "build", "ci", "chore", "docs", "test"}

    added = []
    changed = []
    fixed = []

    # Pattern: type(scope): description  or  type!: description  or  type: description
    commit_re = re.compile(r"^(\w+)(?:\(([^)]*)\))?(!)?:\s*(.+)$")

    for commit in commits:
        # Skip release commits
        if commit.startswith("chore(release):"):
            continue

        match = commit_re.match(commit)
        if match:
            ctype, scope, breaking, description = match.groups()
            # Capitalize first letter of description
            description = description[0].upper() + description[1:] if description else description
            scope_prefix = f"**{scope}**: " if scope else ""
            entry = f"- {scope_prefix}{description}"

            if breaking:
                entry = f"- **BREAKING**: {description}"
                changed.append(entry)
            elif ctype in added_types:
                added.append(entry)
            elif ctype in fixed_types:
                fixed.append(entry)
            elif ctype in changed_types:
                changed.append(entry)
            else:
                changed.append(entry)
        else:
            # Non-conventional commit — include as-is under Changed
            if commit.strip():
                changed.append(f"- {commit}")

    sections = []
    if added:
        sections.append("### Added\n" + "\n".join(added))
    if changed:
        sections.append("### Changed\n" + "\n".join(changed))
    if fixed:
        sections.append("### Fixed\n" + "\n".join(fixed))

    return "\n\n".join(sections)


def update_changelog(new_version: str, message: str = "", dry_run: bool = False) -> bool:
    """Update CHANGELOG.md with a new version entry."""
    if not CHANGELOG_PATH.exists():
        print("Warning: CHANGELOG.md does not exist, creating it")
        if not dry_run:
            CHANGELOG_PATH.write_text(
                "# Changelog\n\n"
                "All notable changes to tasktree-manager will be documented in this file.\n\n"
                "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),\n"
                "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).\n\n"
            )

    today = datetime.now().strftime("%Y-%m-%d")

    if message:
        new_entry = f"## [{new_version}] - {today}\n\n{message}\n\n"
    else:
        # Auto-generate from conventional commits
        changelog_content = get_changelog_from_commits()
        if changelog_content:
            new_entry = f"## [{new_version}] - {today}\n\n{changelog_content}\n\n"
        else:
            new_entry = f"## [{new_version}] - {today}\n\nNo notable changes.\n\n"

    if dry_run:
        print(f"Would add new entry to CHANGELOG.md for version {new_version}")
        return True

    content = CHANGELOG_PATH.read_text()

    # Insert after [Unreleased] section or at top after header
    if "## [Unreleased]" in content:
        # Find [Unreleased] section and insert new version after it
        # Look for the next ## heading after [Unreleased]
        pattern = r"(## \[Unreleased\].*?\n(?:.*?\n)*?)(\n## \[)"
        match = re.search(pattern, content)
        if match:
            insert_pos = match.start(2)
            updated = content[:insert_pos] + "\n" + new_entry + content[insert_pos:]
        else:
            # [Unreleased] is the last section, append after it
            updated = content + "\n" + new_entry
    elif "# Changelog" in content:
        # Insert after the header
        lines = content.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("# Changelog"):
                # Skip blank lines after header
                insert_idx = i + 1
                while insert_idx < len(lines) and lines[insert_idx].strip() == "":
                    insert_idx += 1
                # Skip description lines
                while (
                    insert_idx < len(lines)
                    and lines[insert_idx].strip()
                    and not lines[insert_idx].startswith("##")
                ):
                    insert_idx += 1
                while insert_idx < len(lines) and lines[insert_idx].strip() == "":
                    insert_idx += 1
                break
        lines.insert(insert_idx, new_entry)
        updated = "\n".join(lines)
    else:
        updated = new_entry + content

    CHANGELOG_PATH.write_text(updated)
    print(f"Updated CHANGELOG.md with entry for version {new_version}")
    return True


def commit_changes(new_version: str, push: bool = False, create_tag: bool = False) -> bool:
    """Commit version changes and optionally push and tag."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=PROJECT_ROOT,
        )

        subprocess.run(
            ["git", "add", "pyproject.toml", "CHANGELOG.md"], check=True, cwd=PROJECT_ROOT
        )

        commit_message = f"chore(release): bump version to {new_version}"
        subprocess.run(["git", "commit", "-m", commit_message], check=True, cwd=PROJECT_ROOT)
        print(f"Committed changes with message: '{commit_message}'")

        if create_tag:
            tag_name = f"v{new_version}"
            subprocess.run(
                ["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"],
                check=True,
                cwd=PROJECT_ROOT,
            )
            print(f"Created tag: {tag_name}")

        if push:
            subprocess.run(["git", "push", "origin", "HEAD"], check=True, cwd=PROJECT_ROOT)
            print("Pushed changes to origin")

            if create_tag:
                subprocess.run(
                    ["git", "push", "origin", f"v{new_version}"],
                    check=True,
                    cwd=PROJECT_ROOT,
                )
                print(f"Pushed tag v{new_version} to origin")

        return True

    except subprocess.CalledProcessError as e:
        print(f"Error during git operations: {e}")
        return False


def main():
    args = parse_args()

    if args.push or args.tag:
        args.auto_commit = True

    try:
        current_version = get_current_version()
        if args.set_version:
            if not re.fullmatch(r"\d+\.\d+\.\d+", args.set_version):
                raise ValueError(f"--set expects X.Y.Z, got {args.set_version!r}")
            new_version = args.set_version
        elif args.bump_type:
            new_version = calculate_new_version(current_version, args.bump_type)
        else:
            raise ValueError("either a bump type (patch/minor/major) or --set X.Y.Z is required")

        print(f"Current version: {current_version}")
        print(f"New version: {new_version}")

        pyproject_updated = update_pyproject_version(current_version, new_version, args.dry_run)
        changelog_updated = update_changelog(new_version, args.changelog_message, args.dry_run)

        if args.dry_run:
            print("\nDry run complete. No changes were made.")
            return 0

        if not pyproject_updated and not changelog_updated:
            print("\nNo changes were needed.")
            return 0

        print("\nVersion bump complete!")

        if args.auto_commit:
            if commit_changes(new_version, args.push, args.tag):
                print("\nGit operations completed successfully.")
            else:
                print("\nGit operations failed. Manual intervention required.")
                return 1
        else:
            print("\nNext steps:")
            print(f"1. Edit CHANGELOG.md to document changes in version {new_version}")
            print(
                f"2. Commit changes: git commit -am 'chore(release): bump version to {new_version}'"
            )
            print(f"3. Create tag: git tag -a v{new_version} -m 'Release v{new_version}'")
            print("4. Push changes: git push origin HEAD && git push origin --tags")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
