#!/bin/bash

# PostgreSQL Backup Script
set -e

# Configuration
BACKUP_DIR="/backups"
DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/ai_bot_backup_$DATE.sql.gz"
DB_HOST="postgres"
DB_NAME="ai_bot"
DB_USER="ai_bot"
DB_PASSWORD="$DB_PASSWORD"  # Passed from environment

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Create database backup
echo "Creating backup: $BACKUP_FILE"
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"

# Check if backup was successful (pg_dump is the first stage of the pipe)
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "Backup failed: pg_dump returned a non-zero status"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Verify the gzip archive is intact before trusting it
if ! gzip -t "$BACKUP_FILE"; then
    echo "Backup failed: gzip integrity check did not pass for $BACKUP_FILE"
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "Backup successful: $BACKUP_FILE"

# Set permissions
chmod 600 "$BACKUP_FILE"

# Record a marker for the healthcheck: a verified backup just completed
date +"%Y-%m-%dT%H:%M:%S%z" > "$BACKUP_DIR/last_success"
chmod 600 "$BACKUP_DIR/last_success"

# Cleanup backups older than 14 days
echo "Cleaning up old backups (older than 14 days)"
find "$BACKUP_DIR" -name "ai_bot_backup_*.sql.gz" -mtime +14 -delete

echo "Backup process completed successfully"