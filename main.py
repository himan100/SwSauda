from fastapi import FastAPI, Request, HTTPException, Depends, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
from datetime import timedelta, datetime
import os
import subprocess
import json
from pathlib import Path

from database import connect_to_mongo, close_mongo_connection, db
from models import UserCreate, UserUpdate, LoginRequest, Token, User, UserInDB, ProfileUpdate, PasswordChange
from auth import create_access_token, get_current_active_user, get_super_admin_user, get_admin_user, get_password_hash, verify_password
from crud import create_user, get_users, update_user, delete_user, authenticate_user, create_super_admin
from config import settings

# Store the currently selected database
selected_database_store = {}

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

@app.get("/select-database", response_class=HTMLResponse)
async def select_database_page(request: Request):
    return templates.TemplateResponse("select_database.html", {"request": request})

@app.post("/api/select-database")
async def select_database_api(database_name: str = Form(...), current_user: User = Depends(get_admin_user)):
    selected_database_store["selected"] = database_name
    return {"message": f"Selected database set to {database_name}"}

@app.get("/api/selected-database")
async def get_selected_database(current_user: User = Depends(get_admin_user)):
    return {"selected_database": selected_database_store.get("selected", "")}

@app.post("/api/unset-selected-database")
async def unset_selected_database(current_user: User = Depends(get_admin_user)):
    selected_database_store["selected"] = ""
    return {"message": "Selected database has been unset."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 