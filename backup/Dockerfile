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