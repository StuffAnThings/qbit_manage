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
fi

# Read the current version from the VERSION file
current_version=$(<VERSION)
echo "Current version: $current_version"

# Check if "develop" is not present in the version string
if [[ $current_version != *"develop"* ]]; then
  echo "The word 'develop' is not present in the version string."
  exit 0
fi

# Extract the version number after "develop"
version_number=$(echo "$current_version" | sed -n 's/.*develop\([0-9]*\).*/\1/p')

# Increment the version number
new_version_number=$((version_number + 1))

# Replace the old version number with the new one
new_version=$(echo "$current_version" | sed "s/develop$version_number/develop$new_version_number/")

# Update the VERSION file
sed -i "s/$current_version/$new_version/" VERSION

echo "Version updated to: $new_version"
