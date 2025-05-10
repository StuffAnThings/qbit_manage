#!/usr/bin/env bash

# Check if there are any changes staged for commit
if [[ -z $(git diff --cached --name-only) ]]; then
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
fi

source "$(dirname "$0")/update_develop_version.sh"
