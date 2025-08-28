import asyncio
from storage import create_storage

async def test():
    storage = await create_storage('sqlite+aiosqlite:///:memory:', use_pgvector=False)
    print('Tables created successfully')
    await storage.close()

if __name__ == "__main__":
    asyncio.run(test())