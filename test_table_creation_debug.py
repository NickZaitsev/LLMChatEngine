import asyncio
import logging
from storage import create_storage
from sqlalchemy import text

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test():
    print("Creating storage...")
    storage = await create_storage('sqlite+aiosqlite:///:memory:', use_pgvector=False)
    print('Storage created successfully')
    
    # Check if tables exist
    print("Checking tables...")
    async with storage.engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = result.fetchall()
        print("Tables in database:")
        for table in tables:
            print(f"  {table[0]}")
    
    # Try to access a table directly
    try:
        async with storage.engine.connect() as conn:
            result = await conn.execute(text("SELECT * FROM users"))
            print("Users table exists and is accessible")
    except Exception as e:
        print(f"Error accessing users table: {e}")
    
    await storage.close()

if __name__ == "__main__":
    asyncio.run(test())