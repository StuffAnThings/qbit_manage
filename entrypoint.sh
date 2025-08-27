#!/bin/bash

# Exit on any error
set -e

# Runtime identity and permissions
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
UMASK="${UMASK:-022}"

# Validate inputs (numeric PUID/PGID)
if ! [[ "$PUID" =~ ^[0-9]+$ ]] || ! [[ "$PGID" =~ ^[0-9]+$ ]]; then
    echo "ERROR: PUID and PGID must be numeric. Got PUID='$PUID' PGID='$PGID'"
    exit 1
fi

umask "$UMASK"

# Configuration
SOURCE_FILE="/app/config/config.yml.sample"
DEST_FILE="/config/config.yml.sample"

# Function to safely copy with atomic operation
safe_copy() {
    local src="$1"
    local dest="$2"
    local temp_file="${dest}.tmp"

    # Create a temporary file first
    cp "$src" "$temp_file"

    # Atomic move to final destination
    mv "$temp_file" "$dest"

    echo "Successfully copied $src to $dest"
}

# Function to fix permissions (only when needed; quiet if no changes)
fix_permissions() {
    local path="$1"
    local uid="${PUID:-1000}"
    local gid="${PGID:-1000}"

    if [ -d "$path" ]; then
        if find "$path" -xdev \( -not -user "$uid" -o -not -group "$gid" \) -print -quit | grep -q .; then
            if chown -R "$uid:$gid" "$path" 2>/dev/null; then
                echo "Corrected ownership of directory $path to $uid:$gid"
            else
                echo "Warning: Could not change ownership of directory $path"
            fi
        fi
    else
        if ! find "$path" -maxdepth 0 -user "$uid" -a -group "$gid" -print -quit | grep -q .; then
            if chown "$uid:$gid" "$path" 2>/dev/null; then
                echo "Corrected ownership of $path to $uid:$gid"
            else
                echo "Warning: Could not change ownership of $path"
            fi
        fi
    fi
}

# Main logic
if [ -d "/config" ]; then
    if [ -f "$SOURCE_FILE" ] && [ -s "$SOURCE_FILE" ]; then
        if [ ! -f "$DEST_FILE" ] || ! cmp -s "$SOURCE_FILE" "$DEST_FILE"; then
            # Safely copy the file (logs only when copy occurs)
            safe_copy "$SOURCE_FILE" "$DEST_FILE"
            # Fix permissions (logs only if changes made)
            fix_permissions "$DEST_FILE"
        fi
    elif [ ! -f "$SOURCE_FILE" ]; then
        echo "ERROR: Source file $SOURCE_FILE does not exist"
        exit 1
    fi
fi

# Fix /config ownership if present
if [ -d "/config" ]; then
    fix_permissions "/config"
    # Provide a reasonable HOME for non-root runs (only if /config exists)
    export HOME=/config
fi

# Execute the main command as requested UID:GID
exec /sbin/su-exec "${PUID}:${PGID}" "$@"
