from datetime import datetime
from typing import List, Optional
from database import get_database
from models import UserCreate, UserUpdate, UserInDB, UserRole
from auth import get_password_hash, verify_password
import bson

async def create_user(user: UserCreate) -> UserInDB:
    db = await get_database()
    
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise ValueError("User with this email already exists")
    
    hashed_password = get_password_hash(user.password)
    now = datetime.utcnow()
    
    user_data = {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "hashed_password": hashed_password,
        "created_at": now,
        "updated_at": now
    }
    
    result = await db.users.insert_one(user_data)
    user_data["id"] = str(result.inserted_id)
    
    return UserInDB(**user_data)

async def get_user_by_email(email: str) -> Optional[UserInDB]:
    db = await get_database()
    user = await db.users.find_one({"email": email})
    if user:
        user["id"] = str(user["_id"])
        return UserInDB(**user)
    return None

async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
    db = await get_database()
    try:
        user = await db.users.find_one({"_id": bson.ObjectId(user_id)})
        if user:
            user["id"] = str(user["_id"])
            return UserInDB(**user)
    except bson.errors.InvalidId:
        pass
    return None

async def get_users(skip: int = 0, limit: int = 100) -> List[UserInDB]:
    db = await get_database()
    users = []
    cursor = db.users.find().skip(skip).limit(limit)
    async for user in cursor:
        user["id"] = str(user["_id"])
        users.append(UserInDB(**user))
    return users

async def update_user(user_id: str, user_update: UserUpdate) -> Optional[UserInDB]:
    db = await get_database()
    
    update_data = {}
    if user_update.email is not None:
        update_data["email"] = user_update.email
    if user_update.full_name is not None:
        update_data["full_name"] = user_update.full_name
    if user_update.role is not None:
        update_data["role"] = user_update.role
    if user_update.is_active is not None:
        update_data["is_active"] = user_update.is_active
    if hasattr(user_update, 'hashed_password') and user_update.hashed_password is not None:
        update_data["hashed_password"] = user_update.hashed_password
    
    if update_data:
        update_data["updated_at"] = datetime.utcnow()
        try:
            result = await db.users.update_one(
                {"_id": bson.ObjectId(user_id)},
                {"$set": update_data}
            )
            if result.modified_count:
                return await get_user_by_id(user_id)
        except bson.errors.InvalidId:
            pass
    return None

async def delete_user(user_id: str) -> bool:
    db = await get_database()
    try:
        result = await db.users.delete_one({"_id": bson.ObjectId(user_id)})
        return result.deleted_count > 0
    except bson.errors.InvalidId:
        return False

async def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
    user = await get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

async def create_super_admin():
    db = await get_database()
    from config import settings
    
    # Check if super admin already exists
    existing_admin = await db.users.find_one({"role": UserRole.SUPER_ADMIN})
    if existing_admin:
        return
    
    hashed_password = get_password_hash(settings.super_admin_password)
    now = datetime.utcnow()
    
    super_admin_data = {
        "email": settings.super_admin_email,
        "full_name": "Super Admin",
        "role": UserRole.SUPER_ADMIN,
        "is_active": True,
        "hashed_password": hashed_password,
        "created_at": now,
        "updated_at": now
    }
    
    await db.users.insert_one(super_admin_data)
    print("Super admin created successfully") 