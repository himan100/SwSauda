from fastapi import FastAPI, Request, HTTPException, Depends, status, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
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

from database import connect_to_mongo, close_mongo_connection, db, get_database
from models import (UserCreate, UserUpdate, LoginRequest, Token, User, UserInDB, ProfileUpdate, PasswordChange, 
                   TickData, OptionTickData, TickDataResponse, StartRunRequest, StartRunResponse,
                   OrderCreate, OrderUpdate, Order, OrderStatus, PositionSummary, PositionResponse)
from auth import create_access_token, get_current_active_user, get_super_admin_user, get_admin_user, get_password_hash, verify_password
from crud import (create_user, get_users, update_user, delete_user, authenticate_user, create_super_admin,
                 create_order, get_order_by_id, get_orders, update_order, delete_order)
from config import settings

# Store the currently selected database
selected_database_store = {}

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
                
                try:
                    # Query for new index ticks since last_ft
                    cursor = indextick_collection.find(
                        {"ft": {"$gt": last_ft}}
                    ).sort("ft", 1)
                    
                    new_ticks_found = False
                    async for doc in cursor:
                        # Check if stream was stopped
                        if not self.is_streaming or (self.tick_stream_task and self.tick_stream_task.done()):
                            print("Tick stream was stopped during new tick processing")
                            return
                        
                        new_ticks_found = True
                        current_ft = doc.get("ft", 0)
                        last_ft = current_ft
                        
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
                                option_count += 1
                            
                            if option_count > 0:
                                print(f"New IndexTick {current_ft}: sent {option_count} matching OptionTicks")
                        
                        # Apply interval between each new tick
                        await asyncio.sleep(interval_seconds)
                    
                    if not new_ticks_found:
                        # No new ticks, wait for the configured interval
                        await asyncio.sleep(interval_seconds)
                    
                except Exception as e:
                    print(f"Error in tick stream: {e}")
                    await asyncio.sleep(5)  # Wait longer on error
                    
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

# Templates
templates = Jinja2Templates(directory="templates")

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    await create_super_admin()

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

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

@app.get("/trade-run", response_class=HTMLResponse)
async def trade_run_page(request: Request):
    return templates.TemplateResponse("trade_run.html", {"request": request})

@app.get("/positions", response_class=HTMLResponse)
async def positions_page(request: Request):
    return templates.TemplateResponse("positions.html", {"request": request})

@app.post("/api/trade-run")
async def trade_run_api(database_name: str = Form(...), current_user: User = Depends(get_admin_user)):
    selected_database_store["selected"] = database_name
    return {"message": f"Selected database set to {database_name}"}

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

# Positions API endpoints
@app.get("/api/positions", response_model=PositionResponse)
async def get_positions_api(current_user: User = Depends(get_current_active_user)):
    """Get positions for the current user"""
    try:
        db_instance = await get_database()
        
        # First ensure the positions view exists
        await execute_position_views_script()
        
        # Query the positions view
        positions_cursor = db_instance.v_positions.find({"user_id": current_user.id})
        positions = []
        
        async for position in positions_cursor:
            # Convert MongoDB document to PositionSummary
            position_data = {
                "symbol": position.get("symbol", ""),
                "total_buy_quantity": position.get("total_buy_quantity", 0),
                "total_sell_quantity": position.get("total_sell_quantity", 0),
                "net_position": position.get("net_position", 0),
                "total_buy_value": position.get("total_buy_value", 0.0),
                "total_sell_value": position.get("total_sell_value", 0.0),
                "average_buy_price": position.get("average_buy_price"),
                "average_sell_price": position.get("average_sell_price"),
                "open_buy_orders": position.get("open_buy_orders", 0),
                "open_sell_orders": position.get("open_sell_orders", 0),
                "open_buy_quantity": position.get("open_buy_quantity", 0),
                "open_sell_quantity": position.get("open_sell_quantity", 0),
                "open_buy_avg_price": position.get("open_buy_avg_price"),
                "open_sell_avg_price": position.get("open_sell_avg_price"),
                "realized_pnl": position.get("realized_pnl", 0.0),
                "unrealized_pnl": 0.0,  # TODO: Calculate based on current market price
                "current_price": None  # TODO: Get from market data
            }
            positions.append(PositionSummary(**position_data))
        
        return PositionResponse(positions=positions, total_positions=len(positions))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching positions: {str(e)}")

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
        # Get all users' positions (you might want to filter by user in a real implementation)
        db_instance = await get_database()
        positions_cursor = db_instance.v_positions.find({})
        positions = []
        
        async for position in positions_cursor:
            position_data = {
                "symbol": position.get("symbol", ""),
                "user_id": position.get("user_id", ""),
                "total_buy_quantity": position.get("total_buy_quantity", 0),
                "total_sell_quantity": position.get("total_sell_quantity", 0),
                "net_position": position.get("net_position", 0),
                "total_buy_value": position.get("total_buy_value", 0.0),
                "total_sell_value": position.get("total_sell_value", 0.0),
                "average_buy_price": position.get("average_buy_price"),
                "average_sell_price": position.get("average_sell_price"),
                "open_buy_orders": position.get("open_buy_orders", 0),
                "open_sell_orders": position.get("open_sell_orders", 0),
                "open_buy_quantity": position.get("open_buy_quantity", 0),
                "open_sell_quantity": position.get("open_sell_quantity", 0),
                "open_buy_avg_price": position.get("open_buy_avg_price"),
                "open_sell_avg_price": position.get("open_sell_avg_price"),
                "realized_pnl": position.get("realized_pnl", 0.0),
                "unrealized_pnl": 0.0,
                "current_price": None
            }
            positions.append(position_data)
        
        # Get recent orders
        orders = await get_orders(limit=50)
        orders_data = [
            {
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
            }
            for order in orders
        ]
        
        # Broadcast to all connected clients
        message = json.dumps({
            "type": "positions_update",
            "positions": positions
        })
        await positions_manager.broadcast(message)
        
        orders_message = json.dumps({
            "type": "orders_update", 
            "orders": orders_data
        })
        await positions_manager.broadcast(orders_message)
        
    except Exception as e:
        print(f"Error broadcasting positions update: {e}")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 