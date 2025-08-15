# PostgreSQL Storage Setup Guide

This guide explains how to set up and use the PostgreSQL storage system for the AI Girlfriend Bot, which provides persistent data storage across bot restarts.

## Overview

The bot now supports two storage modes:
- **In-Memory Storage** (default): Fast but data is lost on restart
- **PostgreSQL Storage** (new): Persistent, scalable, with optional semantic search

## Features of PostgreSQL Storage

✅ **Persistent Storage**: All conversations, messages, and memories are saved to database  
✅ **Scalable**: Can handle thousands of users and millions of messages  
✅ **Semantic Search**: Optional pgvector support for intelligent memory search  
✅ **Multi-User Support**: Proper user and persona management  
✅ **Token Management**: Efficient conversation history management  
✅ **Backward Compatible**: Drop-in replacement for the in-memory system  

## Quick Setup (Docker)

1. **Update your `.env` file:**
```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://ai_bot:your_secure_password@postgres:5432/ai_bot
DB_PASSWORD=your_secure_password
USE_POSTGRES=true
USE_PGVECTOR=true
```

2. **Start the services:**
```bash
docker-compose up -d
```

That's it! The bot will automatically:
- Start PostgreSQL with the correct configuration
- Create all necessary database tables
- Initialize pgvector extension (if available)
- Begin using persistent storage
- **Fail to start if PostgreSQL is unavailable** (prevents accidental data loss)

## Manual Setup (Local Development)

### 1. Install PostgreSQL

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
```

**macOS:**
```bash
brew install postgresql
brew services start postgresql
```

**Windows:**
Download and install from [postgresql.org](https://www.postgresql.org/download/windows/)

### 2. Create Database and User

```sql
-- Connect to PostgreSQL as superuser
sudo -u postgres psql

-- Create database and user
CREATE DATABASE ai_bot;
CREATE USER ai_bot WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE ai_bot TO ai_bot;

-- Connect to the new database
\c ai_bot

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO ai_bot;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ai_bot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ai_bot;

-- Exit
\q
```

### 3. Install pgvector (Optional but Recommended)

pgvector enables semantic search for memories:

**Ubuntu/Debian:**
```bash
sudo apt-get install postgresql-15-pgvector
```

**macOS:**
```bash
brew install pgvector
```

**From Source:**
```bash
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

**Enable in database:**
```sql
-- Connect to your database
psql -U ai_bot -d ai_bot

-- Create extension
CREATE EXTENSION IF NOT EXISTS vector;
```

### 4. Configure Environment

Update your `.env` file:
```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://ai_bot:your_secure_password@localhost:5432/ai_bot
DB_PASSWORD=your_secure_password
USE_POSTGRES=true
USE_PGVECTOR=true  # Set to false if pgvector is not available
```

### 5. Install Python Dependencies

```bash
pip install -r requirements.txt
```

The requirements already include:
- `asyncpg>=0.29.0` - PostgreSQL async driver
- `pgvector>=0.2.4` - Vector similarity search
- `sqlalchemy>=2.0.0` - Database ORM

## Testing the Setup

Run the test script to verify everything works:

```bash
python tests/test_postgres_storage.py
```

Expected output:
```
✅ ALL TESTS PASSED! PostgreSQL storage is working correctly.
```

If you see errors, check:
1. PostgreSQL is running
2. Database credentials are correct
3. Database and user exist
4. All dependencies are installed

## Migration from In-Memory Storage

The PostgreSQL system is a **drop-in replacement** for the in-memory system. Simply:

1. Set `USE_POSTGRES=true` in your `.env` file
2. Configure `DATABASE_URL`
3. Restart the bot

**Important Notes:**
- Existing conversation history from the in-memory system will not be migrated. Users will start with fresh conversations.
- **The bot will fail to start** if `USE_POSTGRES=true` but PostgreSQL is unavailable. This prevents accidental data loss.
- To disable PostgreSQL, set `USE_POSTGRES=false` in your `.env` file.

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_POSTGRES` | `false` | Enable PostgreSQL storage |
| `DATABASE_URL` | - | PostgreSQL connection URL |
| `DB_PASSWORD` | `ai_bot_pass` | Database password |
| `USE_PGVECTOR` | `true` | Enable semantic search |

### Database URL Format

```
postgresql+asyncpg://username:password@host:port/database
```

Examples:
- Local: `postgresql+asyncpg://ai_bot:password@localhost:5432/ai_bot`
- Docker: `postgresql+asyncpg://ai_bot:password@postgres:5432/ai_bot`
- Remote: `postgresql+asyncpg://user:pass@db.example.com:5432/ai_bot`

## Database Schema

The system automatically creates these tables:

- **users** - User accounts
- **personas** - AI personalities
- **conversations** - Chat sessions
- **messages** - Individual messages
- **memories** - Long-term memory entries

## Performance Considerations

### Connection Pooling
The system uses SQLAlchemy's connection pooling:
- Pool size: 10 connections
- Max overflow: 20 connections
- Connection recycling: 1 hour

### Token Management
Efficient conversation history management:
- Automatic token counting
- Smart conversation trimming
- Budget-based message retrieval

### Indexing
Optimized database indexes for:
- Message retrieval by conversation
- Memory similarity search (with pgvector)
- User and conversation lookups

## Troubleshooting

### Common Issues

**1. Bot fails to start with PostgreSQL errors**
```
CRITICAL: Failed to initialize PostgreSQL storage
Bot cannot start with PostgreSQL enabled but database unavailable
```
**This is expected behavior** - the bot won't start to prevent data loss. Solutions:
- Check PostgreSQL is running: `sudo systemctl status postgresql`
- Verify connection details in `.env`
- Or disable PostgreSQL: set `USE_POSTGRES=false`

**2. Connection refused**
```
psycopg2.OperationalError: connection to server failed
```
- Check PostgreSQL is running: `sudo systemctl status postgresql`
- Verify connection details in `.env`

**2. Authentication failed**
```
psycopg2.OperationalError: FATAL: authentication failed
```
- Check username/password in `.env`
- Verify user exists: `sudo -u postgres psql -c "\du"`

**3. Database does not exist**
```
psycopg2.OperationalError: database "ai_bot" does not exist
```
- Create database: `sudo -u postgres createdb ai_bot`

**4. pgvector not available**
```
ImportError: No module named 'pgvector'
```
- Install pgvector or set `USE_PGVECTOR=false`

**5. Permission denied**
```
psycopg2.ProgrammingError: permission denied for table
```
- Grant permissions: `GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ai_bot;`

### Debug Mode

Enable detailed SQL logging in `storage/__init__.py`:
```python
engine_kwargs = {
    "echo": True,  # Set to True for SQL debugging
    "future": True,
}
```

### Health Checks

The system includes health check endpoints:
```python
# Check database connectivity
health = await storage.health_check()
```

## Advanced Configuration

### Custom Connection Parameters

```python
# Custom engine configuration
DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db?sslmode=require&pool_size=20"
```

### Multiple Databases

For advanced setups, you can configure separate read/write databases by modifying the connection logic in `storage/__init__.py`.

### Backup and Maintenance

**Regular Backups:**
```bash
# Create backup
pg_dump -U ai_bot -h localhost ai_bot > backup.sql

# Restore backup
psql -U ai_bot -h localhost ai_bot < backup.sql
```

**Vacuum and Analyze:**
```sql
-- Optimize database performance
VACUUM ANALYZE;
```

## Security Considerations

1. **Strong Passwords**: Use secure passwords for database users
2. **Network Security**: Restrict PostgreSQL network access
3. **SSL Connections**: Use SSL in production (`sslmode=require`)
4. **Regular Updates**: Keep PostgreSQL and pgvector updated

## Production Deployment

For production use:

1. Use a dedicated PostgreSQL server
2. Configure SSL connections
3. Set up regular backups
4. Monitor database performance
5. Use connection pooling
6. Consider read replicas for scaling

## Support

If you encounter issues:

1. Check the logs: `docker-compose logs ai-girlfriend-bot`
2. Run the test script: `python tests/test_postgres_storage.py`
3. Verify PostgreSQL status: `docker-compose ps postgres`
4. Check database connectivity: `psql -U ai_bot -h localhost ai_bot`

The PostgreSQL storage system provides a robust, scalable foundation for the AI Girlfriend Bot with persistent memory and advanced features.