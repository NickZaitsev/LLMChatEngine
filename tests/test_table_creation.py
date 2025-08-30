import asyncio
from storage import create_storage
from sqlalchemy import text

async def test():
    storage = await create_storage('sqlite+aiosqlite:///:memory:', use_pgvector=False)
    print('Storage created successfully')
    
    # Check if tables exist
    async with storage.engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = result.fetchall()
        print("Tables in database:")
        for table in tables:
            print(f"  {table[0]}")
    
    await storage.close()

if __name__ == "__main__":
    asyncio.run(test())