import motor.motor_asyncio
import redis.asyncio as redis
from config import settings

# MongoDB connection
client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_url)
db = client[settings.database_name]

# Redis connection
redis_client = redis.from_url(settings.redis_url, db=settings.redis_db, decode_responses=True)

async def connect_to_mongo():
    """Connect to MongoDB"""
    try:
        await client.admin.command('ping')
        print("Connected to MongoDB")
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")

async def connect_to_redis():
    """Connect to Redis"""
    try:
        await redis_client.ping()
        print("Connected to Redis")
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")

async def close_mongo_connection():
    """Close MongoDB connection"""
    client.close()
    print("MongoDB connection closed")

async def close_redis_connection():
    """Close Redis connection"""
    await redis_client.close()
    print("Redis connection closed")

async def get_database():
    return db 