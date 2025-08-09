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

# Trade Parameters Models
class ParameterBase(BaseModel):
    name: str
    value: str
    description: Optional[str] = None
    category: Optional[str] = None
    datatype: Optional[str] = None  # int, double, string, boolean, date, datetime, json
    is_active: bool = True



class ParameterCreate(ParameterBase):
    pass

class ParameterUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    datatype: Optional[str] = None
    is_active: Optional[bool] = None



class Parameter(ParameterBase):
    id: str
    created_at: datetime
    updated_at: datetime
    created_by: str

# Strategy Models
class StrategyConditionType(str, Enum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CROSSES_ABOVE = "price_crosses_above"
    PRICE_CROSSES_BELOW = "price_crosses_below"
    EMA_ABOVE = "ema_above"
    EMA_BELOW = "ema_below"
    EMA_CROSSES_ABOVE = "ema_crosses_above"
    EMA_CROSSES_BELOW = "ema_crosses_below"
    VOLUME_ABOVE = "volume_above"
    VOLUME_BELOW = "volume_below"
    TIME_AFTER = "time_after"
    TIME_BEFORE = "time_before"
    CUSTOM_INDICATOR = "custom_indicator"

class StrategyActionType(str, Enum):
    BUY_MARKET = "buy_market"
    SELL_MARKET = "sell_market"
    BUY_LIMIT = "buy_limit"
    SELL_LIMIT = "sell_limit"
    BUY_STOP = "buy_stop"
    SELL_STOP = "sell_stop"
    SET_STOP_LOSS = "set_stop_loss"
    SET_TAKE_PROFIT = "set_take_profit"
    CLOSE_POSITION = "close_position"
    WAIT = "wait"
    CUSTOM_ACTION = "custom_action"

class StrategyStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"

class StrategyStepType(str, Enum):
    CONDITION = "condition"
    ACTION = "action"
    LOOP = "loop"
    BRANCH = "branch"

class StrategyCondition(BaseModel):
    condition_type: StrategyConditionType
    symbol: Optional[str] = None
    value: float
    comparison_operator: str = ">="  # >=, <=, ==, !=, >, <
    time_value: Optional[str] = None  # For time-based conditions
    custom_indicator: Optional[str] = None  # For custom indicators
    description: Optional[str] = None

class StrategyAction(BaseModel):
    action_type: StrategyActionType
    symbol: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    wait_seconds: Optional[int] = None  # For wait actions
    custom_action: Optional[str] = None  # For custom actions
    description: Optional[str] = None

class StrategyStep(BaseModel):
    step_id: str
    step_type: StrategyStepType
    step_order: int
    condition: Optional[StrategyCondition] = None
    action: Optional[StrategyAction] = None
    next_step_id: Optional[str] = None  # For branching
    loop_start_step_id: Optional[str] = None  # For loops
    loop_end_step_id: Optional[str] = None  # For loops
    loop_count: Optional[int] = None  # For loops
    description: Optional[str] = None
    is_enabled: bool = True

class StrategyBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: StrategyStatus = StrategyStatus.DRAFT
    symbols: List[str] = []  # List of symbols this strategy applies to
    max_positions: Optional[int] = None  # Maximum concurrent positions
    risk_per_trade: Optional[float] = None  # Risk percentage per trade
    is_active: bool = True

class StrategyCreate(StrategyBase):
    steps: List[StrategyStep] = []

class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[StrategyStatus] = None
    symbols: Optional[List[str]] = None
    max_positions: Optional[int] = None
    risk_per_trade: Optional[float] = None
    is_active: Optional[bool] = None
    steps: Optional[List[StrategyStep]] = None

class Strategy(StrategyBase):
    id: str
    steps: List[StrategyStep] = []
    created_at: datetime
    updated_at: datetime
    created_by: str

class StrategyExecution(BaseModel):
    strategy_id: str
    trade_run_id: str  # Reference to the trade run
    status: str = "running"  # running, completed, stopped, error
    started_at: datetime
    completed_at: Optional[datetime] = None
    current_step_id: Optional[str] = None
    execution_log: List[dict] = []  # Log of executed steps and actions
    positions_opened: int = 0
    positions_closed: int = 0
    total_pnl: float = 0.0

class StrategyExecutionCreate(BaseModel):
    strategy_id: str
    trade_run_id: str

class StrategyExecutionUpdate(BaseModel):
    status: Optional[str] = None
    current_step_id: Optional[str] = None
    completed_at: Optional[datetime] = None

class StrategyResponse(BaseModel):
    strategies: List[Strategy]
    total_count: int

class StrategyExecutionResponse(BaseModel):
    executions: List[StrategyExecution]
    total_count: int

# ML Models
class MLTrainRequest(BaseModel):
    database_name: str
    horizon_minutes: int = 5
    lookback_minutes: int = 60
    test_size: float = 0.2

class MLTrainResponse(BaseModel):
    status: str
    message: Optional[str] = None
    samples: Optional[int] = None
    features: Optional[List[str]] = None
    accuracy: Optional[float] = None
    model_path: Optional[str] = None

class MLPredictResponse(BaseModel):
    status: str
    message: Optional[str] = None
    prediction: Optional[int] = None  # 0=down,1=up
    probabilities: Optional[dict] = None
    ft: Optional[int] = None
    price: Optional[float] = None
    minutes_to_expiry: Optional[float] = None