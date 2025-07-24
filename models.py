from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.USER
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    hashed_password: Optional[str] = None

class UserInDB(UserBase):
    id: str
    hashed_password: str
    created_at: datetime
    updated_at: datetime

class User(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

# Tick Data Models
class TickData(BaseModel):
    ft: int  # Feed time
    token: int  # Token number
    e: str  # Exchange (e.g., 'NSE')
    lp: float  # Last price
    pc: float  # Price change
    rt: str  # Record time
    ts: str  # Trading symbol
    _id: Optional[str] = None

class OptionTickData(BaseModel):
    ft: int  # Feed time
    token: int  # Token number
    e: str  # Exchange (e.g., 'NSE')
    lp: float  # Last price
    pc: float  # Price change
    rt: str  # Record time
    ts: str  # Trading symbol
    _id: Optional[str] = None

class TickDataResponse(BaseModel):
    ticks: List[TickData]
    total_count: int
    database_name: str

class StartRunRequest(BaseModel):
    database_name: str
    interval_seconds: float = 1.0

class StartRunResponse(BaseModel):
    message: str
    database_name: str
    status: str
    interval_seconds: float
    hours_for_expiry: Optional[int] = None 

# Order Models
class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    SL = "sl"
    SLM = "slm"

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class OrderBase(BaseModel):
    symbol: str
    quantity: int
    side: OrderSide
    order_type: OrderType
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    user_id: str

class OrderCreate(OrderBase):
    pass

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    filled_quantity: Optional[int] = None
    average_price: Optional[float] = None

class Order(OrderBase):
    id: str
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    average_price: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    filled_at: Optional[datetime] = None

# Position Models
class PositionSummary(BaseModel):
    symbol: str
    total_buy_quantity: int = 0
    total_sell_quantity: int = 0
    net_position: int = 0
    total_buy_value: float = 0.0
    total_sell_value: float = 0.0
    average_buy_price: Optional[float] = None
    average_sell_price: Optional[float] = None
    open_buy_orders: int = 0
    open_sell_orders: int = 0
    open_buy_quantity: int = 0
    open_sell_quantity: int = 0
    open_buy_avg_price: Optional[float] = None
    open_sell_avg_price: Optional[float] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    current_price: Optional[float] = None

class PositionResponse(BaseModel):
    positions: List[PositionSummary]
    total_positions: int