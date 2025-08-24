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

  # If BASE_REF not provided (e.g., pre-commit.ci), infer remote default branch
  if [[ -z "$BASE_REF" ]]; then
    DEFAULT_BASE="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
    if [[ -z "$DEFAULT_BASE" ]]; then
      DEFAULT_BASE="$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' | head -n1)"
    fi
    BASE_REF="$DEFAULT_BASE"
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

  # If diff is quiet, there were no changes to VERSION between base and head.
  if git diff --quiet "$BASE_RESOLVED...HEAD" -- VERSION; then
    echo "No VERSION bump detected in PR range ($BASE_RESOLVED...HEAD). Updating develop version."
    source "$(dirname "$0")/update_develop_version.sh"
  else
    echo "PR includes a VERSION change. Skipping version update."
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

# Check if the VERSION file is staged for modification
if git diff --cached --name-only | grep -q "VERSION"; then
  echo "The VERSION file is already modified. Skipping version update."
  exit 0
elif git diff --name-only | grep -q "VERSION"; then
  echo "The VERSION file has unstaged changes. Please stage them before committing."
  exit 0
elif ! git show --name-only HEAD | grep -q "VERSION"; then
  source "$(dirname "$0")/update_develop_version.sh"
elif [[ -n "$(git diff --cached --name-only)" ]] && ! git diff --cached --name-only | grep -q "VERSION"; then
  source "$(dirname "$0")/update_develop_version.sh"
fi
