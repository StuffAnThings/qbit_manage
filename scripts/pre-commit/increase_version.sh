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
  BASE_REF="${GITHUB_BASE_REF:-}"

  # If BASE_REF not provided (e.g., pre-commit.ci), try to infer it
  if [[ -z "$BASE_REF" ]]; then
    # First try to get the default branch
    DEFAULT_BASE="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
    if [[ -z "$DEFAULT_BASE" ]]; then
      DEFAULT_BASE="$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' | head -n1)"
    fi

    # If current branch contains "develop", assume base is "develop"
    CURRENT_BRANCH_CI="${GITHUB_HEAD_REF:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')}"
    if [[ "$CURRENT_BRANCH_CI" == *"develop"* ]]; then
      BASE_REF="develop"
    elif grep -q "develop" VERSION 2>/dev/null; then
      # If VERSION contains "develop" but branch doesn't, still assume base is "develop"
      BASE_REF="develop"
    else
      BASE_REF="$DEFAULT_BASE"
    fi
  fi

  # Resolve a usable base ref
  CANDIDATES=()
  if [[ -n "$BASE_REF" ]]; then
    CANDIDATES+=("refs/remotes/origin/$BASE_REF")
    CANDIDATES+=("refs/heads/$BASE_REF")
  fi

  BASE_RESOLVED=""
  for ref in "${CANDIDATES[@]}"; do
    if git rev-parse --verify -q "$ref" >/dev/null; then
      BASE_RESOLVED="$ref"
      break
    fi
  done

  # Attempt to fetch the remote-tracking base if missing (handles shallow clones)
  if [[ -z "$BASE_RESOLVED" && -n "$BASE_REF" ]]; then
    git fetch --no-tags --depth=100 origin "refs/heads/$BASE_REF:refs/remotes/origin/$BASE_REF" >/dev/null 2>&1 || true
    if git rev-parse --verify -q "refs/remotes/origin/$BASE_REF" >/dev/null; then
      BASE_RESOLVED="refs/remotes/origin/$BASE_REF"
    elif git rev-parse --verify -q "refs/heads/$BASE_REF" >/dev/null; then
      BASE_RESOLVED="refs/heads/$BASE_REF"
    fi
  fi

  if [[ -z "$BASE_RESOLVED" ]]; then
    echo "Warning: Could not resolve PR base ref for '$BASE_REF'."
    echo "Hint: ensure the base ref is available (e.g., full fetch)."
    echo "Skipping version update because PR base could not be resolved."
    exit 0
  fi

  # Check if VERSION file contains "develop"
  if ! grep -q "develop" VERSION; then
    echo "VERSION file does not contain 'develop'. Skipping version update."
    exit 0
  fi

  # If VERSION is the same as base branch, user didn't bump it, so we should update
  if git diff --quiet "$BASE_RESOLVED" -- VERSION 2>/dev/null; then
    echo "VERSION file is the same as in base branch ($BASE_RESOLVED). User didn't bump version, so updating develop version."
    source "$(dirname "$0")/update_develop_version.sh"
  else
    echo "VERSION file differs from base branch. User already bumped version. Skipping update."
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
