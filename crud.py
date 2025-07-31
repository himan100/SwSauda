from datetime import datetime
from typing import List, Optional
from database import get_database
from models import UserCreate, UserUpdate, UserInDB, UserRole, OrderCreate, OrderUpdate, Order, OrderStatus, ParameterCreate, ParameterUpdate, Parameter, StrategyCreate, StrategyUpdate, Strategy, StrategyExecutionCreate, StrategyExecutionUpdate, StrategyExecution
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

# Parameter CRUD functions
async def create_parameter(parameter: ParameterCreate, user_id: str) -> Parameter:
    db = await get_database()
    
    # Check if parameter with same name already exists
    existing_parameter = await db.parameters.find_one({"name": parameter.name})
    if existing_parameter:
        raise ValueError("Parameter with this name already exists")
    
    now = datetime.utcnow()
    parameter_data = {
        "name": parameter.name,
        "value": parameter.value,
        "description": parameter.description,
        "category": parameter.category,
        "datatype": parameter.datatype,
        "is_active": parameter.is_active,
        "created_at": now,
        "updated_at": now,
        "created_by": user_id
    }
    
    result = await db.parameters.insert_one(parameter_data)
    parameter_data["id"] = str(result.inserted_id)
    
    return Parameter(**parameter_data)

async def get_parameters(skip: int = 0, limit: int = 100, category: Optional[str] = None) -> List[Parameter]:
    db = await get_database()
    parameters = []
    
    filter_query = {}
    if category:
        filter_query["category"] = category
    
    cursor = db.parameters.find(filter_query).skip(skip).limit(limit).sort("created_at", -1)
    async for parameter in cursor:
        parameter["id"] = str(parameter["_id"])
        parameters.append(Parameter(**parameter))
    return parameters

async def get_parameter_by_id(parameter_id: str) -> Optional[Parameter]:
    db = await get_database()
    try:
        parameter = await db.parameters.find_one({"_id": bson.ObjectId(parameter_id)})
        if parameter:
            parameter["id"] = str(parameter["_id"])
            return Parameter(**parameter)
    except bson.errors.InvalidId:
        pass
    return None

async def get_parameter_by_name(name: str) -> Optional[Parameter]:
    db = await get_database()
    parameter = await db.parameters.find_one({"name": name})
    if parameter:
        parameter["id"] = str(parameter["_id"])
        return Parameter(**parameter)
    return None

async def update_parameter(parameter_id: str, parameter_update: ParameterUpdate) -> Optional[Parameter]:
    db = await get_database()
    
    update_data = {}
    if parameter_update.name is not None:
        # Check if name already exists for another parameter
        existing_parameter = await db.parameters.find_one({
            "name": parameter_update.name,
            "_id": {"$ne": bson.ObjectId(parameter_id)}
        })
        if existing_parameter:
            raise ValueError("Parameter with this name already exists")
        update_data["name"] = parameter_update.name
    
    if parameter_update.value is not None:
        update_data["value"] = parameter_update.value
    if parameter_update.description is not None:
        update_data["description"] = parameter_update.description
    if parameter_update.category is not None:
        update_data["category"] = parameter_update.category
    if parameter_update.datatype is not None:
        update_data["datatype"] = parameter_update.datatype
    if parameter_update.is_active is not None:
        update_data["is_active"] = parameter_update.is_active
    
    if update_data:
        update_data["updated_at"] = datetime.utcnow()
        try:
            result = await db.parameters.update_one(
                {"_id": bson.ObjectId(parameter_id)},
                {"$set": update_data}
            )
            if result.modified_count:
                return await get_parameter_by_id(parameter_id)
        except bson.errors.InvalidId:
            pass
    return None

async def delete_parameter(parameter_id: str) -> bool:
    db = await get_database()
    try:
        result = await db.parameters.delete_one({"_id": bson.ObjectId(parameter_id)})
        return result.deleted_count > 0
    except bson.errors.InvalidId:
        return False

async def get_parameter_categories() -> List[str]:
    db = await get_database()
    categories = await db.parameters.distinct("category")
    return [cat for cat in categories if cat]  # Filter out None values

# Strategy CRUD Operations
async def create_strategy(strategy: StrategyCreate, user_id: str) -> Strategy:
    db = await get_database()
    now = datetime.utcnow()
    
    strategy_data = {
        "name": strategy.name,
        "description": strategy.description,
        "status": strategy.status,
        "symbols": strategy.symbols,
        "max_positions": strategy.max_positions,
        "risk_per_trade": strategy.risk_per_trade,
        "is_active": strategy.is_active,
        "steps": [step.dict() for step in strategy.steps],
        "created_at": now,
        "updated_at": now,
        "created_by": user_id
    }
    
    result = await db.strategies.insert_one(strategy_data)
    strategy_data["id"] = str(result.inserted_id)
    
    return Strategy(**strategy_data)

async def get_strategies(skip: int = 0, limit: int = 100, status: Optional[str] = None, is_active: Optional[bool] = None) -> List[Strategy]:
    db = await get_database()
    strategies = []
    
    filter_query = {}
    if status:
        filter_query["status"] = status
    if is_active is not None:
        filter_query["is_active"] = is_active
    
    cursor = db.strategies.find(filter_query).skip(skip).limit(limit).sort("created_at", -1)
    async for strategy in cursor:
        strategy["id"] = str(strategy["_id"])
        strategies.append(Strategy(**strategy))
    return strategies

async def get_strategy_by_id(strategy_id: str) -> Optional[Strategy]:
    db = await get_database()
    try:
        strategy = await db.strategies.find_one({"_id": bson.ObjectId(strategy_id)})
        if strategy:
            strategy["id"] = str(strategy["_id"])
            return Strategy(**strategy)
    except bson.errors.InvalidId:
        pass
    return None

async def update_strategy(strategy_id: str, strategy_update: StrategyUpdate) -> Optional[Strategy]:
    db = await get_database()
    
    update_data = {}
    if strategy_update.name is not None:
        update_data["name"] = strategy_update.name
    if strategy_update.description is not None:
        update_data["description"] = strategy_update.description
    if strategy_update.status is not None:
        update_data["status"] = strategy_update.status
    if strategy_update.symbols is not None:
        update_data["symbols"] = strategy_update.symbols
    if strategy_update.max_positions is not None:
        update_data["max_positions"] = strategy_update.max_positions
    if strategy_update.risk_per_trade is not None:
        update_data["risk_per_trade"] = strategy_update.risk_per_trade
    if strategy_update.is_active is not None:
        update_data["is_active"] = strategy_update.is_active
    if strategy_update.steps is not None:
        update_data["steps"] = [step.dict() for step in strategy_update.steps]
    
    if update_data:
        update_data["updated_at"] = datetime.utcnow()
        try:
            result = await db.strategies.update_one(
                {"_id": bson.ObjectId(strategy_id)},
                {"$set": update_data}
            )
            if result.modified_count:
                return await get_strategy_by_id(strategy_id)
        except bson.errors.InvalidId:
            pass
    return None

async def delete_strategy(strategy_id: str) -> bool:
    db = await get_database()
    try:
        result = await db.strategies.delete_one({"_id": bson.ObjectId(strategy_id)})
        return result.deleted_count > 0
    except bson.errors.InvalidId:
        return False

async def get_strategies_by_symbol(symbol: str) -> List[Strategy]:
    db = await get_database()
    strategies = []
    
    cursor = db.strategies.find({
        "symbols": symbol,
        "is_active": True,
        "status": {"$in": ["active", "draft"]}
    }).sort("created_at", -1)
    
    async for strategy in cursor:
        strategy["id"] = str(strategy["_id"])
        strategies.append(Strategy(**strategy))
    return strategies

# Strategy Execution CRUD Operations
async def create_strategy_execution(execution: StrategyExecutionCreate) -> StrategyExecution:
    db = await get_database()
    now = datetime.utcnow()
    
    execution_data = {
        "strategy_id": execution.strategy_id,
        "trade_run_id": execution.trade_run_id,
        "status": "running",
        "started_at": now,
        "completed_at": None,
        "current_step_id": None,
        "execution_log": [],
        "positions_opened": 0,
        "positions_closed": 0,
        "total_pnl": 0.0
    }
    
    result = await db.strategy_executions.insert_one(execution_data)
    execution_data["id"] = str(result.inserted_id)
    
    return StrategyExecution(**execution_data)

async def get_strategy_executions(skip: int = 0, limit: int = 100, strategy_id: Optional[str] = None, trade_run_id: Optional[str] = None) -> List[StrategyExecution]:
    db = await get_database()
    executions = []
    
    filter_query = {}
    if strategy_id:
        filter_query["strategy_id"] = strategy_id
    if trade_run_id:
        filter_query["trade_run_id"] = trade_run_id
    
    cursor = db.strategy_executions.find(filter_query).skip(skip).limit(limit).sort("started_at", -1)
    async for execution in cursor:
        execution["id"] = str(execution["_id"])
        executions.append(StrategyExecution(**execution))
    return executions

async def get_strategy_execution_by_id(execution_id: str) -> Optional[StrategyExecution]:
    db = await get_database()
    try:
        execution = await db.strategy_executions.find_one({"_id": bson.ObjectId(execution_id)})
        if execution:
            execution["id"] = str(execution["_id"])
            return StrategyExecution(**execution)
    except bson.errors.InvalidId:
        pass
    return None

async def update_strategy_execution(execution_id: str, execution_update: StrategyExecutionUpdate) -> Optional[StrategyExecution]:
    db = await get_database()
    
    update_data = {}
    if execution_update.status is not None:
        update_data["status"] = execution_update.status
    if execution_update.current_step_id is not None:
        update_data["current_step_id"] = execution_update.current_step_id
    if execution_update.completed_at is not None:
        update_data["completed_at"] = execution_update.completed_at
    
    if update_data:
        try:
            result = await db.strategy_executions.update_one(
                {"_id": bson.ObjectId(execution_id)},
                {"$set": update_data}
            )
            if result.modified_count:
                return await get_strategy_execution_by_id(execution_id)
        except bson.errors.InvalidId:
            pass
    return None

async def add_execution_log(execution_id: str, log_entry: dict) -> bool:
    db = await get_database()
    try:
        result = await db.strategy_executions.update_one(
            {"_id": bson.ObjectId(execution_id)},
            {"$push": {"execution_log": log_entry}}
        )
        return result.modified_count > 0
    except bson.errors.InvalidId:
        return False

async def update_execution_stats(execution_id: str, positions_opened: int = 0, positions_closed: int = 0, total_pnl: float = 0.0) -> bool:
    db = await get_database()
    try:
        update_data = {}
        if positions_opened != 0:
            update_data["positions_opened"] = positions_opened
        if positions_closed != 0:
            update_data["positions_closed"] = positions_closed
        if total_pnl != 0.0:
            update_data["total_pnl"] = total_pnl
        
        if update_data:
            result = await db.strategy_executions.update_one(
                {"_id": bson.ObjectId(execution_id)},
                {"$inc": update_data}
            )
            return result.modified_count > 0
        return True
    except bson.errors.InvalidId:
        return False