#!/usr/bin/env bash

# This script must be sourced so environment changes affect the current shell.
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
	echo "  source deactivate.sh"
	exit 1
fi

if ! command -v deactivate >/dev/null 2>&1; then
	echo "No active Python virtual environment found."
	return 0
fi

deactivate
