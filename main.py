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
from pathlib import Path
from typing import List, Dict

from database import connect_to_mongo, close_mongo_connection, db
from models import UserCreate, UserUpdate, LoginRequest, Token, User, UserInDB, ProfileUpdate, PasswordChange, TickData, TickDataResponse, StartRunRequest, StartRunResponse
from auth import create_access_token, get_current_active_user, get_super_admin_user, get_admin_user, get_password_hash, verify_password
from crud import create_user, get_users, update_user, delete_user, authenticate_user, create_super_admin
from config import settings

# Store the currently selected database
selected_database_store = {}

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
            
            print(f"Starting tick stream from database {database_name} with {interval_seconds}s interval")
            
            # First, send ALL historical ticks one by one with interval
            print("Sending all historical ticks one by one...")
            cursor = indextick_collection.find({}).sort("ft", 1)  # Oldest first
            
            initial_count = 0
            async for doc in cursor:
                # Check if stream was stopped
                if not self.is_streaming or (self.tick_stream_task and self.tick_stream_task.done()):
                    print("Tick stream was stopped during historical data send")
                    return
                
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
                
                # Send each tick immediately
                await self.broadcast(tick_data.json())
                initial_count += 1
                
                # Apply interval between each tick for better control
                await asyncio.sleep(interval_seconds)
                
                # Progress update every 100 ticks
                if initial_count % 100 == 0:
                    print(f"Sent {initial_count} historical ticks...")
            
            print(f"Sent {initial_count} historical ticks")
            
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
                    # Query for new ticks since last_ft
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
                        # Update last_ft
                        last_ft = doc.get("ft", last_ft)
                        
                        # Convert to TickData model
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
                        
                        # Send to all connected clients
                        await self.broadcast(tick_data.json())
                        
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

# Create connection manager instance
manager = ConnectionManager()

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
        
        return {"message": f"Backup created successfully", "backup_path": str(pinaka_dir)}
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

@app.post("/api/start-run", response_model=StartRunResponse)
async def start_run(request: StartRunRequest, current_user: User = Depends(get_admin_user)):
    """Start a trading run with the specified database"""
    try:
        # Validate that the database exists
        databases = await db.client.list_database_names()
        if request.database_name not in databases:
            raise HTTPException(status_code=404, detail=f"Database '{request.database_name}' not found")
        
        # Store the selected database for the run
        selected_database_store["run_database"] = request.database_name
        selected_database_store["run_interval"] = request.interval_seconds
        
        # Start WebSocket tick stream with the provided interval
        await manager.start_tick_stream(request.database_name, request.interval_seconds)
        
        return StartRunResponse(
            message=f"Trading run started with database '{request.database_name}'",
            database_name=request.database_name,
            status="started",
            interval_seconds=request.interval_seconds
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 