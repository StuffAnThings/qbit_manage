#!/usr/bin/env bash

# Detect if running in CI (e.g., GitHub Actions or pre-commit.ci)
if [[ -n "$GITHUB_ACTIONS" || -n "$CI" || -n "$PRE_COMMIT_CI" ]]; then
  IN_CI=true
else
  IN_CI=false
fi
# CI: For pull_request events, check if the PR itself changes VERSION.
# If not, run the develop version updater. This avoids relying on staged files.
if [[ "$IN_CI" == "true" ]]; then
  # Check if VERSION file contains "develop"
  if ! grep -q "develop" VERSION; then
    echo "VERSION file does not contain 'develop'. Skipping version update."
    exit 0
  fi

  # Check if VERSION differs from develop branch
  if git diff --quiet origin/develop...HEAD -- VERSION 2>/dev/null; then
    echo "VERSION file is the same as in develop branch. User didn't bump version, so updating develop version."
    source "$(dirname "$0")/update_develop_version.sh"
  else
    echo "VERSION file differs from develop branch. User already bumped version. Skipping update."
  fi
  exit 0
fi

# When running locally during an actual commit, skip if nothing is staged.
# In CI, pre-commit typically runs outside of a commit with no staged files,
# so we must not early-exit there.
if [[ "$IN_CI" != "true" && -z $(git diff --cached --name-only) ]]; then
  echo "There are no changes staged for commit. Skipping version update."
  exit 0
fi

# For local development, check if VERSION contains "develop"
if [[ "$IN_CI" != "true" ]]; then
  # Check if VERSION file contains "develop"
  if ! grep -q "develop" VERSION; then
    echo "VERSION file does not contain 'develop'. Skipping version update."
    exit 0
  # Check if the VERSION file is staged for modification
  elif git diff --cached --name-only | grep -q "VERSION"; then
    echo "The VERSION file is already modified. Skipping version update."
    exit 0
  elif git diff --name-only | grep -q "VERSION"; then
    echo "The VERSION file has unstaged changes. Please stage them before committing."
    exit 0
  fi
fi

# Check if we should run version update
if ! git diff --quiet origin/develop -- VERSION 2>/dev/null; then
  # VERSION differs from develop branch, so we should update it
  source "$(dirname "$0")/update_develop_version.sh"
elif [[ -n "$(git diff --cached --name-only)" ]] && ! git diff --cached --name-only | grep -q "VERSION"; then
  # There are staged changes but VERSION is not among them
  source "$(dirname "$0")/update_develop_version.sh"
elif ! git show --name-only HEAD | grep -q "VERSION"; then
  # VERSION doesn't exist in HEAD (new file)
  source "$(dirname "$0")/update_develop_version.sh"
fi
