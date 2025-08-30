#!/bin/bash
set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Configuration
readonly SOURCE_FILE="/app/config/config.yml.sample"
readonly DEST_DIR="${QBT_CONFIG_DIR:-/config}"
readonly DEST_FILE="${DEST_DIR}/config.yml.sample"

# Logging function for consistent output
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

# Validate numeric environment variables
validate_numeric_env() {
    local var_name="$1"
    local var_value="$2"

    if [[ -n "$var_value" ]] && ! [[ "$var_value" =~ ^[0-9]+$ ]]; then
        log "Warning: $var_name must be numeric. Got $var_name='$var_value' - ignoring PUID/PGID and running as root"
        return 1
    fi
    return 0
}

# Validate and set PUID/PGID
validate_user_group_ids() {
    local puid_valid=0
    local pgid_valid=0

    if ! validate_numeric_env "PUID" "${PUID:-}"; then
        puid_valid=1
    fi

    if ! validate_numeric_env "PGID" "${PGID:-}"; then
        pgid_valid=1
    fi

    # If either is invalid, clear both
    if [[ $puid_valid -eq 1 ]] || [[ $pgid_valid -eq 1 ]]; then
        PUID=""
        PGID=""
        return 1
    fi

    return 0
}

# Safely copy file with atomic operation and error handling
safe_copy() {
    local src="$1"
    local dest="$2"
    local temp_file="${dest}.tmp"

    # Validate source file exists and is readable
    if [[ ! -f "$src" ]] || [[ ! -r "$src" ]]; then
        log "Error: Source file '$src' does not exist or is not readable"
        return 1
    fi

    # Create parent directory if it doesn't exist
    local dest_dir
    dest_dir="$(dirname "$dest")"
    if [[ ! -d "$dest_dir" ]]; then
        mkdir -p "$dest_dir" || {
            log "Error: Could not create destination directory '$dest_dir'"
            return 1
        }
    fi

    # Atomic copy operation
    if cp "$src" "$temp_file" && mv "$temp_file" "$dest"; then
        log "Successfully copied $src to $dest"
        return 0
    else
        # Clean up temp file on failure
        [[ -f "$temp_file" ]] && rm -f "$temp_file"
        log "Error: Failed to copy $src to $dest"
        return 1
    fi
}

# Optimized permission fixing with better performance
fix_permissions() {
    local path="$1"

    # Skip if PUID or PGID are not set
    if [[ -z "${PUID:-}" ]] || [[ -z "${PGID:-}" ]]; then
        log "Skipping permission fix for $path - PUID or PGID not set"
        return 0
    fi

    # Check if we're running as root
    if [[ "$(id -u)" != "0" ]]; then
        log "Skipping permission fix for $path - not running as root"
        return 0
    fi

    local needs_fix=0

    if [[ -d "$path" ]]; then
        # Check if any files in directory need ownership change
        if find "$path" -xdev \( -not -user "$PUID" -o -not -group "$PGID" \) -print -quit 2>/dev/null | grep -q .; then
            needs_fix=1
        fi
    elif [[ -e "$path" ]]; then
        # Check if file needs ownership change
        if [[ "$(stat -c '%u:%g' "$path" 2>/dev/null || echo "0:0")" != "$PUID:$PGID" ]]; then
            needs_fix=1
        fi
    else
        log "Warning: Path '$path' does not exist, skipping permission fix"
        return 0
    fi

    if [[ $needs_fix -eq 1 ]]; then
        if chown -R "$PUID:$PGID" "$path" 2>/dev/null; then
            local type_msg="file"
            [[ -d "$path" ]] && type_msg="directory"
            log "Corrected ownership of $type_msg $path to $PUID:$PGID"
            return 0
        else
            log "Warning: Could not change ownership of $path"
            return 1
        fi
    fi

    return 0
}

# Execute command with appropriate privilege level
execute_command() {
    local current_uid
    current_uid="$(id -u)"

    if [[ "$current_uid" = "0" ]]; then
        if [[ -n "${PUID:-}" ]] && [[ -n "${PGID:-}" ]]; then
            log "Changing privileges to PUID:PGID = $PUID:$PGID"
            exec /sbin/su-exec "${PUID}:${PGID}" "$@" || {
                log "Warning: Could not drop privileges to ${PUID}:${PGID}, continuing as root"
                exec "$@"
            }
        else
            log "PUID/PGID not set, running as root"
            exec "$@"
        fi
    else
        log "Already running as non-root user (UID: $current_uid), executing command"
        exec "$@"
    fi
}

# Main execution
main() {
    # Validate user/group IDs
    validate_user_group_ids

    # Handle config file setup
    if [[ -d "$DEST_DIR" ]]; then
        if [[ -f "$SOURCE_FILE" ]] && [[ -s "$SOURCE_FILE" ]]; then
            # Check if destination needs updating
            if [[ ! -f "$DEST_FILE" ]] || ! cmp -s "$SOURCE_FILE" "$DEST_FILE" 2>/dev/null; then
                if safe_copy "$SOURCE_FILE" "$DEST_FILE"; then
                    # Fix permissions if running as root and IDs are set
                    if [[ "$(id -u)" = "0" ]] && [[ -n "${PUID:-}" ]] && [[ -n "${PGID:-}" ]]; then
                        fix_permissions "$DEST_FILE"
                    fi
                fi
            fi
        elif [[ ! -f "$SOURCE_FILE" ]]; then
            log "Warning: Source file $SOURCE_FILE does not exist, skipping config setup"
        fi
    fi

    # Execute the main command
    execute_command "$@"
}

# Run main function with all arguments
main "$@"
