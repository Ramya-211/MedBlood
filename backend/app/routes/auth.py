"""Authentication routes: /api/auth/login, /logout, /me"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user, get_token
from app.schemas.auth import LoginRequest, LoginResponse, UserPublic
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    try:
        return auth_service.login(body.username, body.password)
    except auth_service.AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e), headers={"WWW-Authenticate": "Bearer"})


@router.post("/logout")
def logout(token: str = Depends(get_token), _user: dict = Depends(get_current_user)):
    auth_service.logout(token)
    return {"message": "Logged out."}


@router.get("/me", response_model=UserPublic)
def me(user: dict = Depends(get_current_user)):
    return user
