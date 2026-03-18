import logging

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import create_client

from app.config import settings
from app.core.dependencies import get_current_user
from app.schemas.auth import AuthResponse, RegisterRequest, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def get_supabase():
    """Create Supabase client lazily so a bad key fails at request time, not import."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """Register a new user via Supabase Auth and return the session token."""
    supabase = get_supabase()
    try:
        response = supabase.auth.sign_up(
            {"email": body.email, "password": body.password}
        )

        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed — user not created",
            )

        return AuthResponse(
            access_token=response.session.access_token if response.session else "",
            user_id=response.user.id,
            email=response.user.email or body.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Registration error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=AuthResponse)
async def login(body: RegisterRequest):
    """Log in via Supabase Auth and return the session token."""
    supabase = get_supabase()
    try:
        response = supabase.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )

        if not response.user or not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        return AuthResponse(
            access_token=response.session.access_token,
            user_id=response.user.id,
            email=response.user.email or body.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    return UserResponse(
        user_id=current_user["user_id"],
        email=current_user.get("email"),
    )
