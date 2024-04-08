#!/usr/bin/env bash

# Try to get the name of the current branch
branch_name=$(git symbolic-ref --short HEAD 2> /dev/null)

# If the command failed, exit with code 0
if [ $? -ne 0 ]; then
    echo "Error: ref HEAD is not a symbolic ref"
    exit 0
fi

# Run the python script with the branch name as an argument
python3 scripts/update-readme-version.py $branch_name
