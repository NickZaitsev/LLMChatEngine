# PostgreSQL Backup Solution for AI Girlfriend Bot

This guide explains how to set up automated daily backups for your PostgreSQL database with automatic cleanup of backups older than 14 days.

## Overview

The backup solution uses:
- `pg_dump` to create database dumps
- A separate backup service in Docker Compose
- A cron job for daily scheduling
- Automatic cleanup of old backups (14-day retention)

## Implementation Plan

### 1. Create Backup Script

Create a shell script `backup_db.sh` with the following content:

```bash
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

# Check if backup was successful
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "Backup successful: $BACKUP_FILE"
    
    # Set permissions
    chmod 600 "$BACKUP_FILE"
    
    # Cleanup backups older than 14 days
    echo "Cleaning up old backups (older than 14 days)"
    find "$BACKUP_DIR" -name "ai_bot_backup_*.sql.gz" -mtime +14 -delete
    
    echo "Backup process completed successfully"
else
    echo "Backup failed"
    exit 1
fi
```

### 2. Create Dockerfile for Backup Service

Create a file `backup/Dockerfile` with the following content:

```dockerfile
FROM postgres:15

# Install cron
RUN apt-get update && apt-get install -y \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Copy backup script
COPY backup_db.sh /usr/local/bin/backup_db.sh
RUN chmod +x /usr/local/bin/backup_db.sh

# Setup cron job for daily backups at 2 AM
RUN echo "0 2 * * * /usr/local/bin/backup_db.sh >> /var/log/backup.log 2>&1" | crontab -

# Create log file
RUN touch /var/log/backup.log

# Health check
HEALTHCHECK CMD crontab -l || exit 1

# Start cron
CMD ["cron", "-f"]
```

### 3. Update docker-compose.yml

Modify your `docker-compose.yml` to add the backup service:

```yaml
services:
  ai-girlfriend-bot:
    build: .
    container_name: ai-girlfriend-bot
    restart: unless-stopped
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - AZURE_API_KEY=${AZURE_API_KEY}
      - AZURE_MODEL=${AZURE_MODEL:-deepseek/DeepSeek-V3-0324}
      - BOT_NAME=${BOT_NAME:-Luna}
      - DATABASE_URL=postgresql+asyncpg://ai_bot:${DB_PASSWORD:-ai_bot_pass}@postgres:5432/ai_bot
      - PROVIDER=${PROVIDER:-lmstudio}
      - LMSTUDIO_MODEL=${LMSTUDIO_MODEL:-openai/gpt-oss-20b}
      - LMSTUDIO_BASE_URL=http://host-machine:1234/v1
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - bot-network
    extra_hosts:
      - "host-machine:host-gateway"

  postgres:
    image: pgvector/pgvector:pg15
    container_name: ai-girlfriend-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=ai_bot
      - POSTGRES_USER=ai_bot
      - POSTGRES_PASSWORD=${DB_PASSWORD:-ai_bot_pass}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-pgvector.sql:/docker-entrypoint-initdb.d/init-pgvector.sql
      - backups:/backups
    ports:
      - "5432:5432"
    networks:
      - bot-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ai_bot -d ai_bot"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres-backup:
    build: ./backup
    container_name: ai-girlfriend-postgres-backup
    restart: unless-stopped
    environment:
      - DB_PASSWORD=${DB_PASSWORD:-ai_bot_pass}
    volumes:
      - backups:/backups
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - bot-network

volumes:
  postgres_data:
  backups:

networks:
  bot-network:
    driver: bridge
```

### 4. Manual Backup Execution

To manually trigger a backup, run:

```bash
docker-compose exec postgres-backup /usr/local/bin/backup_db.sh
```

### 5. Restore from Backup

To restore from a backup:

```bash
# List available backups
docker-compose exec postgres-backup ls -la /backups

# Copy backup to postgres container
docker-compose cp postgres-backup:/backups/backup_file.sql.gz ./backup_file.sql.gz

# Restore (from host machine)
gunzip < backup_file.sql.gz | psql -h localhost -U ai_bot -d ai_bot
```

Or restore directly within the containers:

```bash
# Enter postgres container
docker-compose exec postgres bash

# Restore from backup (within postgres container)
gunzip -c /backups/backup_file.sql.gz | psql -U ai_bot -d ai_bot
```

## Configuration Details

### Backup Schedule

The backup runs daily at 2:00 AM server time. To modify the schedule:

1. Edit the cron expression in `backup/Dockerfile`
2. Rebuild the backup container: `docker-compose build postgres-backup`
3. Restart the service: `docker-compose up -d postgres-backup`

### Backup Retention

Backups are automatically deleted after 14 days. To change the retention period:

1. Modify the `-mtime +14` value in the `backup_db.sh` script
2. Rebuild the backup container: `docker-compose build postgres-backup`
3. Restart the service: `docker-compose up -d postgres-backup`

## Monitoring and Troubleshooting

### Check Backup Status

```bash
# View backup logs
docker-compose logs postgres-backup

# List backups
docker-compose exec postgres-backup ls -la /backups
```

### Manual Backup Test

```bash
# Run a manual backup to test
docker-compose exec postgres-backup /usr/local/bin/backup_db.sh
```

### Common Issues

1. **Backup fails with permission errors**
   - Check that the backup script has execute permissions
   - Verify database credentials in environment variables

2. **Cron job not running**
   - Check that the cron service is running: `docker-compose exec postgres-backup ps aux | grep cron`
   - Verify cron entry: `docker-compose exec postgres-backup crontab -l`

3. **Disk space issues**
   - Monitor backup volume usage: `docker system df -v`
   - Check backup directory size: `docker-compose exec postgres-backup du -sh /backups`

## Security Considerations

1. Backup files contain sensitive data and are stored with restricted permissions (600)
2. Database credentials are passed through Docker environment variables
3. The backup volume should be secured and regularly monitored

## Performance Impact

The backup process has minimal impact on database performance:
- Backups run during low-usage hours (2 AM by default)
- `pg_dump` creates consistent snapshots without locking tables
- Compressed backups reduce storage requirements

This backup solution provides a reliable, automated approach to protecting your AI Girlfriend Bot's conversation data with a 14-day retention policy.