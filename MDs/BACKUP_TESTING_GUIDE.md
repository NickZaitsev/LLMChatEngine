# PostgreSQL Backup Testing Guide

This guide explains how to test the backup and restore functionality for your AI Girlfriend Bot.

## Prerequisites

1. Ensure all services are built and running:
   ```bash
   docker-compose up -d
   ```

2. Wait for all services to be healthy:
   ```bash
   docker-compose ps
   ```

## Testing Backup Functionality

### 1. Manual Backup Test

Run a manual backup to verify the process works:

```bash
docker-compose exec postgres-backup /usr/local/bin/backup_db.sh
```

Expected output:
```
Creating backup: /backups/ai_bot_backup_20250821_143022.sql.gz
Backup successful: /backups/ai_bot_backup_20250821_143022.sql.gz
Cleaning up old backups (older than 14 days)
Backup process completed successfully
```

### 2. Verify Backup Created

List the backups:
```bash
docker-compose exec postgres-backup ls -la /backups
```

You should see a .sql.gz file with today's date.

### 3. Check Backup Service Logs

View the backup service logs:
```bash
docker-compose logs postgres-backup
```

## Testing Restore Functionality

### 1. Identify Backup File

List available backups:
```bash
docker-compose exec postgres-backup ls -la /backups
```

### 2. Copy Backup to Postgres Container (Optional)

If you need to access the backup file from your host:
```bash
docker-compose cp postgres-backup:/backups/backup_file.sql.gz ./backup_file.sql.gz
```

### 3. Restore Backup

Restore directly within the containers:
```bash
# Enter postgres container
docker-compose exec postgres bash

# Restore from backup (within postgres container)
gunzip -c /backups/backup_file.sql.gz | psql -U ai_bot -d ai_bot
```

Or restore from the host machine:
```bash
# From host machine
gunzip < backup_file.sql.gz | psql -h localhost -U ai_bot -d ai_bot
```

## Automated Backup Verification

### 1. Check Cron Job

Verify the cron job is scheduled:
```bash
docker-compose exec postgres-backup crontab -l
```

Expected output:
```
0 2 * * * /usr/local/bin/backup_db.sh >> /var/log/backup.log 2>&1
```

### 2. Check Backup Logs

View backup logs:
```bash
docker-compose exec postgres-backup cat /var/log/backup.log
```

## Troubleshooting

### Common Issues

1. **Permission denied errors**
   - Ensure the backup script has execute permissions
   - Check that the DB_PASSWORD environment variable is set correctly

2. **Connection failed errors**
   - Verify that the postgres service is running and healthy
   - Check database credentials in the environment variables

3. **Backup file not found**
   - Ensure the backups volume is properly mounted
   - Check that the backup script is writing to the correct directory

### Health Checks

Check service health:
```bash
docker-compose ps
```

All services should show "healthy" status.

## Verification Checklist

- [ ] Manual backup completes successfully
- [ ] Backup file is created with correct naming format
- [ ] Backup file has appropriate permissions (600)
- [ ] Cron job is properly scheduled
- [ ] Old backups are cleaned up (test by creating backups older than 14 days)
- [ ] Restore process works correctly
- [ ] Backup service logs show no errors

This testing guide ensures your backup solution is working correctly and can protect your AI Girlfriend Bot's data.