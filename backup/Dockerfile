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

# Health check: cron must be scheduled AND a verified backup must exist that is
# newer than 26 hours (daily backups run at 02:00; 26h tolerates schedule drift).
HEALTHCHECK --interval=5m --timeout=10s --start-period=2m \
    CMD crontab -l >/dev/null 2>&1 && find /backups/last_success -mmin -1560 2>/dev/null | grep -q . || exit 1

# Run one backup immediately so the container becomes healthy on a fresh deploy
# instead of waiting for the first scheduled run, then keep cron in the foreground.
CMD ["bash", "-c", "/usr/local/bin/backup_db.sh || true; cron -f"]