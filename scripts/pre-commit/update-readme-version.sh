#!/usr/bin/env bash

# Get the name of the current branch
branch_name=$(git symbolic-ref --short HEAD)

# Run the python script with the branch name as an argument
python3 scripts/update-readme-version.py $branch_name
