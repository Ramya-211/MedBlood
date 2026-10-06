"""Admin routes. ADMIN role only. (Dashboard/alerts endpoints are added in later phases.)"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import require_roles
from app.schemas.auth import Role, UserCreate, UserList, UserPublic, UserUpdate
from app.services import admin_service, user_service
from fastapi import HTTPException

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = require_roles(Role.ADMIN)


@router.get("/dashboard")
def dashboard(_admin: dict = Depends(admin_only)):
    return admin_service.dashboard_overview()


def _wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except user_service.UserServiceError as e:
        raise HTTPException(e.status_code, str(e))


@router.get("/users", response_model=UserList)
def list_users(role: Optional[Role] = None, search: Optional[str] = Query(None, max_length=64),
               is_active: Optional[bool] = None, limit: int = Query(25, ge=1, le=100),
               offset: int = Query(0, ge=0), _admin: dict = Depends(admin_only)):
    """Filter by role=PHARMACIST or role=BLOOD_STAFF for pharmacist/blood-staff management views."""
    return user_service.list_users(role.value if role else None, search, is_active, limit, offset)


@router.post("/users", response_model=UserPublic, status_code=201)
def create_user(body: UserCreate, _admin: dict = Depends(admin_only)):
    return _wrap(user_service.create_user, body.username, body.password, body.full_name, body.role.value)


@router.patch("/users/{user_id}", response_model=UserPublic)
def update_user(user_id: int, body: UserUpdate, admin: dict = Depends(admin_only)):
    return _wrap(
    user_service.update_user,
    user_id,
    admin["id"],
    body.username,
    body.full_name,
    body.role.value if body.role else None,
    body.is_active,
    body.new_password,
)
