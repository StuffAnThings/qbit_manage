#!/usr/bin/env bash

# This script must be sourced so the virtualenv remains active in the current shell.
is_sourced=0
if [ -n "${ZSH_VERSION:-}" ]; then
	case ${ZSH_EVAL_CONTEXT:-} in
		*:file) is_sourced=1 ;;
	esac
else
	(return 0 2>/dev/null) && is_sourced=1
fi

if [ "$is_sourced" -ne 1 ]; then
	echo "Please source this script instead:"
	echo "  source activate.sh"
	exit 1
fi

if [ -n "${ZSH_VERSION:-}" ]; then
	SCRIPT_PATH="${(%):-%x}"
else
	SCRIPT_PATH="${BASH_SOURCE[0]}"
fi

SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
VENV_ACTIVATE="$SCRIPT_DIR/.venv/bin/activate"

if [ ! -f "$VENV_ACTIVATE" ]; then
	echo "Virtual environment not found at $VENV_ACTIVATE"
	echo "Run: make venv"
	return 1
fi

# shellcheck disable=SC1090
. "$VENV_ACTIVATE"
