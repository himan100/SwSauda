from fastapi import FastAPI, Request, HTTPException, Depends, status, Form, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
from datetime import timedelta, datetime
import os
import subprocess
import json
import asyncio
import math
from pathlib import Path
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

from database import connect_to_mongo, connect_to_redis, close_mongo_connection, close_redis_connection, db, get_database, redis_client
from models import (UserCreate, UserUpdate, LoginRequest, Token, User, UserInDB, ProfileUpdate, PasswordChange, 
                   TickData, OptionTickData, TickDataResponse, StartRunRequest, StartRunResponse,
                   OrderCreate, OrderUpdate, Order, OrderStatus, PositionSummary, PositionResponse,
                   ParameterCreate, ParameterUpdate, Parameter, StrategyCreate, StrategyUpdate, Strategy, 
                   StrategyResponse, StrategyExecutionCreate, StrategyExecutionUpdate, StrategyExecution, 
                   StrategyExecutionResponse, StrategyStep, StrategyCondition, StrategyAction,
                   MLTrainRequest, MLTrainResponse, MLPredictResponse)
from auth import create_access_token, get_current_active_user, get_super_admin_user, get_admin_user, get_password_hash, verify_password
from crud import (create_user, get_users, update_user, delete_user, authenticate_user, create_super_admin,
                 create_order, get_order_by_id, get_orders, update_order, delete_order,
                 create_parameter, get_parameters, get_parameter_by_id, update_parameter, delete_parameter, get_parameter_categories, get_parameter_by_name,
                 create_strategy, get_strategies, get_strategy_by_id, update_strategy, delete_strategy, get_strategies_by_symbol,
                 create_strategy_execution, get_strategy_executions, get_strategy_execution_by_id, update_strategy_execution, add_execution_log, update_execution_stats)
from config import settings

# Store the currently selected database
selected_database_store = {}

# Redis tick storage functions
async def get_redis_tick_length() -> int:
    """Get the REDIS_LONG_TICK_LENGTH parameter from the database"""
    try:
        parameter = await get_parameter_by_name("REDIS_LONG_TICK_LENGTH")
        if parameter and parameter.is_active:
            return int(parameter.value)
        else:
            # Default value if parameter not found or inactive
            return 1000
    except (ValueError, TypeError):
        # Default value if parameter value is not a valid integer
        return 1000

async def get_redis_short_tick_length() -> int:
    """Get the REDIS_SHORT_TICK_LENGTH parameter from the database"""
    try:
        parameter = await get_parameter_by_name("REDIS_SHORT_TICK_LENGTH")
        if parameter and parameter.is_active:
            return int(parameter.value)
        else:
            # Default value if parameter not found or inactive
            return 50
    except (ValueError, TypeError):
        # Default value if parameter value is not a valid integer
        return 50

def calculate_ema(prices: list, period: int) -> float:
    """
    Calculate Exponential Moving Average (EMA)
    
    Args:
        prices: List of prices in chronological order (oldest first)
        period: EMA period
    
    Returns:
        EMA value
    """
    if not prices or len(prices) < period:
        return None
    
    # Use Simple Moving Average (SMA) as the initial EMA value
    sma = sum(prices[:period]) / period
    
    # Multiplier for EMA calculation
    multiplier = 2 / (period + 1)
    
    # Calculate EMA
    ema = sma
    for price in prices[period:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    
    return round(ema, 2)

async def calculate_index_emas(database_name: str) -> dict:
    """
    Calculate long and short EMAs for index ticks from Redis with progressive calculation
    
    Args:
        database_name: Name of the database
        
    Returns:
        Dictionary with long_ema and short_ema values
    """
    try:
        # Get the tick lengths for EMA calculations
        long_length = await get_redis_tick_length()
        short_length = await get_redis_short_tick_length()
        
        # Get all available index ticks from Redis (up to long_length)
        index_ticks = await get_ticks_from_redis(database_name, "indextick", long_length)
        
        if not index_ticks:
            return {"long_ema": None, "short_ema": None}
        
        # Sort ticks by feed time (ft) in ascending order (oldest first)
        index_ticks.sort(key=lambda x: x.get("ft", 0))
        
        # Extract prices
        prices = [tick.get("lp", 0) for tick in index_ticks if tick.get("lp") is not None]
        total_ticks = len(prices)
        
        # Calculate short EMA if we have enough ticks
        short_ema = None
        short_period_used = 0
        if total_ticks >= short_length:
            short_ema = calculate_ema(prices, short_length)
            short_period_used = short_length
        elif total_ticks > 0:
            # If we have some ticks but not enough for short EMA, use all available
            short_ema = calculate_ema(prices, total_ticks)
            short_period_used = total_ticks
        
        # Calculate long EMA using all available ticks (progressive)
        long_ema = None
        long_period_used = 0
        if total_ticks > 0:
            # Use all available ticks for long EMA (up to long_length)
            actual_long_period = min(total_ticks, long_length)
            long_ema = calculate_ema(prices, actual_long_period)
            long_period_used = actual_long_period
        
        return {
            "long_ema": long_ema,
            "short_ema": short_ema,
            "long_period": long_period_used,
            "short_period": short_period_used,
            "total_ticks": total_ticks
        }
        
    except Exception as e:
        print(f"Error calculating index EMAs: {e}")
        return {"long_ema": None, "short_ema": None}

async def flush_redis_for_database(database_name: str):
    """Flush Redis data for a specific database when trade run starts"""
    try:
        # Get all keys for this database
        pattern = f"ticks:{database_name}:*"
        keys = await redis_client.keys(pattern)
        
        if keys:
            # Delete all keys for this database
            await redis_client.delete(*keys)
            print(f"Flushed Redis data for database {database_name}: {len(keys)} keys deleted")
        else:
            print(f"No existing Redis data found for database {database_name}")
    except Exception as e:
        print(f"Error flushing Redis for database {database_name}: {e}")

async def store_tick_in_redis(tick_data: dict, tick_type: str, database_name: str):
    """Store tick data in Redis with FIFO behavior and proper sorting"""
    try:
        # Get the maximum number of ticks to store
        max_ticks = await get_redis_tick_length()
        
        if tick_type == "indextick":
            # For index ticks, use a single key
            redis_key = f"ticks:{database_name}:{tick_type}"
            
            # Add the tick data to the list
            tick_json = json.dumps(tick_data)
            await redis_client.lpush(redis_key, tick_json)
            
            # Trim the list to keep only the latest max_ticks
            await redis_client.ltrim(redis_key, 0, max_ticks - 1)
            
        elif tick_type == "optiontick":
            # For option ticks, store per token
            token = tick_data.get("token", "unknown")
            redis_key = f"ticks:{database_name}:{tick_type}:{token}"
            
            # Add the tick data to the list
            tick_json = json.dumps(tick_data)
            await redis_client.lpush(redis_key, tick_json)
            
            # Trim the list to keep only the latest max_ticks per token
            await redis_client.ltrim(redis_key, 0, max_ticks - 1)
        
        print(f"Stored {tick_type} tick in Redis for database {database_name}")
    except Exception as e:
        print(f"Error storing tick in Redis: {e}")

async def get_ticks_from_redis(database_name: str, tick_type: str, limit: int = None, token: str = None) -> list:
    """Get ticks from Redis for a specific database and tick type"""
    try:
        if tick_type == "indextick":
            redis_key = f"ticks:{database_name}:{tick_type}"
        elif tick_type == "optiontick":
            if token:
                # Get ticks for specific token
                redis_key = f"ticks:{database_name}:{tick_type}:{token}"
            else:
                # Get all option ticks (all tokens)
                pattern = f"ticks:{database_name}:{tick_type}:*"
                keys = await redis_client.keys(pattern)
                all_ticks = []
                
                for key in keys:
                    if limit:
                        tick_jsons = await redis_client.lrange(key, 0, limit - 1)
                    else:
                        tick_jsons = await redis_client.lrange(key, 0, -1)
                    
                    for tick_json in tick_jsons:
                        try:
                            tick_data = json.loads(tick_json)
                            all_ticks.append(tick_data)
                        except json.JSONDecodeError:
                            continue
                
                # Sort by feed time (ft) in descending order (latest first)
                all_ticks.sort(key=lambda x: x.get("ft", 0), reverse=True)
                
                # Apply limit if specified
                if limit:
                    all_ticks = all_ticks[:limit]
                
                return all_ticks
        else:
            return []
        
        # For index ticks or specific token option ticks
        if limit:
            tick_jsons = await redis_client.lrange(redis_key, 0, limit - 1)
        else:
            tick_jsons = await redis_client.lrange(redis_key, 0, -1)
        
        # Parse JSON strings back to dictionaries
        ticks = []
        for tick_json in tick_jsons:
            try:
                tick_data = json.loads(tick_json)
                ticks.append(tick_data)
            except json.JSONDecodeError:
                continue
        
        return ticks
    except Exception as e:
        print(f"Error getting ticks from Redis: {e}")
        return []

async def get_option_tokens_from_redis(database_name: str) -> list:
    """Get list of option tokens that have data in Redis"""
    try:
        pattern = f"ticks:{database_name}:optiontick:*"
        keys = await redis_client.keys(pattern)
        
        # Extract token numbers from keys
        tokens = []
        for key in keys:
            # Key format: ticks:database:optiontick:token
            parts = key.split(":")
            if len(parts) >= 4:
                token = parts[3]
                tokens.append(token)
        
        return tokens
    except Exception as e:
        print(f"Error getting option tokens from Redis: {e}")
        return []

def validate_parameter_value(value: str, datatype: str):
    """Validate that a parameter value matches its specified datatype"""
    try:
        if datatype == 'int':
            int(value)
        elif datatype == 'double':
            float(value)
        elif datatype == 'boolean':
            if value.lower() not in ['true', 'false', '1', '0', 'yes', 'no']:
                raise ValueError(f"Value '{value}' is not a valid boolean")
        elif datatype == 'date':
            # Basic date format validation (YYYY-MM-DD)
            import re
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                raise ValueError(f"Value '{value}' is not a valid date format (YYYY-MM-DD)")
        elif datatype == 'datetime':
            # Basic datetime format validation (YYYY-MM-DD HH:MM:SS)
            import re
            if not re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', value):
                raise ValueError(f"Value '{value}' is not a valid datetime format (YYYY-MM-DD HH:MM:SS)")
        elif datatype == 'json':
            import json
            json.loads(value)
        # string type doesn't need validation
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Value '{value}' does not match datatype '{datatype}': {str(e)}")

async def execute_mongo_views_script(database_name: str):
    """Execute the MongoDB analysis views script on the selected database"""
    try:
        # Path to the MongoDB JavaScript file
        script_path = os.path.join(os.path.dirname(__file__), "scripts", "mongo_data_analysis_views.js")
        
        if not os.path.exists(script_path):
            print(f"MongoDB views script not found at: {script_path}")
            return False
        
        # Create a temporary script with the correct database name
        temp_script_content = f"""
use('{database_name}');

// Drop existing views if they exist
try {{ db.v_index_base.drop(); }} catch(e) {{ print('v_index_base view does not exist, continuing...'); }}
try {{ db.v_option_pair_base.drop(); }} catch(e) {{ print('v_option_pair_base view does not exist, continuing...'); }}

// Create v_index_base view
db.createView(
  'v_index_base',
  'IndexTick',
  [
    {{
      $sort: {{ ft: 1 }}
    }},
    {{
      $limit: 150
    }},
    {{
      $match: {{
        $expr: {{
          $eq: [{{ $mod: ['$ft', 60] }}, 0]
        }}
      }}
    }},
    {{
      $group: {{
        _id: null,
        minFt: {{ $min: '$ft' }}
      }}
    }},
    {{
      $lookup: {{
        from: "IndexTick",
        let: {{ minFt: "$minFt" }},
        pipeline: [
          {{
            $match: {{
              $expr: {{ $eq: ["$ft", "$$minFt"] }}
            }}
          }},
          {{
            $lookup: {{
              from: "Index",
              localField: "token",
              foreignField: "token",
              as: "indexData"
            }}
          }},
          {{
            $unwind: "$indexData"
          }},
          {{
            $replaceRoot: {{
              newRoot: {{ $mergeObjects: [ "$$ROOT", "$indexData" ] }}
            }}
          }},
          {{
            $unset: "indexData"
          }},
          {{
            $addFields: {{
              ibase: {{
                $multiply: [
                  {{ $floor: {{ $divide: ["$lp", "$strkstep"] }} }},
                  "$strkstep"
                ]
              }},
              itop: {{
                $multiply: [
                  {{ $ceil: {{ $divide: ["$lp", "$strkstep"] }} }},
                  "$strkstep"
                ]
              }}
            }}
          }}
        ],
        as: "results"
      }}
    }},
    {{
      $unwind: "$results"
    }},
    {{
      $replaceRoot: {{ newRoot: "$results" }}
    }}
  ]
);

print('v_index_base view created successfully for database: {database_name}');

// Create v_option_pair_base view
db.createView(
  'v_option_pair_base',
  'IndexTick',
  [
    {{
      $match: {{
        $expr: {{
          $eq: [{{ $mod: ['$ft', 300] }}, 0]
        }}
      }}
    }},
    {{
      $lookup: {{
        from: "Index",
        localField: "token",
        foreignField: "token",
        as: "indexData"
      }}
    }},
    {{
      $unwind: "$indexData"
    }},
    {{
      $replaceRoot: {{
        newRoot: {{ $mergeObjects: [ "$$ROOT", "$indexData" ] }}
      }}
    }},
    {{
      $unset: "indexData"
    }},
    {{
      $addFields: {{
        ibase: {{
          $multiply: [
            {{ $floor: {{ $divide: ["$lp", "$strkstep"] }} }},
            "$strkstep"
          ]
        }},
        itop: {{
          $multiply: [
            {{ $ceil: {{ $divide: ["$lp", "$strkstep"] }} }},
            "$strkstep"
          ]
        }}
      }},
      {{
        $addFields: {{
          levels: {{ $range: [0, 10, 1] }}
        }}
      }},
      {{
        $unwind: "$levels"
      }},
      {{
        $addFields: {{
          level: "$levels",
          ce_strike: {{ $subtract: ["$ibase", {{ $multiply: ["$strkstep", "$levels"] }}] }},
          pe_strike: {{ $add: ["$itop", {{ $multiply: ["$strkstep", "$levels"] }}] }}
        }}
      }},
      {{
        $lookup: {{
          from: "Option",
          let: {{ strike: "$ce_strike" }},
          pipeline: [
            {{
              $match: {{
                $expr: {{
                  $and: [
                    {{ $eq: ["$strprc", "$$strike"] }},
                    {{ $eq: ["$optt", "CE"] }}
                  ]
                }}
              }}
            }}
          ],
          as: "ceOption"
        }}
      }},
      {{
        $lookup: {{
          from: "Option",
          let: {{ strike: "$pe_strike" }},
          pipeline: [
            {{
              $match: {{
                $expr: {{
                  $and: [
                    {{ $eq: ["$strprc", "$$strike"] }},
                    {{ $eq: ["$optt", "PE"] }}
                  ]
                }}
              }}
            }}
          ],
          as: "peOption"
        }}
      }},
      {{
        $addFields: {{
          ce_token: {{ $getField: {{ field: "token", input: {{ $arrayElemAt: ["$ceOption", 0] }} }} }},
          ce_tsym: {{ $getField: {{ field: "tsym", input: {{ $arrayElemAt: ["$ceOption", 0] }} }} }},
          pe_token: {{ $getField: {{ field: "token", input: {{ $arrayElemAt: ["$peOption", 0] }} }} }},
          pe_tsym: {{ $getField: {{ field: "tsym", input: {{ $arrayElemAt: ["$peOption", 0] }} }} }}
        }}
      }},
      {{
        $unset: ["ceOption", "peOption"]
      }},
      {{
        $lookup: {{
          from: "OptionTick",
          let: {{ ft: "$ft", token_var: "$ce_token" }},
          pipeline: [
            {{
              $match: {{
                $expr: {{
                  $and: [
                    {{ $eq: ["$ft", "$$ft"] }},
                    {{ $eq: ["$token", "$$token_var"] }}
                  ]
                }}
              }}
            }}
          ],
          as: "ceTick"
        }}
      }},
      {{
        $lookup: {{
          from: "OptionTick",
          let: {{ ft: "$ft", token_var: "$pe_token" }},
          pipeline: [
            {{
              $match: {{
                $expr: {{
                  $and: [
                    {{ $eq: ["$ft", "$$ft"] }},
                    {{ $eq: ["$token", "$$token_var"] }}
                  ]
                }}
              }}
            }}
          ],
          as: "peTick"
        }}
      }},
      {{
        $addFields: {{
          ce_lp: {{ $getField: {{ field: "lp", input: {{ $arrayElemAt: ["$ceTick", 0] }} }} }},
          pe_lp: {{ $getField: {{ field: "lp", input: {{ $arrayElemAt: ["$peTick", 0] }} }} }}
        }}
      }},
      {{
        $addFields: {{
          sum_lp: {{ $round: [{{ $add: ["$ce_lp", "$pe_lp"] }}, 2] }},
          diff: {{ $subtract: ["$pe_strike", "$ce_strike"] }}
        }}
      }},
      {{
        $addFields: {{
          risk_prec: {{ 
            $round: [
              {{ 
                $subtract: [
                  100, 
                  {{ 
                    $multiply: [
                      {{ 
                        $cond: [
                          {{ $eq: ["$sum_lp", 0] }}, 
                          0, 
                          {{ $divide: ["$diff", "$sum_lp"] }}
                        ] 
                      }}, 
                      100
                    ] 
                  }}
                ] 
              }}, 
              2
            ] 
          }}
        }}
      }},
      {{
        $unset: ["ceTick", "peTick", "levels"]
      }},
      {{
        $project: {{
          level: 1,
          ft: 1,
          e: 1,
          rt: 1,
          lotsize: 1,
          strkstep: 1,
          ibase: "$ce_strike",
          itop: "$pe_strike",
          ilp: "$lp",
          itoken: "$token",
          its: "$ts",
          ce_token: 1,
          pe_token: 1,
          ce_tsym: 1,
          pe_tsym: 1,
          ce_lp: 1,
          pe_lp: 1,
          sum_lp: 1,
          risk_prec: 1
        }}
      }}
    ]
  );

  print('v_option_pair_base view created successfully for database: {database_name}');
"""
        
        # Create temporary script file
        temp_script_path = os.path.join(os.path.dirname(__file__), "temp_views_script.js")
        with open(temp_script_path, 'w') as f:
            f.write(temp_script_content)
        
        try:
            # Try mongosh first, then fall back to mongo
            mongo_commands = ["mongosh", "mongo"]
            
            for mongo_cmd in mongo_commands:
                try:
                    # Check if the command exists
                    check_cmd = subprocess.run([mongo_cmd, "--version"], 
                                             capture_output=True, text=True, timeout=10)
                    if check_cmd.returncode == 0:
                        # Execute the MongoDB script
                        if mongo_cmd == "mongosh":
                            cmd = [mongo_cmd, "--quiet", "--file", temp_script_path]
                        else:
                            cmd = [mongo_cmd, "--quiet", temp_script_path]
                        
                        print(f"Executing MongoDB views script using {mongo_cmd} for database: {database_name}")
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                        
                        if result.returncode == 0:
                            print(f"MongoDB views script executed successfully for database: {database_name}")
                            if result.stdout:
                                print(f"Script output: {result.stdout}")
                            return True
                        else:
                            print(f"MongoDB views script failed for database: {database_name}")
                            print(f"Error: {result.stderr}")
                            # Try the next command
                            continue
                            
                except FileNotFoundError:
                    # Command not found, try the next one
                    continue
                except subprocess.TimeoutExpired:
                    print(f"Timeout while checking {mongo_cmd}")
                    continue
            
            # If we get here, none of the MongoDB commands worked
            print("Neither mongosh nor mongo command found or working")
            return False
                
        finally:
            # Clean up temporary script file
            if os.path.exists(temp_script_path):
                os.remove(temp_script_path)
                
    except Exception as e:
        print(f"Exception while executing MongoDB views script: {str(e)}")
        return False

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.tick_stream_task = None
        self.current_database = None
        self.is_streaming = False

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        if self.active_connections:
            # Send to all connected clients
            for connection in self.active_connections:
                try:
                    await connection.send_text(message)
                except:
                    # Remove disconnected clients
                    self.active_connections.remove(connection)

    def is_stream_running(self) -> bool:
        """Check if the tick stream is currently running"""
        return self.is_streaming and self.tick_stream_task and not self.tick_stream_task.done()

    async def start_tick_stream(self, database_name: str, interval_seconds: float = 1.0):
        """Start streaming tick data from the specified database"""
        if self.tick_stream_task and not self.tick_stream_task.done():
            self.tick_stream_task.cancel()
        
        self.current_database = database_name
        self.is_streaming = True
        self.tick_stream_task = asyncio.create_task(self._stream_ticks(database_name, interval_seconds))

    async def stop_tick_stream(self):
        """Stop the tick data stream"""
        print("Stopping tick stream...")
        if self.tick_stream_task and not self.tick_stream_task.done():
            self.tick_stream_task.cancel()
            try:
                await self.tick_stream_task
            except asyncio.CancelledError:
                print("Tick stream task cancelled successfully")
            except Exception as e:
                print(f"Error cancelling tick stream task: {e}")
        self.current_database = None
        self.is_streaming = False
        print("Tick stream stopped")

    async def _stream_ticks(self, database_name: str, interval_seconds: float = 1.0):
        """Stream tick data from MongoDB with proper interval control"""
        try:
            # Connect to the specific database
            database = db.client[database_name]
            indextick_collection = database["IndexTick"]
            
            # Check if OptionTick collection exists
            try:
                optiontick_collection = database["OptionTick"]  # Exact collection name
                optiontick_exists = True
                print(f"OptionTick collection found in database {database_name}")
            except Exception as e:
                print(f"OptionTick collection not found in database {database_name}: {e}")
                optiontick_exists = False
            
            print(f"Starting tick stream from database {database_name} with {interval_seconds}s interval")
            
            # Stream IndexTick data and find matching OptionTick data for each
            print("Starting synchronized IndexTick and OptionTick streaming...")
            cursor = indextick_collection.find({}).sort("ft", 1)  # Oldest first
            
            initial_count = 0
            async for doc in cursor:
                # Check if stream was stopped
                if not self.is_streaming or (self.tick_stream_task and self.tick_stream_task.done()):
                    print("DEBUG: Tick stream was stopped during streaming")
                    return
                
                # Get the feed time for this IndexTick
                current_ft = doc.get("ft", 0)
                
                # Send IndexTick data
                tick_data = TickData(
                    ft=doc.get("ft", 0),
                    token=doc.get("token", 0),
                    e=doc.get("e", ""),
                    lp=doc.get("lp", 0.0),
                    pc=doc.get("pc", 0.0),
                    rt=doc.get("rt", ""),
                    ts=doc.get("ts", ""),
                    _id=str(doc.get("_id", ""))
                )
                
                tick_dict = tick_data.dict()
                tick_dict["data_type"] = "indextick"
                await self.broadcast(json.dumps(tick_dict))
                
                # Store index tick in Redis
                await store_tick_in_redis(tick_dict, "indextick", database_name)
                
                # Calculate and broadcast EMA data
                try:
                    ema_data = await calculate_index_emas(database_name)
                    if ema_data["long_ema"] is not None or ema_data["short_ema"] is not None:
                        ema_message = {
                            "data_type": "ema_data",
                            "long_ema": ema_data["long_ema"],
                            "short_ema": ema_data["short_ema"],
                            "long_period": ema_data["long_period"],
                            "short_period": ema_data["short_period"],
                            "total_ticks": ema_data["total_ticks"],
                            "timestamp": datetime.now().isoformat()
                        }
                        await self.broadcast(json.dumps(ema_message))
                except Exception as e:
                    print(f"Error calculating EMAs: {e}")
                
                # Find and send all OptionTick data with the same feed time
                if optiontick_exists:
                    option_cursor = optiontick_collection.find({"ft": current_ft})
                    option_count = 0
                    async for option_doc in option_cursor:
                        option_tick_data = OptionTickData(
                            ft=option_doc.get("ft", 0),
                            token=option_doc.get("token", 0),
                            e=option_doc.get("e", ""),
                            lp=option_doc.get("lp", 0.0),
                            pc=option_doc.get("pc", 0.0),
                            rt=option_doc.get("rt", ""),
                            ts=option_doc.get("ts", ""),
                            _id=str(option_doc.get("_id", ""))
                        )
                        
                        option_tick_dict = option_tick_data.dict()
                        option_tick_dict["data_type"] = "optiontick"
                        await self.broadcast(json.dumps(option_tick_dict))
                        
                        # Store option tick in Redis
                        await store_tick_in_redis(option_tick_dict, "optiontick", database_name)
                        option_count += 1
                    
                    if option_count > 0:
                        print(f"IndexTick {current_ft}: sent {option_count} matching OptionTicks")
                
                initial_count += 1
                
                # Apply interval between each IndexTick
                await asyncio.sleep(interval_seconds)
                
                # Progress update every 100 ticks
                if initial_count % 100 == 0:
                    print(f"Processed {initial_count} IndexTicks...")
            
            print(f"Completed streaming {initial_count} IndexTicks with matching OptionTicks")
            
            # Get the latest timestamp to start monitoring for new data
            latest_doc = await indextick_collection.find_one({}, sort=[("ft", -1)])
            last_ft = latest_doc.get("ft", 0) if latest_doc else 0
            
            print(f"Monitoring for new ticks after timestamp: {last_ft}")
            
            # Now monitor for new ticks with configurable interval
            while self.is_streaming:
                # Check if stream was stopped
                if self.tick_stream_task and self.tick_stream_task.done():
                    print("Tick stream was stopped during monitoring")
                    break
                
                # Check for new ticks
                new_ticks = indextick_collection.find({"ft": {"$gt": last_ft}}).sort("ft", 1)
                new_tick_count = 0
                
                async for new_doc in new_ticks:
                    # Check if stream was stopped
                    if not self.is_streaming or (self.tick_stream_task and self.tick_stream_task.done()):
                        print("DEBUG: Tick stream was stopped during new tick monitoring")
                        return
                    
                    # Get the feed time for this IndexTick
                    current_ft = new_doc.get("ft", 0)
                    
                    # Send IndexTick data
                    tick_data = TickData(
                        ft=new_doc.get("ft", 0),
                        token=new_doc.get("token", 0),
                        e=new_doc.get("e", ""),
                        lp=new_doc.get("lp", 0.0),
                        pc=new_doc.get("pc", 0.0),
                        rt=new_doc.get("rt", ""),
                        ts=new_doc.get("ts", ""),
                        _id=str(new_doc.get("_id", ""))
                    )
                    
                    tick_dict = tick_data.dict()
                    tick_dict["data_type"] = "indextick"
                    await self.broadcast(json.dumps(tick_dict))
                    
                    # Store index tick in Redis
                    await store_tick_in_redis(tick_dict, "indextick", database_name)
                    
                    # Calculate and broadcast EMA data
                    try:
                        ema_data = await calculate_index_emas(database_name)
                        if ema_data["long_ema"] is not None or ema_data["short_ema"] is not None:
                            ema_message = {
                                "data_type": "ema_data",
                                "long_ema": ema_data["long_ema"],
                                "short_ema": ema_data["short_ema"],
                                "long_period": ema_data["long_period"],
                                "short_period": ema_data["short_period"],
                                "total_ticks": ema_data["total_ticks"],
                                "timestamp": datetime.now().isoformat()
                            }
                            await self.broadcast(json.dumps(ema_message))
                    except Exception as e:
                        print(f"Error calculating EMAs: {e}")
                    
                    # Find and send all OptionTick data with the same feed time
                    if optiontick_exists:
                        option_cursor = optiontick_collection.find({"ft": current_ft})
                        option_count = 0
                        async for option_doc in option_cursor:
                            option_tick_data = OptionTickData(
                                ft=option_doc.get("ft", 0),
                                token=option_doc.get("token", 0),
                                e=option_doc.get("e", ""),
                                lp=option_doc.get("lp", 0.0),
                                pc=option_doc.get("pc", 0.0),
                                rt=option_doc.get("rt", ""),
                                ts=option_doc.get("ts", ""),
                                _id=str(option_doc.get("_id", ""))
                            )
                            
                            option_tick_dict = option_tick_data.dict()
                            option_tick_dict["data_type"] = "optiontick"
                            await self.broadcast(json.dumps(option_tick_dict))
                            
                            # Store option tick in Redis
                            await store_tick_in_redis(option_tick_dict, "optiontick", database_name)
                            option_count += 1
                        
                        if option_count > 0:
                            print(f"New IndexTick {current_ft}: sent {option_count} matching OptionTicks")
                    
                    new_tick_count += 1
                    last_ft = current_ft
                
                if new_tick_count > 0:
                    print(f"Processed {new_tick_count} new IndexTicks")
                
                # Calculate and broadcast EMA data periodically (even if no new ticks)
                try:
                    ema_data = await calculate_index_emas(database_name)
                    if ema_data["long_ema"] is not None or ema_data["short_ema"] is not None:
                        ema_message = {
                            "data_type": "ema_data",
                            "long_ema": ema_data["long_ema"],
                            "short_ema": ema_data["short_ema"],
                            "long_period": ema_data["long_period"],
                            "short_period": ema_data["short_period"],
                            "total_ticks": ema_data["total_ticks"],
                            "timestamp": datetime.now().isoformat()
                        }
                        await self.broadcast(json.dumps(ema_message))
                except Exception as e:
                    print(f"Error calculating EMAs: {e}")
                
                # Apply interval between checks
                await asyncio.sleep(interval_seconds)
            
        except Exception as e:
            print(f"Error starting tick stream: {e}")
        finally:
            print("Tick stream ended")

# Create connection manager instances
manager = ConnectionManager()
positions_manager = ConnectionManager()

app = FastAPI(title="SwSauda", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Favicon route
@app.get("/favicon.png", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.png")

# Templates
templates = Jinja2Templates(directory="templates")

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    await connect_to_redis()
    await create_super_admin()

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()
    await close_redis_connection()

# Authentication routes
@app.post("/api/login", response_model=Token)
async def login(login_data: LoginRequest):
    user = await authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/logout")
async def logout():
    return {"message": "Successfully logged out"}

# User management routes (admin only)
@app.post("/api/users", response_model=User)
async def create_new_user(
    user: UserCreate,
    current_user: User = Depends(get_admin_user)
):
    try:
        created_user = await create_user(user)
        return User(
            id=created_user.id,
            email=created_user.email,
            full_name=created_user.full_name,
            role=created_user.role,
            is_active=created_user.is_active,
            created_at=created_user.created_at,
            updated_at=created_user.updated_at
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/users", response_model=list[User])
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_admin_user)
):
    users = await get_users(skip=skip, limit=limit)
    return [
        User(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        for user in users
    ]

@app.put("/api/users/{user_id}", response_model=User)
async def update_user_by_id(
    user_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(get_admin_user)
):
    updated_user = await update_user(user_id, user_update)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(
        id=updated_user.id,
        email=updated_user.email,
        full_name=updated_user.full_name,
        role=updated_user.role,
        is_active=updated_user.is_active,
        created_at=updated_user.created_at,
        updated_at=updated_user.updated_at
    )

@app.delete("/api/users/{user_id}")
async def delete_user_by_id(
    user_id: str,
    current_user: User = Depends(get_admin_user)
):
    success = await delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}

# Profile routes
@app.get("/api/profile", response_model=User)
async def get_profile(current_user: User = Depends(get_current_active_user)):
    return current_user

@app.put("/api/profile", response_model=User)
async def update_profile(
    profile_update: ProfileUpdate,
    current_user: User = Depends(get_current_active_user)
):
    user_update = UserUpdate(
        full_name=profile_update.full_name,
        email=profile_update.email
    )
    updated_user = await update_user(current_user.id, user_update)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(
        id=updated_user.id,
        email=updated_user.email,
        full_name=updated_user.full_name,
        role=updated_user.role,
        is_active=updated_user.is_active,
        created_at=updated_user.created_at,
        updated_at=updated_user.updated_at
    )

@app.put("/api/profile/password")
async def change_password(
    password_change: PasswordChange,
    current_user: UserInDB = Depends(get_current_active_user)
):
    if not verify_password(password_change.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    user_update = UserUpdate(hashed_password=get_password_hash(password_change.new_password))
    
    updated_user = await update_user(current_user.id, user_update)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "Password changed successfully"}

# Database management routes
@app.get("/api/databases")
async def get_databases(current_user: User = Depends(get_admin_user)):
    """Get list of all MongoDB databases"""
    try:
        databases = await db.client.list_database_names()
        # Filter out system databases
        user_databases = [db_name for db_name in databases if db_name not in ['admin', 'local', 'config']]
        return {"databases": user_databases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching databases: {str(e)}")

@app.delete("/api/databases/{database_name}")
async def delete_database(database_name: str, current_user: User = Depends(get_admin_user)):
    """Delete a MongoDB database"""
    try:
        # Prevent deletion of system databases
        if database_name in ['admin', 'local', 'config']:
            raise HTTPException(status_code=400, detail="Cannot delete system databases")
        
        # Drop the database
        await db.client.drop_database(database_name)
        return {"message": f"Database '{database_name}' deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting database: {str(e)}")

@app.get("/api/backups")
async def get_backups(current_user: User = Depends(get_admin_user)):
    """Get list of backup folders"""
    try:
        backups_dir = Path("Backups")
        if not backups_dir.exists():
            return {"backups": []}
        
        backup_folders = []
        for date_folder in backups_dir.iterdir():
            if date_folder.is_dir() and date_folder.name.isdigit() and len(date_folder.name) == 8:
                # This is a DDMMYYYY folder
                # Look for database folders inside (like Pinaka)
                for db_folder in date_folder.iterdir():
                    if db_folder.is_dir():
                        # Check if database folder has any database files (BSON files)
                        database_files = list(db_folder.glob("*.bson"))
                        backup_folders.append({
                            "name": date_folder.name,  # DDMMYYYY format
                            "path": str(date_folder),
                            "is_empty": len(database_files) == 0,
                            "file_count": len(database_files),
                            "database_name": db_folder.name  # The actual database name
                        })
        
        return {"backups": backup_folders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching backups: {str(e)}")

@app.post("/api/backups/{database_name}")
async def create_backup(database_name: str, current_user: User = Depends(get_admin_user)):
    """Create a backup of a database"""
    try:
        # Prevent backup of system databases
        if database_name in ['admin', 'local', 'config']:
            raise HTTPException(status_code=400, detail="Cannot backup system databases")
        
        backups_dir = Path("Backups")
        backups_dir.mkdir(exist_ok=True)
        
        # Create DDMMYYYY folder
        date_folder = backups_dir / datetime.now().strftime('%d%m%Y')
        date_folder.mkdir(exist_ok=True)
        
        # Use mongodump to create backup
        # Output to DDMMYYYY folder, which will create database_name subfolder
        cmd = [
            "mongodump",
            "--db", database_name,
            "--out", str(date_folder)  # Output to DDMMYYYY folder
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Backup failed: {result.stderr}")
        
        return {"message": f"Backup created successfully", "backup_path": str(date_folder)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating backup: {str(e)}")

from pydantic import BaseModel

class RestoreRequest(BaseModel):
    backup_folder: str

@app.post("/api/restore/{database_name}")
async def restore_database(database_name: str, restore_request: RestoreRequest, current_user: User = Depends(get_admin_user)):
    """Restore a database from backup"""
    try:
        print(f"Restore request: database_name={database_name}, backup_folder={restore_request.backup_folder}")
        
        # Look for backup in DDMMYYYY/database_name folder
        backup_path = Path("Backups") / restore_request.backup_folder / database_name
        print(f"Backup path: {backup_path}")
        
        if not backup_path.exists():
            print(f"Backup path does not exist: {backup_path}")
            raise HTTPException(status_code=404, detail="Backup folder not found")
        
        # Check if backup folder contains BSON files
        bson_files = list(backup_path.glob("*.bson"))
        print(f"Found {len(bson_files)} BSON files in backup")
        
        if not bson_files:
            raise HTTPException(status_code=404, detail="No backup files found in the backup folder")
        
        # Convert DDMMYYYY to YYYYMMDD for restored database name
        backup_date = restore_request.backup_folder
        if len(backup_date) == 8 and backup_date.isdigit():
            # Convert DDMMYYYY to YYYYMMDD
            day = int(backup_date[:2])
            month = int(backup_date[2:4])
            year = int(backup_date[4:8])
            yyyymmdd = f"{year:04d}{month:02d}{day:02d}"
        else:
            yyyymmdd = backup_date
        
        # Add prefix to database name: prefix_YYYYMMDD
        prefixed_database_name = f"{settings.database_prefix}_{yyyymmdd}"
        print(f"Restoring to database: {prefixed_database_name}")
        
        # Use mongorestore to restore backup (Pinaka is the database folder)
        cmd = [
            "mongorestore",
            "--db", prefixed_database_name,
            "--drop",  # Drop existing database before restore
            str(backup_path)  # Restore from Pinaka folder directly
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print(f"Command return code: {result.returncode}")
        if result.stdout:
            print(f"Command stdout: {result.stdout}")
        if result.stderr:
            print(f"Command stderr: {result.stderr}")
        
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Restore failed: {result.stderr}")
        
        return {"message": f"Database '{prefixed_database_name}' restored successfully"}
    except Exception as e:
        print(f"Exception during restore: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error restoring database: {str(e)}")

@app.delete("/api/backups/{backup_folder}")
async def delete_backup(backup_folder: str, current_user: User = Depends(get_admin_user)):
    """Delete a backup folder"""
    try:
        # Look for backup in YYYYMMDD folder
        backup_path = Path("Backups") / backup_folder
        
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup folder not found")
        
        # Remove the backup folder and all its contents
        import shutil
        shutil.rmtree(backup_path)
        
        return {"message": f"Backup '{backup_folder}' deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting backup: {str(e)}")

@app.get("/api/config/database-prefix")
async def get_database_prefix(current_user: User = Depends(get_admin_user)):
    print(f"[DEBUG] DATABASE_PREFIX from settings: {settings.database_prefix}")
    return {"database_prefix": settings.database_prefix}

@app.get("/api/databases/prefixed")
async def get_prefixed_databases(current_user: User = Depends(get_admin_user)):
    """Get list of all MongoDB databases with the configured prefix"""
    try:
        databases = await db.client.list_database_names()
        prefix = settings.database_prefix
        user_databases = [db_name for db_name in databases if db_name.startswith(prefix)]
        return {"databases": user_databases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching databases: {str(e)}")

# Frontend routes
@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    return templates.TemplateResponse("profile.html", {"request": request})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})

@app.get("/roles", response_class=HTMLResponse)
async def roles_page(request: Request):
    return templates.TemplateResponse("roles.html", {"request": request})

@app.get("/databases", response_class=HTMLResponse)
async def databases_page(request: Request):
    return templates.TemplateResponse("databases.html", {"request": request})

@app.get("/ml-training", response_class=HTMLResponse)
async def ml_training_page(request: Request):
    return templates.TemplateResponse("ml_training.html", {"request": request})

@app.get("/trade-run", response_class=HTMLResponse)
async def trade_run_page(request: Request):
    return templates.TemplateResponse("trade_run.html", {"request": request})

@app.get("/positions", response_class=HTMLResponse)
async def positions_page(request: Request):
    return templates.TemplateResponse("positions.html", {"request": request})

@app.get("/parameters", response_class=HTMLResponse)
async def parameters_page(request: Request):
    return templates.TemplateResponse("parameters.html", {"request": request})

@app.post("/api/trade-run")
async def trade_run_api(database_name: str = Form(...), current_user: User = Depends(get_admin_user)):
    selected_database_store["selected"] = database_name
    # Clear existing orders and positions view when a new trade run starts
    try:
        db_instance = await get_database()
        # Delete all orders
        delete_result = await db_instance.orders.delete_many({})
        # Drop positions view if exists so it will be recreated on next access
        try:
            await db_instance.drop_collection("v_positions")
        except Exception:
            pass
        # Optionally broadcast an empty update so UI clears immediately
        try:
            await broadcast_positions_update()
        except Exception as e:
            print(f"Broadcast after clearing failed: {e}")
        return {"message": f"Selected database set to {database_name}. Cleared {delete_result.deleted_count} orders and reset positions."}
    except Exception as e:
        return {"message": f"Selected database set to {database_name}, but failed to clear positions/orders: {e}"}

@app.get("/api/selected-database")
async def get_selected_database(current_user: User = Depends(get_admin_user)):
    return {"selected_database": selected_database_store.get("selected", "")}

@app.post("/api/unset-selected-database")
async def unset_selected_database(current_user: User = Depends(get_admin_user)):
    selected_database_store["selected"] = ""
    return {"message": "Selected database has been unset."}

@app.post("/api/execute-views/{database_name}")
async def execute_views_for_database(database_name: str, current_user: User = Depends(get_admin_user)):
    """Execute MongoDB analysis views script for a specific database"""
    try:
        # Validate that the database exists
        databases = await db.client.list_database_names()
        if database_name not in databases:
            raise HTTPException(status_code=404, detail=f"Database '{database_name}' not found")
        
        # Execute MongoDB views script for the selected database
        print(f"Executing MongoDB views script for database: {database_name}")
        views_success = await execute_mongo_views_script(database_name)
        
        if views_success:
            return {"message": f"MongoDB analysis views created successfully for database '{database_name}'", "success": True}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to create MongoDB analysis views for database '{database_name}'")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing views script: {str(e)}")

async def calculate_trading_hours_to_expiry(rt: str, expiry_timestamp: int) -> int:
    """
    Calculate trading hours from rt to expiry considering market hours and weekdays.
    
    Args:
        rt: Record time string (e.g., "2025-07-18 09:16:00")
        expiry_timestamp: Expiry timestamp in seconds
    
    Returns:
        Total trading hours until expiry
    """
    try:
        # Set timezone to Asia/Kolkata
        ist = ZoneInfo("Asia/Kolkata")
        
        # Convert expiry timestamp to datetime in IST
        expiry_dt = datetime.fromtimestamp(expiry_timestamp, tz=ist)
        print(f"Expiry datetime (IST): {expiry_dt}")
        
        # Parse rt datetime string (format: "2025-07-18 09:16:00")
        try:
            # Parse the rt datetime string
            rt_dt = datetime.fromisoformat(rt)
            # If rt doesn't have timezone info, assume it's in IST
            if rt_dt.tzinfo is None:
                rt_dt = rt_dt.replace(tzinfo=ist)
            print(f"RT datetime (IST): {rt_dt}")
        except ValueError:
            print(f"Error parsing rt datetime: {rt}")
            return 0
        
        # Calculate total unique days between rt and expiry
        rt_date = rt_dt.date()
        expiry_date = expiry_dt.date()
        total_days = (expiry_date - rt_date).days
        print(f"Total days between rt and expiry: {total_days}")
        
        if total_days < 0:
            print("Expiry is in the past relative to rt")
            return 0
        
        total_hours = 0
        
        # Market closing time is 15:30 (3:30 PM)
        market_close_hour = 15
        market_close_minute = 30
        
        # Calculate hours for day one (from rt to 15:30 or expiry)
        if total_days == 0:
            # Same day expiry - calculate hours from rt to expiry time
            if expiry_dt.hour < market_close_hour or (expiry_dt.hour == market_close_hour and expiry_dt.minute <= market_close_minute):
                # Expiry is before market close
                rt_minutes = rt_dt.hour * 60 + rt_dt.minute
                expiry_minutes = expiry_dt.hour * 60 + expiry_dt.minute
                if expiry_minutes > rt_minutes:
                    hours_day_one = (expiry_minutes - rt_minutes) / 60.0
                    total_hours += hours_day_one
                    print(f"Same day expiry - hours from rt to expiry: {hours_day_one}")
            else:
                # Expiry is after market close, count till market close
                rt_minutes = rt_dt.hour * 60 + rt_dt.minute
                market_close_minutes = market_close_hour * 60 + market_close_minute
                if market_close_minutes > rt_minutes:
                    hours_day_one = (market_close_minutes - rt_minutes) / 60.0
                    total_hours += hours_day_one
                    print(f"Same day - hours from rt to market close: {hours_day_one}")
        else:
            # Multi-day calculation
            # Day 1: From rt to 15:30
            rt_minutes = rt_dt.hour * 60 + rt_dt.minute
            market_close_minutes = market_close_hour * 60 + market_close_minute
            if market_close_minutes > rt_minutes:
                hours_day_one = (market_close_minutes - rt_minutes) / 60.0
                total_hours += hours_day_one
                print(f"Day 1 ({rt_date}) - hours from rt to market close: {hours_day_one}")
            
            # Days 2 to expiry day: Add 6 hours for each weekday
            current_check_date = rt_date + timedelta(days=1)
            
            while current_check_date <= expiry_date:
                # Check if it's a weekday (Monday=0, Sunday=6)
                if current_check_date.weekday() < 5:  # Monday to Friday
                    if current_check_date == expiry_date:
                        # On expiry day, calculate from market open to expiry time or market close
                        market_open_minutes = 9 * 60 + 15  # 9:15 AM
                        if expiry_dt.hour < market_close_hour or (expiry_dt.hour == market_close_hour and expiry_dt.minute <= market_close_minute):
                            # Expiry is before market close
                            expiry_minutes = expiry_dt.hour * 60 + expiry_dt.minute
                            if expiry_minutes > market_open_minutes:
                                hours_expiry_day = (expiry_minutes - market_open_minutes) / 60.0
                                total_hours += hours_expiry_day
                                print(f"Expiry day ({expiry_date}) - hours from market open to expiry: {hours_expiry_day}")
                        else:
                            # Expiry is after market close, count full trading day
                            total_hours += 6  # Full trading day
                            print(f"Expiry day ({expiry_date}) - full trading day: 6 hours")
                    else:
                        # Full trading day (6 hours)
                        total_hours += 6
                        print(f"Weekday {current_check_date} - full trading day: 6 hours")
                else:
                    print(f"Weekend {current_check_date} - skipped")
                
                current_check_date += timedelta(days=1)
        
        # Return floor of total hours
        result = math.floor(total_hours)
        print(f"Total trading hours to expiry: {result}")
        return result
        
    except Exception as e:
        print(f"Error in calculate_trading_hours_to_expiry: {str(e)}")
        return 0

@app.post("/api/start-run", response_model=StartRunResponse)
async def start_run(request: StartRunRequest, current_user: User = Depends(get_admin_user)):
    """Start a trading run with the specified database"""
    try:
        # Validate that the database exists
        databases = await db.client.list_database_names()
        if request.database_name not in databases:
            raise HTTPException(status_code=404, detail=f"Database '{request.database_name}' not found")
        
        # Execute MongoDB views script for the selected database
        print(f"Executing MongoDB views script for database: {request.database_name}")
        views_success = await execute_mongo_views_script(request.database_name)
        if not views_success:
            print(f"Warning: MongoDB views script execution failed for database: {request.database_name}")
            # Continue with the run even if views creation fails
        else:
            print(f"MongoDB views created successfully for database: {request.database_name}")
        
        # Get the specific database
        target_db = db.client[request.database_name]
        
        # Initialize hours_for_expiry
        hours_for_expiry = None
        
        # Step 1: Get ibase and index ft from view v_index_base
        try:
            v_index_base_cursor = target_db.v_index_base.find().limit(1)
            v_index_base_doc = await v_index_base_cursor.to_list(length=1)
            
            if not v_index_base_doc:
                print("Warning: No data found in v_index_base view")
                ibase = None
                index_ft = None
            else:
                ibase = v_index_base_doc[0].get('ibase')
                index_ft = v_index_base_doc[0].get('ft')
                rt = v_index_base_doc[0].get('rt')  # Get rt from v_index_base
                print(f"Retrieved from v_index_base - ibase: {ibase}, index_ft: {index_ft}, rt: {rt}")
                
                if ibase is not None and index_ft is not None and rt is not None:
                    # Step 2: Get token from Option collection where ibase matches strprc and optt = "CE"
                    option_cursor = target_db.Option.find({"strprc": ibase, "optt": "CE"}).limit(1)
                    option_doc = await option_cursor.to_list(length=1)
                    
                    if not option_doc:
                        print(f"Warning: No CE option found with strprc: {ibase}")
                        option_token = None
                    else:
                        option_token = option_doc[0].get('token')
                        print(f"Retrieved from Option collection - token: {option_token}")
                        
                        if option_token is not None:
                            # Step 3: Get expiry from FyersSymbolMaster where token matches
                            fyers_cursor = target_db.FyersSymbolMaster.find({"token": option_token}).limit(1)
                            fyers_doc = await fyers_cursor.to_list(length=1)
                            
                            if not fyers_doc:
                                print(f"Warning: No FyersSymbolMaster record found with token: {option_token}")
                                expiry = None
                            else:
                                expiry = fyers_doc[0].get('expiry')
                                print(f"Retrieved from FyersSymbolMaster - expiry: {expiry}")
                                
                                if expiry is not None:
                                    # Step 4-6: Complex expiry calculation
                                    hours_for_expiry = await calculate_trading_hours_to_expiry(rt, expiry)
                                    print(f"Calculated hours for expiry: {hours_for_expiry}")
                                else:
                                    print("Warning: Expiry value is None")
                        else:
                            print("Warning: Option token is None")
                else:
                    print("Warning: ibase, index_ft, or rt is None")
        except Exception as e:
            print(f"Error during expiry calculation: {str(e)}")
        
        # Store the selected database for the run
        selected_database_store["run_database"] = request.database_name
        selected_database_store["run_interval"] = request.interval_seconds
        
        # Flush Redis data for this database to ensure clean start
        await flush_redis_for_database(request.database_name)
        
        # Start WebSocket tick stream with the provided interval
        await manager.start_tick_stream(request.database_name, request.interval_seconds)
        
        return StartRunResponse(
            message=f"Trading run started with database '{request.database_name}'{' (views created)' if views_success else ' (views creation failed)'}",
            database_name=request.database_name,
            status="started",
            interval_seconds=request.interval_seconds,
            hours_for_expiry=hours_for_expiry
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting run: {str(e)}")

@app.post("/api/stop-run")
async def stop_run(current_user: User = Depends(get_admin_user)):
    """Stop the current trading run"""
    try:
        if "run_database" in selected_database_store:
            database_name = selected_database_store["run_database"]
            del selected_database_store["run_database"]
            if "run_interval" in selected_database_store:
                del selected_database_store["run_interval"]
            
            # Stop WebSocket tick stream
            await manager.stop_tick_stream()
            
            return {"message": f"Trading run stopped for database '{database_name}'"}
        else:
            return {"message": "No active run to stop"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping run: {str(e)}")

@app.get("/api/tick-data", response_model=TickDataResponse)
async def get_tick_data(
    skip: int = 0, 
    limit: int = 100, 
    current_user: User = Depends(get_admin_user)
):
    """Get tick data from the indextick collection of the selected database"""
    try:
        # Get the database name from the run
        database_name = selected_database_store.get("run_database")
        if not database_name:
            raise HTTPException(status_code=400, detail="No active run. Please start a run first.")
        
        # Connect to the specific database
        database = db.client[database_name]
        
        # Get the IndexTick collection (note the capital letters)
        indextick_collection = database["IndexTick"]
        
        # Get total count
        total_count = await indextick_collection.count_documents({})
        
        # Fetch tick data with pagination
        cursor = indextick_collection.find({}).skip(skip).limit(limit).sort("ft", -1)  # Sort by feed time descending
        
        ticks = []
        async for doc in cursor:
            # Convert MongoDB document to TickData model
            tick_data = TickData(
                ft=doc.get("ft", 0),
                token=doc.get("token", 0),
                e=doc.get("e", ""),
                lp=doc.get("lp", 0.0),
                pc=doc.get("pc", 0.0),
                rt=doc.get("rt", ""),
                ts=doc.get("ts", ""),
                _id=str(doc.get("_id", ""))
            )
            ticks.append(tick_data)
        
        return TickDataResponse(
            ticks=ticks,
            total_count=total_count,
            database_name=database_name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tick data: {str(e)}")

@app.get("/api/redis-ticks/{tick_type}")
async def get_redis_ticks(
    tick_type: str,
    limit: int = 100,
    token: str = None,
    current_user: User = Depends(get_admin_user)
):
    """Get tick data from Redis for a specific tick type"""
    try:
        # Get the database name from the run
        database_name = selected_database_store.get("run_database")
        if not database_name:
            raise HTTPException(status_code=400, detail="No active run. Please start a run first.")
        
        # Validate tick type
        if tick_type not in ["indextick", "optiontick"]:
            raise HTTPException(status_code=400, detail="Invalid tick type. Must be 'indextick' or 'optiontick'")
        
        # Get ticks from Redis
        ticks = await get_ticks_from_redis(database_name, tick_type, limit, token)
        
        return {
            "ticks": ticks,
            "total_count": len(ticks),
            "database_name": database_name,
            "tick_type": tick_type,
            "token": token
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Redis tick data: {str(e)}")

@app.get("/api/redis-option-tokens")
async def get_redis_option_tokens(current_user: User = Depends(get_admin_user)):
    """Get list of option tokens that have data in Redis"""
    try:
        # Get the database name from the run
        database_name = selected_database_store.get("run_database")
        if not database_name:
            raise HTTPException(status_code=400, detail="No active run. Please start a run first.")
        
        # Get option tokens from Redis
        tokens = await get_option_tokens_from_redis(database_name)
        
        return {
            "tokens": tokens,
            "total_count": len(tokens),
            "database_name": database_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Redis option tokens: {str(e)}")

# Option symbols endpoint
@app.get("/api/options")
async def get_option_symbols(limit: int = 1000, current_user: User = Depends(get_current_active_user)):
    """Return list of available option symbols from the Option collection of the active run database (falls back to default)."""
    try:
        run_db_name = selected_database_store.get("run_database")
        # Use run database if available else default configured db
        target_db = db.client[run_db_name] if run_db_name else db
        # Projection to only necessary fields
        cursor = target_db["Option"].find({}, {"token": 1, "tsym": 1, "strprc": 1, "optt": 1}).limit(limit)
        options = []
        async for doc in cursor:
            options.append({
                "token": doc.get("token"),
                "tsym": doc.get("tsym"),
                "strprc": doc.get("strprc"),
                "optt": doc.get("optt")
            })
        return {"options": options, "count": len(options), "database_name": run_db_name or settings.database_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching option symbols: {str(e)}")

@app.get("/api/run-status")
async def get_run_status(current_user: User = Depends(get_admin_user)):
    """Get the current run status"""
    database_name = selected_database_store.get("run_database", "")
    interval_seconds = selected_database_store.get("run_interval", 1.0)
    is_stream_running = manager.is_stream_running()
    return {
        "is_running": bool(database_name),
        "database_name": database_name,
        "interval_seconds": interval_seconds,
        "is_stream_running": is_stream_running
    }

@app.get("/api/index-emas")
async def get_index_emas(current_user: User = Depends(get_admin_user)):
    """Get long and short EMA calculations for index ticks"""
    try:
        # Get the database name from the run
        database_name = selected_database_store.get("run_database")
        if not database_name:
            raise HTTPException(status_code=400, detail="No active run. Please start a run first.")
        
        # Calculate EMAs
        ema_data = await calculate_index_emas(database_name)
        
        return {
            "database_name": database_name,
            "long_ema": ema_data["long_ema"],
            "short_ema": ema_data["short_ema"],
            "long_period": ema_data["long_period"],
            "short_period": ema_data["short_period"],
            "total_ticks": ema_data["total_ticks"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating EMAs: {str(e)}")

# Orders API endpoints
@app.post("/api/orders", response_model=Order)
async def create_order_api(order: OrderCreate, current_user: User = Depends(get_current_active_user)):
    """Create a new order"""
    try:
        # Set the user_id from the current user
        order.user_id = current_user.id
        new_order = await create_order(order)
        
        # Trigger WebSocket update
        await broadcast_positions_update()
        
        return new_order
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/orders", response_model=List[Order])
async def get_orders_api(
    symbol: Optional[str] = None,
    status: Optional[OrderStatus] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_active_user)
):
    """Get orders for the current user"""
    try:
        orders = await get_orders(user_id=current_user.id, symbol=symbol, status=status, limit=limit, skip=skip)
        return orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/{order_id}", response_model=Order)
async def get_order_api(order_id: str, current_user: User = Depends(get_current_active_user)):
    """Get a specific order by ID"""
    try:
        order = await get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Check if the order belongs to the current user
        if order.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return order
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/orders/{order_id}", response_model=Order)
async def update_order_api(
    order_id: str, 
    order_update: OrderUpdate, 
    current_user: User = Depends(get_current_active_user)
):
    """Update an order"""
    try:
        # First check if the order exists and belongs to the user
        existing_order = await get_order_by_id(order_id)
        if not existing_order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if existing_order.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        updated_order = await update_order(order_id, order_update)
        if not updated_order:
            raise HTTPException(status_code=400, detail="Failed to update order")
        
        # Trigger WebSocket update
        await broadcast_positions_update()
        
        return updated_order
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/orders/{order_id}")
async def delete_order_api(order_id: str, current_user: User = Depends(get_current_active_user)):
    """Delete an order"""
    try:
        # First check if the order exists and belongs to the user
        existing_order = await get_order_by_id(order_id)
        if not existing_order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if existing_order.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        success = await delete_order(order_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete order")
        
        # Trigger WebSocket update
        await broadcast_positions_update()
        
        return {"message": "Order deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Parameters API endpoints
@app.post("/api/parameters", response_model=Parameter)
async def create_parameter_api(parameter: ParameterCreate, current_user: User = Depends(get_current_active_user)):
    """Create a new parameter"""
    try:
        # Validate datatype if specified
        if parameter.datatype:
            validate_parameter_value(parameter.value, parameter.datatype)
        
        created_parameter = await create_parameter(parameter, current_user.id)
        return created_parameter
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/parameters", response_model=List[Parameter])
async def get_parameters_api(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
):
    """Get all parameters with optional filtering"""
    try:
        parameters = await get_parameters(skip=skip, limit=limit, category=category)
        return parameters
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/parameters/{parameter_id}", response_model=Parameter)
async def get_parameter_api(parameter_id: str, current_user: User = Depends(get_current_active_user)):
    """Get a specific parameter by ID"""
    try:
        parameter = await get_parameter_by_id(parameter_id)
        if not parameter:
            raise HTTPException(status_code=404, detail="Parameter not found")
        return parameter
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/parameters/{parameter_id}", response_model=Parameter)
async def update_parameter_api(
    parameter_id: str,
    parameter_update: ParameterUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """Update a parameter"""
    try:
        # Validate datatype if both value and datatype are being updated
        if parameter_update.value is not None and parameter_update.datatype:
            validate_parameter_value(parameter_update.value, parameter_update.datatype)
        elif parameter_update.value is not None:
            # If only value is being updated, get the current parameter to check datatype
            current_parameter = await get_parameter_by_id(parameter_id)
            if current_parameter and current_parameter.datatype:
                validate_parameter_value(parameter_update.value, current_parameter.datatype)
        
        updated_parameter = await update_parameter(parameter_id, parameter_update)
        if not updated_parameter:
            raise HTTPException(status_code=404, detail="Parameter not found")
        return updated_parameter
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/parameters/{parameter_id}")
async def delete_parameter_api(parameter_id: str, current_user: User = Depends(get_current_active_user)):
    """Delete a parameter"""
    try:
        success = await delete_parameter(parameter_id)
        if not success:
            raise HTTPException(status_code=404, detail="Parameter not found")
        return {"message": "Parameter deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/parameters/categories")
async def get_parameter_categories_api(current_user: User = Depends(get_current_active_user)):
    """Get all parameter categories"""
    try:
        categories = await get_parameter_categories()
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/parameters/import")
async def import_parameters_api(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user)
):
    """Import parameters from Excel/CSV file"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Check file extension
        if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
            raise HTTPException(status_code=400, detail="Only Excel (.xlsx, .xls) and CSV files are supported")
        
        # Read file content
        content = await file.read()
        
        # Parse based on file type
        if file.filename.lower().endswith('.csv'):
            import csv
            import io
            text = content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(text))
            data = list(csv_reader)
        else:
            # Excel file
            import pandas as pd
            import io
            df = pd.read_excel(io.BytesIO(content))
            data = df.to_dict('records')
        
        # Validate and import data
        imported_count = 0
        errors = []
        
        for row in data:
            try:
                # Validate required fields
                if not row.get('name') or not row.get('value'):
                    errors.append(f"Row missing required fields: {row}")
                    continue
                
                # Create parameter
                parameter_data = ParameterCreate(
                    name=row['name'].strip(),
                    value=str(row['value']).strip(),
                    description=row.get('description', '').strip() if row.get('description') else None,
                    category=row.get('category', '').strip() if row.get('category') else None,
                    datatype=row.get('datatype', '').strip() if row.get('datatype') else None,
                    is_active=row.get('is_active', True) if 'is_active' in row else True
                )
                
                await create_parameter(parameter_data, current_user.id)
                imported_count += 1
                
            except Exception as e:
                errors.append(f"Error importing row {row}: {str(e)}")
        
        return {
            "message": f"Import completed. {imported_count} parameters imported successfully.",
            "imported_count": imported_count,
            "errors": errors
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@app.get("/api/parameters/template")
async def download_parameter_template(current_user: User = Depends(get_current_active_user)):
    """Download a sample Excel template for parameter imports"""
    try:
        import pandas as pd
        import io
        
        # Create sample data
        sample_data = [
            {
                'name': 'max_position_size',
                'value': '1000',
                'description': 'Maximum position size for any trade',
                'category': 'Risk Management',
                'datatype': 'int',
                'is_active': True
            },
            {
                'name': 'stop_loss_percentage',
                'value': '2.5',
                'description': 'Stop loss percentage for trades',
                'category': 'Risk Management',
                'datatype': 'double',
                'is_active': True
            },
            {
                'name': 'profit_target_percentage',
                'value': '5.0',
                'description': 'Profit target percentage for trades',
                'category': 'Risk Management',
                'datatype': 'double',
                'is_active': True
            },
            {
                'name': 'trading_hours_start',
                'value': '09:15',
                'description': 'Trading session start time',
                'category': 'Trading Schedule',
                'datatype': 'string',
                'is_active': True
            },
            {
                'name': 'trading_hours_end',
                'value': '15:30',
                'description': 'Trading session end time',
                'category': 'Trading Schedule',
                'datatype': 'string',
                'is_active': True
            },
            {
                'name': 'enable_auto_trading',
                'value': 'true',
                'description': 'Enable automatic trading',
                'category': 'Trading Settings',
                'datatype': 'boolean',
                'is_active': True
            }
        ]
        
        # Create DataFrame
        df = pd.DataFrame(sample_data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Parameters', index=False)
        
        output.seek(0)
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            io.BytesIO(output.read()),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=parameters_template.xlsx"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate template: {str(e)}")

# Positions API endpoints
@app.get("/api/positions", response_model=PositionResponse)
async def get_positions_api(current_user: User = Depends(get_current_active_user)):
    """Get positions for the current user"""
    try:
        positions = await aggregate_positions(user_id=current_user.id)
        return PositionResponse(positions=positions, total_positions=len(positions))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching positions: {str(e)}")

async def aggregate_positions(user_id: str | None, raw: bool = False):
    """Aggregate positions directly from orders collection.
    Args:
        user_id: filter by user if provided
        raw: if True return list of dicts, else list of PositionSummary
    """
    db_instance = await get_database()
    match_stage = {"$match": {}}
    if user_id:
        match_stage["$match"]["user_id"] = user_id
    pipeline = [
        match_stage,
        {"$group": {
            "_id": {"symbol": "$symbol", "user_id": "$user_id"},
            "total_buy_quantity": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "filled"]}]}, "$filled_quantity", 0]}},
            "total_sell_quantity": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "filled"]}]}, "$filled_quantity", 0]}},
            "total_buy_value": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "filled"]}]}, {"$multiply": ["$filled_quantity", "$average_price"]}, 0]}},
            "total_sell_value": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "filled"]}]}, {"$multiply": ["$filled_quantity", "$average_price"]}, 0]}},
            "open_buy_orders": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "pending"]}]}, 1, 0]}},
            "open_sell_orders": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "pending"]}]}, 1, 0]}},
            "open_buy_quantity": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "pending"]}]}, {"$subtract": ["$quantity", "$filled_quantity"]}, 0]}},
            "open_sell_quantity": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "pending"]}]}, {"$subtract": ["$quantity", "$filled_quantity"]}, 0]}},
            "open_buy_value": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "pending"]}, {"$ne": ["$price", None]}]}, {"$multiply": [{"$subtract": ["$quantity", "$filled_quantity"]}, "$price"]}, 0]}},
            "open_sell_value": {"$sum": {"$cond": [{"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "pending"]}, {"$ne": ["$price", None]}]}, {"$multiply": [{"$subtract": ["$quantity", "$filled_quantity"]}, "$price"]}, 0]}}
        }},
        {"$addFields": {
            "symbol": "$_id.symbol",
            "user_id": "$_id.user_id",
            "net_position": {"$subtract": ["$total_buy_quantity", "$total_sell_quantity"]},
            "average_buy_price": {"$cond": [{"$gt": ["$total_buy_quantity", 0]}, {"$divide": ["$total_buy_value", "$total_buy_quantity"]}, None]},
            "average_sell_price": {"$cond": [{"$gt": ["$total_sell_quantity", 0]}, {"$divide": ["$total_sell_value", "$total_sell_quantity"]}, None]},
            "open_buy_avg_price": {"$cond": [{"$gt": ["$open_buy_quantity", 0]}, {"$divide": ["$open_buy_value", "$open_buy_quantity"]}, None]},
            "open_sell_avg_price": {"$cond": [{"$gt": ["$open_sell_quantity", 0]}, {"$divide": ["$open_sell_value", "$open_sell_quantity"]}, None]},
            "realized_pnl": {"$cond": [
                {"$and": [{"$gt": ["$total_buy_quantity", 0]}, {"$gt": ["$total_sell_quantity", 0]}]},
                {"$multiply": [
                    {"$min": ["$total_buy_quantity", "$total_sell_quantity"]},
                    {"$subtract": [
                        {"$divide": ["$total_sell_value", "$total_sell_quantity"]},
                        {"$divide": ["$total_buy_value", "$total_buy_quantity"]}
                    ]}
                ]},
                0
            ]}
        }},
        {"$project": {"_id": 0}}
    ]
    cursor = db_instance.orders.aggregate(pipeline)
    results = []
    async for doc in cursor:
        doc["unrealized_pnl"] = 0.0
        doc["current_price"] = None
        results.append(doc)
    if raw:
        return results
    return [PositionSummary(**r) for r in results]

async def execute_position_views_script():
    """Execute the MongoDB position views script"""
    try:
        db_instance = await get_database()
        
        # Drop existing view if it exists
        try:
            await db_instance.drop_collection("v_positions")
        except:
            pass
        
        # Create the positions view using aggregation pipeline
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "symbol": "$symbol",
                        "user_id": "$user_id"
                    },
                    "total_buy_quantity": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "filled"]}]},
                                "$filled_quantity",
                                0
                            ]
                        }
                    },
                    "total_sell_quantity": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "filled"]}]},
                                "$filled_quantity",
                                0
                            ]
                        }
                    },
                    "total_buy_value": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "filled"]}]},
                                {"$multiply": ["$filled_quantity", "$average_price"]},
                                0
                            ]
                        }
                    },
                    "total_sell_value": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "filled"]}]},
                                {"$multiply": ["$filled_quantity", "$average_price"]},
                                0
                            ]
                        }
                    },
                    "open_buy_orders": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "pending"]}]},
                                1,
                                0
                            ]
                        }
                    },
                    "open_sell_orders": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "pending"]}]},
                                1,
                                0
                            ]
                        }
                    },
                    "open_buy_quantity": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "pending"]}]},
                                {"$subtract": ["$quantity", "$filled_quantity"]},
                                0
                            ]
                        }
                    },
                    "open_sell_quantity": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "pending"]}]},
                                {"$subtract": ["$quantity", "$filled_quantity"]},
                                0
                            ]
                        }
                    },
                    "open_buy_value": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "pending"]}, {"$ne": ["$price", None]}]},
                                {"$multiply": [{"$subtract": ["$quantity", "$filled_quantity"]}, "$price"]},
                                0
                            ]
                        }
                    },
                    "open_sell_value": {
                        "$sum": {
                            "$cond": [
                                {"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "pending"]}, {"$ne": ["$price", None]}]},
                                {"$multiply": [{"$subtract": ["$quantity", "$filled_quantity"]}, "$price"]},
                                0
                            ]
                        }
                    }
                }
            },
            {
                "$addFields": {
                    "symbol": "$_id.symbol",
                    "user_id": "$_id.user_id",
                    "net_position": {"$subtract": ["$total_buy_quantity", "$total_sell_quantity"]},
                    "average_buy_price": {
                        "$cond": [
                            {"$gt": ["$total_buy_quantity", 0]},
                            {"$divide": ["$total_buy_value", "$total_buy_quantity"]},
                            None
                        ]
                    },
                    "average_sell_price": {
                        "$cond": [
                            {"$gt": ["$total_sell_quantity", 0]},
                            {"$divide": ["$total_sell_value", "$total_sell_quantity"]},
                            None
                        ]
                    },
                    "open_buy_avg_price": {
                        "$cond": [
                            {"$gt": ["$open_buy_quantity", 0]},
                            {"$divide": ["$open_buy_value", "$open_buy_quantity"]},
                            None
                        ]
                    },
                    "open_sell_avg_price": {
                        "$cond": [
                            {"$gt": ["$open_sell_quantity", 0]},
                            {"$divide": ["$open_sell_value", "$open_sell_quantity"]},
                            None
                        ]
                    },
                    "realized_pnl": {
                        "$cond": [
                            {"$and": [{"$gt": ["$total_buy_quantity", 0]}, {"$gt": ["$total_sell_quantity", 0]}]},
                            {
                                "$multiply": [
                                    {"$min": ["$total_buy_quantity", "$total_sell_quantity"]},
                                    {
                                        "$subtract": [
                                            {"$divide": ["$total_sell_value", "$total_sell_quantity"]},
                                            {"$divide": ["$total_buy_value", "$total_buy_quantity"]}
                                        ]
                                    }
                                ]
                            },
                            0
                        ]
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "symbol": 1,
                    "user_id": 1,
                    "total_buy_quantity": 1,
                    "total_sell_quantity": 1,
                    "net_position": 1,
                    "total_buy_value": 1,
                    "total_sell_value": 1,
                    "average_buy_price": 1,
                    "average_sell_price": 1,
                    "open_buy_orders": 1,
                    "open_sell_orders": 1,
                    "open_buy_quantity": 1,
                    "open_sell_quantity": 1,
                    "open_buy_avg_price": 1,
                    "open_sell_avg_price": 1,
                    "realized_pnl": 1
                }
            }
        ]
        
        # Create the view
        await db_instance.create_collection("v_positions", viewOn="orders", pipeline=pipeline)
        
    except Exception as e:
        print(f"Error creating positions view: {e}")

async def broadcast_positions_update():
    """Broadcast position updates to all connected WebSocket clients"""
    try:
        # Aggregate for all users
        positions = await aggregate_positions(user_id=None, raw=True)

        # Get recent orders
        orders = await get_orders(limit=50)
        orders_data = []
        for order in orders:
            orders_data.append({
                "id": order.id,
                "symbol": order.symbol,
                "quantity": order.quantity,
                "filled_quantity": order.filled_quantity,
                "side": order.side,
                "order_type": order.order_type,
                "price": order.price,
                "status": order.status,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "average_price": order.average_price
            })

        # Broadcast to all connected clients
        await positions_manager.broadcast(json.dumps({
            "type": "positions_update",
            "positions": positions
        }))
        await positions_manager.broadcast(json.dumps({
            "type": "orders_update",
            "orders": orders_data
        }))
    except Exception as exc:
        print(f"Error broadcasting positions update: {exc}")

@app.websocket("/ws/tick-data")
async def websocket_tick_data(websocket: WebSocket):
    """WebSocket endpoint for real-time tick data streaming"""
    await manager.connect(websocket)
    try:
        # Send initial connection message
        await manager.send_personal_message(
            json.dumps({"type": "connection", "message": "Connected to tick data stream"}),
            websocket
        )
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "start_stream":
                    database_name = message.get("database_name")
                    interval_seconds = message.get("interval_seconds", 1.0)
                    if database_name:
                        await manager.start_tick_stream(database_name, interval_seconds)
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "stream_started", 
                                "database": database_name,
                                "interval_seconds": interval_seconds
                            }),
                            websocket
                        )
                
                elif message.get("type") == "stop_stream":
                    await manager.stop_tick_stream()
                    await manager.send_personal_message(
                        json.dumps({"type": "stream_stopped"}),
                        websocket
                    )
                
            except WebSocketDisconnect:
                manager.disconnect(websocket)
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                await manager.send_personal_message(
                    json.dumps({"type": "error", "message": str(e)}),
                    websocket
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)

@app.websocket("/ws/positions")
async def websocket_positions(websocket: WebSocket):
    """WebSocket endpoint for real-time positions and orders updates"""
    await positions_manager.connect(websocket)
    try:
        while True:
            # Send periodic position updates
            await asyncio.sleep(1)
            # Keep the connection alive
            await websocket.ping()
    except WebSocketDisconnect:
        positions_manager.disconnect(websocket)
    except Exception as e:
        print(f"Positions WebSocket connection error: {e}")
        positions_manager.disconnect(websocket)

@app.websocket("/ws/ema-data")
async def websocket_ema_data(websocket: WebSocket):
    """WebSocket endpoint for real-time EMA data streaming"""
    await manager.connect(websocket)
    try:
        # Send initial connection message
        await manager.send_personal_message(
            json.dumps({"type": "connection", "message": "Connected to EMA data stream"}),
            websocket
        )
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "start_ema_stream":
                    database_name = message.get("database_name")
                    interval_seconds = message.get("interval_seconds", 1.0)
                    if database_name:
                        # Start periodic EMA calculation and streaming
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "ema_stream_started", 
                                "database": database_name,
                                "interval_seconds": interval_seconds
                            }),
                            websocket
                        )
                        
                        # Start EMA streaming task
                        print(f"Starting EMA streaming task for database: {database_name}")
                        asyncio.create_task(stream_ema_data(websocket, database_name, interval_seconds))
                
                elif message.get("type") == "stop_ema_stream":
                    await manager.send_personal_message(
                        json.dumps({"type": "ema_stream_stopped"}),
                        websocket
                    )
                
            except WebSocketDisconnect:
                manager.disconnect(websocket)
                break
            except Exception as e:
                print(f"EMA WebSocket error: {e}")
                await manager.send_personal_message(
                    json.dumps({"type": "error", "message": str(e)}),
                    websocket
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"EMA WebSocket connection error: {e}")
        manager.disconnect(websocket)

async def stream_ema_data(websocket: WebSocket, database_name: str, interval_seconds: float = 1.0):
    """Stream EMA data from Redis at regular intervals"""
    print(f"EMA streaming task started for database: {database_name}")
    try:
        while True:
            print(f"EMA streaming loop iteration for {database_name}")
            
            # Check if WebSocket is still connected
            try:
                await websocket.ping()
                print(f"WebSocket ping successful for {database_name}")
            except:
                print(f"EMA WebSocket disconnected for {database_name}")
                break
            
            # Calculate EMAs from Redis data
            try:
                print(f"Calculating EMAs for {database_name}...")
                ema_data = await calculate_index_emas(database_name)
                print(f"EMA calculation result: {ema_data}")
                
                # Send EMA data if at least one EMA is available
                if ema_data["long_ema"] is not None or ema_data["short_ema"] is not None:
                    ema_message = {
                        "data_type": "ema_data",
                        "long_ema": ema_data["long_ema"],
                        "short_ema": ema_data["short_ema"],
                        "long_period": ema_data["long_period"],
                        "short_period": ema_data["short_period"],
                        "total_ticks": ema_data["total_ticks"],
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send_text(json.dumps(ema_message))
                    print(f"Sent EMA data: {ema_message}")
                else:
                    print("No EMA data available to send")
            except Exception as e:
                print(f"Error calculating EMAs: {e}")
            
            # Wait for next interval
            print(f"Waiting {interval_seconds} seconds before next EMA calculation...")
            await asyncio.sleep(interval_seconds)
            
    except Exception as e:
        print(f"Error in EMA streaming: {e}")

# Strategy API Endpoints

@app.post("/api/strategies", response_model=Strategy)
async def create_strategy_api(strategy: StrategyCreate, current_user: User = Depends(get_current_active_user)):
    """Create a new trading strategy"""
    try:
        return await create_strategy(strategy, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating strategy: {str(e)}")

@app.get("/api/strategies", response_model=StrategyResponse)
async def get_strategies_api(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_active_user)
):
    """Get all strategies with optional filtering"""
    try:
        strategies = await get_strategies(skip=skip, limit=limit, status=status, is_active=is_active)
        total_count = len(strategies)  # In a real app, you'd get total count separately
        return StrategyResponse(strategies=strategies, total_count=total_count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching strategies: {str(e)}")

@app.get("/api/strategies/{strategy_id}", response_model=Strategy)
async def get_strategy_api(strategy_id: str, current_user: User = Depends(get_current_active_user)):
    """Get a specific strategy by ID"""
    try:
        strategy = await get_strategy_by_id(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return strategy
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching strategy: {str(e)}")

@app.put("/api/strategies/{strategy_id}", response_model=Strategy)
async def update_strategy_api(
    strategy_id: str,
    strategy_update: StrategyUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """Update a strategy"""
    try:
        strategy = await update_strategy(strategy_id, strategy_update)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return strategy
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating strategy: {str(e)}")

@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy_api(strategy_id: str, current_user: User = Depends(get_current_active_user)):
    """Delete a strategy"""
    try:
        success = await delete_strategy(strategy_id)
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return {"message": "Strategy deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting strategy: {str(e)}")

@app.get("/api/strategies/symbol/{symbol}")
async def get_strategies_by_symbol_api(symbol: str, current_user: User = Depends(get_current_active_user)):
    """Get strategies that apply to a specific symbol"""
    try:
        strategies = await get_strategies_by_symbol(symbol)
        return {"strategies": strategies, "total_count": len(strategies)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching strategies for symbol: {str(e)}")

# Strategy Execution API Endpoints
@app.post("/api/strategy-executions", response_model=StrategyExecution)
async def create_strategy_execution_api(
    execution: StrategyExecutionCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Create a new strategy execution"""
    try:
        # Validate that the strategy exists
        strategy = await get_strategy_by_id(execution.strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Validate that the strategy is active
        if not strategy.is_active or strategy.status not in ["active", "draft"]:
            raise HTTPException(status_code=400, detail="Strategy is not active")
        
        return await create_strategy_execution(execution)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating strategy execution: {str(e)}")

@app.get("/api/strategy-executions", response_model=StrategyExecutionResponse)
async def get_strategy_executions_api(
    skip: int = 0,
    limit: int = 100,
    strategy_id: Optional[str] = None,
    trade_run_id: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
):
    """Get strategy executions with optional filtering"""
    try:
        executions = await get_strategy_executions(
            skip=skip, 
            limit=limit, 
            strategy_id=strategy_id, 
            trade_run_id=trade_run_id
        )
        total_count = len(executions)  # In a real app, you'd get total count separately
        return StrategyExecutionResponse(executions=executions, total_count=total_count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching strategy executions: {str(e)}")

@app.get("/api/strategy-executions/{execution_id}", response_model=StrategyExecution)
async def get_strategy_execution_api(execution_id: str, current_user: User = Depends(get_current_active_user)):
    """Get a specific strategy execution by ID"""
    try:
        execution = await get_strategy_execution_by_id(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Strategy execution not found")
        return execution
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching strategy execution: {str(e)}")

@app.put("/api/strategy-executions/{execution_id}", response_model=StrategyExecution)
async def update_strategy_execution_api(
    execution_id: str,
    execution_update: StrategyExecutionUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """Update a strategy execution"""
    try:
        execution = await update_strategy_execution(execution_id, execution_update)
        if not execution:
            raise HTTPException(status_code=404, detail="Strategy execution not found")
        return execution
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating strategy execution: {str(e)}")

@app.post("/api/strategy-executions/{execution_id}/log")
async def add_execution_log_api(
    execution_id: str,
    log_entry: dict,
    current_user: User = Depends(get_current_active_user)
):
    """Add a log entry to a strategy execution"""
    try:
        # Add timestamp to log entry
        log_entry["timestamp"] = datetime.utcnow().isoformat()
        log_entry["user_id"] = current_user.id
        
        success = await add_execution_log(execution_id, log_entry)
        if not success:
            raise HTTPException(status_code=404, detail="Strategy execution not found")
        return {"message": "Log entry added successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding log entry: {str(e)}")

@app.post("/api/strategy-executions/{execution_id}/stats")
async def update_execution_stats_api(
    execution_id: str,
    positions_opened: int = 0,
    positions_closed: int = 0,
    total_pnl: float = 0.0,
    current_user: User = Depends(get_current_active_user)
):
    """Update statistics for a strategy execution"""
    try:
        success = await update_execution_stats(
            execution_id, 
            positions_opened=positions_opened,
            positions_closed=positions_closed,
            total_pnl=total_pnl
        )
        if not success:
            raise HTTPException(status_code=404, detail="Strategy execution not found")
        return {"message": "Statistics updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating statistics: {str(e)}")

@app.post("/api/strategy-executions/{execution_id}/start")
async def start_strategy_execution_api(
    execution_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Start executing a strategy"""
    try:
        # Get the execution
        execution = await get_strategy_execution_by_id(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Strategy execution not found")
        
        # Get the strategy
        strategy = await get_strategy_by_id(execution.strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Check if strategy is active
        if not strategy.is_active or strategy.status not in ["active", "draft"]:
            raise HTTPException(status_code=400, detail="Strategy is not active")
        
        # Start execution
        success = await strategy_engine.start_execution(execution_id, strategy, execution.trade_run_id)
        if not success:
            raise HTTPException(status_code=400, detail="Strategy execution is already running")
        
        return {"message": "Strategy execution started successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting strategy execution: {str(e)}")

@app.post("/api/strategy-executions/{execution_id}/stop")
async def stop_strategy_execution_api(
    execution_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Stop executing a strategy"""
    try:
        # Stop execution
        success = await strategy_engine.stop_execution(execution_id)
        if not success:
            raise HTTPException(status_code=404, detail="Strategy execution not found or not running")
        
        return {"message": "Strategy execution stopped successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping strategy execution: {str(e)}")

@app.post("/api/trade-run/attach-strategy")
async def attach_strategy_to_trade_run_api(
    strategy_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Attach a strategy to the current trade run"""
    try:
        # Check if there's an active trade run
        run_database = selected_database_store.get("run_database")
        if not run_database:
            raise HTTPException(status_code=400, detail="No active trade run")
        
        # Get the strategy
        strategy = await get_strategy_by_id(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Check if strategy is active
        if not strategy.is_active or strategy.status not in ["active", "draft"]:
            raise HTTPException(status_code=400, detail="Strategy is not active")
        
        # Create strategy execution
        execution = StrategyExecutionCreate(
            strategy_id=strategy_id,
            trade_run_id=run_database
        )
        
        created_execution = await create_strategy_execution(execution)
        
        # Start the execution
        await strategy_engine.start_execution(created_execution.id, strategy, run_database)
        
        return {
            "message": f"Strategy '{strategy.name}' attached to trade run successfully",
            "execution_id": created_execution.id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error attaching strategy to trade run: {str(e)}")

@app.get("/api/trade-run/attached-strategies")
async def get_attached_strategies_api(current_user: User = Depends(get_current_active_user)):
    """Get strategies attached to the current trade run"""
    try:
        # Check if there's an active trade run
        run_database = selected_database_store.get("run_database")
        if not run_database:
            return {"executions": [], "total_count": 0}
        
        # Get executions for this trade run
        executions = await get_strategy_executions(trade_run_id=run_database)
        
        # Get strategy details for each execution
        result = []
        for execution in executions:
            strategy = await get_strategy_by_id(execution.strategy_id)
            if strategy:
                result.append({
                    "execution": execution,
                    "strategy": strategy
                })
        
        return {
            "executions": result,
            "total_count": len(result)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting attached strategies: {str(e)}")

# Strategy Execution Engine
class StrategyExecutionEngine:
    def __init__(self):
        self.active_executions = {}  # execution_id -> execution_task
        self.execution_data = {}  # execution_id -> execution state
    
    async def start_execution(self, execution_id: str, strategy: Strategy, trade_run_id: str):
        """Start executing a strategy"""
        if execution_id in self.active_executions:
            return False  # Already running
        
        # Create execution task
        task = asyncio.create_task(self._execute_strategy(execution_id, strategy, trade_run_id))
        self.active_executions[execution_id] = task
        self.execution_data[execution_id] = {
            "current_step": 0,
            "step_results": {},
            "positions": [],
            "last_tick_data": None
        }
        
        return True
    
    async def stop_execution(self, execution_id: str):
        """Stop executing a strategy"""
        if execution_id in self.active_executions:
            task = self.active_executions[execution_id]
            task.cancel()
            del self.active_executions[execution_id]
            if execution_id in self.execution_data:
                del self.execution_data[execution_id]
            return True
        return False
    
    async def _execute_strategy(self, execution_id: str, strategy: Strategy, trade_run_id: str):
        """Main strategy execution loop"""
        try:
            # Update execution status to running
            await update_strategy_execution(execution_id, StrategyExecutionUpdate(status="running"))
            
            # Add initial log entry
            await add_execution_log(execution_id, {
                "type": "execution_started",
                "message": f"Strategy execution started for {strategy.name}",
                "strategy_id": strategy.id,
                "trade_run_id": trade_run_id
            })
            
            # Main execution loop
            step_index = 0
            while step_index < len(strategy.steps):
                step = strategy.steps[step_index]
                
                if not step.is_enabled:
                    step_index += 1
                    continue
                
                # Update current step
                await update_strategy_execution(execution_id, StrategyExecutionUpdate(current_step_id=step.step_id))
                
                # Execute step based on type
                if step.step_type == "condition":
                    result = await self._evaluate_condition(step, execution_id)
                    if result:
                        step_index += 1  # Continue to next step
                    else:
                        # Condition failed, skip to next step or end
                        step_index += 1
                        
                elif step.step_type == "action":
                    result = await self._execute_action(step, execution_id)
                    step_index += 1
                    
                elif step.step_type == "loop":
                    # Handle loop logic
                    step_index = await self._handle_loop(step, step_index, strategy.steps, execution_id)
                    
                elif step.step_type == "branch":
                    # Handle branching logic
                    step_index = await self._handle_branch(step, step_index, strategy.steps, execution_id)
                
                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.1)
            
            # Execution completed
            await update_strategy_execution(
                execution_id, 
                StrategyExecutionUpdate(
                    status="completed",
                    completed_at=datetime.utcnow()
                )
            )
            
            await add_execution_log(execution_id, {
                "type": "execution_completed",
                "message": f"Strategy execution completed for {strategy.name}"
            })
            
        except asyncio.CancelledError:
            # Execution was cancelled
            await update_strategy_execution(
                execution_id, 
                StrategyExecutionUpdate(
                    status="stopped",
                    completed_at=datetime.utcnow()
                )
            )
            await add_execution_log(execution_id, {
                "type": "execution_stopped",
                "message": f"Strategy execution stopped for {strategy.name}"
            })
        except Exception as e:
            # Execution failed
            await update_strategy_execution(
                execution_id, 
                StrategyExecutionUpdate(
                    status="error",
                    completed_at=datetime.utcnow()
                )
            )
            await add_execution_log(execution_id, {
                "type": "execution_error",
                "message": f"Strategy execution failed: {str(e)}"
            })
    
    async def _evaluate_condition(self, step: StrategyStep, execution_id: str) -> bool:
        """Evaluate a strategy condition"""
        try:
            condition = step.condition
            if not condition:
                return False
            
            # Get current market data
            current_data = await self._get_current_market_data(condition.symbol)
            if not current_data:
                return False
            
            result = False
            
            if condition.condition_type == "price_above":
                result = current_data.get("price", 0) > condition.value
            elif condition.condition_type == "price_below":
                result = current_data.get("price", 0) < condition.value
            elif condition.condition_type == "ema_above":
                result = current_data.get("ema", 0) > condition.value
            elif condition.condition_type == "ema_below":
                result = current_data.get("ema", 0) < condition.value
            # Add more condition types as needed
            
            # Log condition evaluation
            await add_execution_log(execution_id, {
                "type": "condition_evaluated",
                "step_id": step.step_id,
                "condition_type": condition.condition_type,
                "symbol": condition.symbol,
                "value": condition.value,
                "current_data": current_data,
                "result": result
            })
            
            return result
            
        except Exception as e:
            await add_execution_log(execution_id, {
                "type": "condition_error",
                "step_id": step.step_id,
                "error": str(e)
            })
            return False
    
    async def _execute_action(self, step: StrategyStep, execution_id: str) -> bool:
        """Execute a strategy action"""
        try:
            action = step.action
            if not action:
                return False
            
            # Log action execution
            await add_execution_log(execution_id, {
                "type": "action_executed",
                "step_id": step.step_id,
                "action_type": action.action_type,
                "symbol": action.symbol,
                "quantity": action.quantity,
                "price": action.price
            })
            
            # Execute the action based on type
            if action.action_type == "buy_market":
                # Place buy market order
                await self._place_order("buy", "market", action.symbol, action.quantity, None, execution_id)
            elif action.action_type == "sell_market":
                # Place sell market order
                await self._place_order("sell", "market", action.symbol, action.quantity, None, execution_id)
            elif action.action_type == "buy_limit":
                # Place buy limit order
                await self._place_order("buy", "limit", action.symbol, action.quantity, action.price, execution_id)
            elif action.action_type == "sell_limit":
                # Place sell limit order
                await self._place_order("sell", "limit", action.symbol, action.quantity, action.price, execution_id)
            elif action.action_type == "wait":
                # Wait for specified time
                if action.wait_seconds:
                    await asyncio.sleep(action.wait_seconds)
            # Add more action types as needed
            
            return True
            
        except Exception as e:
            await add_execution_log(execution_id, {
                "type": "action_error",
                "step_id": step.step_id,
                "error": str(e)
            })
            return False
    
    async def _handle_loop(self, step: StrategyStep, current_index: int, steps: list, execution_id: str) -> int:
        """Handle loop logic"""
        # Simple loop implementation - can be enhanced
        if step.loop_count and step.loop_count > 0:
            # For now, just continue to next step
            return current_index + 1
        return current_index + 1
    
    async def _handle_branch(self, step: StrategyStep, current_index: int, steps: list, execution_id: str) -> int:
        """Handle branching logic"""
        # Simple branch implementation - can be enhanced
        if step.next_step_id:
            # Find the target step
            for i, s in enumerate(steps):
                if s.step_id == step.next_step_id:
                    return i
        return current_index + 1
    
    async def _get_current_market_data(self, symbol: str) -> dict:
        """Get current market data for a symbol"""
        try:
            # Get the current run database
            run_database = selected_database_store.get("run_database")
            if not run_database:
                return None
            
            # Get latest tick data from Redis
            ticks = await get_ticks_from_redis(run_database, "indextick", 1)
            if not ticks:
                return None
            
            latest_tick = ticks[0]
            
            # Calculate EMAs if needed
            ema_data = await calculate_index_emas(run_database)
            
            return {
                "price": latest_tick.get("lp", 0),
                "volume": latest_tick.get("volume", 0),
                "ema_short": ema_data.get("short_ema", 0),
                "ema_long": ema_data.get("long_ema", 0),
                "timestamp": latest_tick.get("ft", 0)
            }
            
        except Exception as e:
            print(f"Error getting market data: {e}")
            return None
    
    async def _place_order(self, side: str, order_type: str, symbol: str, quantity: int, price: float, execution_id: str):
        """Place an order through the system"""
        try:
            # Create order through the existing order system
            order_data = {
                "symbol": symbol,
                "quantity": quantity,
                "side": side,
                "order_type": order_type,
                "price": price,
                "user_id": "system"  # System user for strategy orders
            }
            
            # This would integrate with the existing order system
            # For now, just log the order
            await add_execution_log(execution_id, {
                "type": "order_placed",
                "side": side,
                "order_type": order_type,
                "symbol": symbol,
                "quantity": quantity,
                "price": price
            })
            
        except Exception as e:
            await add_execution_log(execution_id, {
                "type": "order_error",
                "error": str(e)
            })

# Global strategy execution engine
strategy_engine = StrategyExecutionEngine()

# ------------------ ML Endpoints ------------------
from fastapi import BackgroundTasks

@app.post("/api/ml/train-index-model", response_model=MLTrainResponse)
async def train_index_model_api(request: MLTrainRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_admin_user)):
    """Train or retrain index trend model."""
    try:
        # Validate database exists
        databases = await db.client.list_database_names()
        if request.database_name not in databases:
            return MLTrainResponse(status="error", message=f"Database {request.database_name} not found")
        from ml.modeling import TrainConfig, train_index_model
        cfg = TrainConfig(
            database_name=request.database_name,
            horizon_minutes=request.horizon_minutes,
            lookback_minutes=request.lookback_minutes,
            test_size=request.test_size
        )
        result = await train_index_model(cfg)
        return MLTrainResponse(**result)
    except Exception as e:
        return MLTrainResponse(status="error", message=str(e))

@app.get("/api/ml/predict-index-trend", response_model=MLPredictResponse)
async def predict_index_trend_api(database_name: str, current_user: User = Depends(get_admin_user)):
    """Predict future direction (up/down) for next horizon minutes based on latest data."""
    try:
        from ml.modeling import predict_index_direction
        result = await predict_index_direction(database_name)
        return MLPredictResponse(**result)
    except Exception as e:
        return MLPredictResponse(status="error", message=str(e))

@app.get("/api/ml/model-status")
async def ml_model_status(database_name: str, current_user: User = Depends(get_admin_user)):
    from ml.modeling import get_model_status
    return get_model_status(database_name)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 