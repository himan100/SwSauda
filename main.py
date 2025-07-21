from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
from datetime import timedelta
import os

from database import connect_to_mongo, close_mongo_connection
from models import UserCreate, UserUpdate, LoginRequest, Token, User, UserInDB, ProfileUpdate, PasswordChange
from auth import create_access_token, get_current_active_user, get_super_admin_user, get_admin_user, get_password_hash, verify_password
from crud import create_user, get_users, update_user, delete_user, authenticate_user, create_super_admin
from config import settings

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 