"""
Authentication router for Sapient API
"""

from fastapi import APIRouter, HTTPException, status, Depends

from backend.schemas.auth import UserCreate, UserLogin, TokenResponse, UserResponse
from core.database import UserService
from backend.auth_utils import create_access_token, get_current_user

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    """Register a new user account."""
    result = UserService.create_user(
        email=user_data.email,
        password=user_data.password,
        display_name=user_data.display_name
    )
    
    if not result['success']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result['error']
        )
    
    user = result['user']
    access_token = create_access_token(data={"sub": str(user["id"])})
    
    return TokenResponse(
        access_token=access_token,
        user=UserResponse(**user)
    )


@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    """Authenticate a user and return a token."""
    result = UserService.authenticate(
        email=user_data.email,
        password=user_data.password
    )
    
    if not result['success']:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result['error']
        )
    
    user = result['user']
    access_token = create_access_token(data={"sub": str(user["id"])})
    
    return TokenResponse(
        access_token=access_token,
        user=UserResponse(**user)
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(**current_user)
