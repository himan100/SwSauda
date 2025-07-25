from datetime import datetime
from typing import List, Optional
from database import get_database
from models import UserCreate, UserUpdate, UserInDB, UserRole, OrderCreate, OrderUpdate, Order, OrderStatus
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
    if user_update.hashed_password is not None:
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

# Order CRUD operations
async def create_order(order: OrderCreate) -> Order:
    db = await get_database()
    
    now = datetime.utcnow()
    order_data = {
        "symbol": order.symbol,
        "quantity": order.quantity,
        "side": order.side,
        "order_type": order.order_type,
        "price": order.price,
        "trigger_price": order.trigger_price,
        "user_id": order.user_id,
        "status": OrderStatus.PENDING,
        "filled_quantity": 0,
        "average_price": None,
        "created_at": now,
        "updated_at": now,
        "filled_at": None
    }
    
    result = await db.orders.insert_one(order_data)
    order_data["id"] = str(result.inserted_id)
    
    return Order(**order_data)

async def get_order_by_id(order_id: str) -> Optional[Order]:
    db = await get_database()
    try:
        order = await db.orders.find_one({"_id": bson.ObjectId(order_id)})
        if order:
            order["id"] = str(order["_id"])
            return Order(**order)
    except bson.errors.InvalidId:
        pass
    return None

async def get_orders(user_id: Optional[str] = None, symbol: Optional[str] = None, 
                    status: Optional[OrderStatus] = None, limit: int = 100, skip: int = 0) -> List[Order]:
    db = await get_database()
    
    filter_query = {}
    if user_id:
        filter_query["user_id"] = user_id
    if symbol:
        filter_query["symbol"] = symbol
    if status:
        filter_query["status"] = status
    
    cursor = db.orders.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
    orders = []
    
    async for order in cursor:
        order["id"] = str(order["_id"])
        orders.append(Order(**order))
    
    return orders

async def update_order(order_id: str, order_update: OrderUpdate) -> Optional[Order]:
    db = await get_database()
    
    try:
        update_data = {k: v for k, v in order_update.dict().items() if v is not None}
        update_data["updated_at"] = datetime.utcnow()
        
        if order_update.status == OrderStatus.FILLED:
            update_data["filled_at"] = datetime.utcnow()
        
        result = await db.orders.update_one(
            {"_id": bson.ObjectId(order_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            return await get_order_by_id(order_id)
    except bson.errors.InvalidId:
        pass
    
    return None

async def delete_order(order_id: str) -> bool:
    db = await get_database()
    try:
        result = await db.orders.delete_one({"_id": bson.ObjectId(order_id)})
        return result.deleted_count > 0
    except bson.errors.InvalidId:
        return False