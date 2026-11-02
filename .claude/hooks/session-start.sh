#!/bin/bash
# SessionStart hook for Claude Code cloud sessions.
#
# 1. Makes the tests and the linter runnable (Qt libraries + Python packages).
# 2. Makes sure the "ponytail" plugin is installed (declared in settings.json).
#
# Runs synchronously, only in cloud sessions, and is safe to run repeatedly.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# --- 1a. System libraries PyQt6 and OpenCV need, even headless (QT_QPA_PLATFORM=offscreen) ---
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi
missing=()
for pkg in libegl1 libgl1 libglib2.0-0 libxkbcommon0 libfontconfig1 libdbus-1-3; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq "${missing[@]}"
fi

# --- 1b. Python packages (system Python, so no hash file; pip is a no-op if satisfied) ---
python -m pip install -q -e ".[dev]"

# --- 2. ponytail plugin ---
# .claude/settings.json declares the marketplace (pinned to a release tag) and
# enables the plugin, but the CLI only clones a marketplace once it was added,
# so do that here. User scope keeps the repository untouched, and the container
# state is cached after this hook, so the install only happens once.
# A failure here must not block the session.
PONYTAIL_SOURCE="DietrichGebert/ponytail#v5.3.3"
if command -v claude >/dev/null 2>&1; then
  if ! claude plugin list 2>/dev/null | grep -q 'ponytail@ponytail'; then
    if ! { timeout 180 claude plugin marketplace add "$PONYTAIL_SOURCE" --scope user \
           && timeout 180 claude plugin install ponytail@ponytail --scope user; }; then
      echo "session-start: ponytail install failed, continuing without it" >&2
    fi
  fi
else
  echo "session-start: claude CLI not found, skipping ponytail" >&2
fi
