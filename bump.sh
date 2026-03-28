#!/usr/bin/env bash
# Usage: ./bump.sh [major|minor|patch]
# Bumps version in version.py, updates CHANGELOG.md, README.md, commits and tags.
set -euo pipefail

PART="${1:-patch}"
VERSION_FILE="version.py"
CHANGELOG_FILE="CHANGELOG.md"
README_FILE="README.md"

# ── Read current version ──────────────────────────────────────────────────────
CURRENT="$(grep -oP '(?<=__version__ = ")[^"]+' "$VERSION_FILE")"
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

# ── Bump ──────────────────────────────────────────────────────────────────────
case "$PART" in
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
    patch) PATCH=$((PATCH + 1)) ;;
    *)     echo "Usage: ./bump.sh [major|minor|patch]"; exit 1 ;;
esac

NEW="${MAJOR}.${MINOR}.${PATCH}"
TODAY="$(date +%Y-%m-%d)"

echo "Bumping $CURRENT → $NEW"

# ── Update version.py ─────────────────────────────────────────────────────────
sed -i "s/__version__ = \"${CURRENT}\"/__version__ = \"${NEW}\"/" "$VERSION_FILE"

# ── Update CHANGELOG.md — replace [Unreleased] header ────────────────────────
sed -i "s/## \[Unreleased\]/## [Unreleased]\n\n---\n\n## [${NEW}] — ${TODAY}/" "$CHANGELOG_FILE"

# ── Update README.md — version badge ─────────────────────────────────────────
sed -i "s/version-${CURRENT}-blue/version-${NEW}-blue/" "$README_FILE"

# ── Commit and tag ────────────────────────────────────────────────────────────
git add "$VERSION_FILE" "$CHANGELOG_FILE" "$README_FILE"
git commit -m "chore: bump version to ${NEW}"
git tag -a "v${NEW}" -m "Release v${NEW}"

echo "Done. Run 'git push && git push --tags' to publish."
