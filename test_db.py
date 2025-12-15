import asyncio
from database.client import DatabaseClient
from config import config

async def test_db():
    """Test database operations"""
    print("Testing database user save...")
    
    db = DatabaseClient()
    await db.connect()
    
    # Test save
    print("Saving user 999...")
    await db.create_or_update_user(
        user_id=999,
        username="testuser",
        first_name="Test"
    )
    
    # Test retrieve
    print("Retrieving user 999...")
    user = await db.get_user(999)
    print(f"Retrieved user: {user}")
    
    # Test preferences
    print("Creating default preferences...")
    await db.create_default_preferences(999)
    
    prefs = await db.get_user_preferences(999)
    print(f"Preferences: {prefs}")
    
    await db.disconnect()
    print("✓ Database test complete")

asyncio.run(test_db())
