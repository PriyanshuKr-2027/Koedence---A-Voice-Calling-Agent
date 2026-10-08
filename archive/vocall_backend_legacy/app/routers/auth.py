from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Auth"])


class AuthLoginRequest(BaseModel):
    email: str
    password: str


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Dependency that returns current authenticated user and org_id from JWT header.
    """
    if not authorization:
        # Default mock user / fallback for local development & testing
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "dev@vocall.ai",
            "org_id": "00000000-0000-0000-0000-000000000000",
            "role": "admin",
        }

    token = authorization.replace("Bearer ", "").strip()
    try:
        import jwt

        decoded = jwt.decode(token, options={"verify_signature": False})
        org_id = (
            decoded.get("org_id")
            or decoded.get("app_metadata", {}).get("org_id")
            or decoded.get("user_metadata", {}).get("org_id")
            or "00000000-0000-0000-0000-000000000000"
        )
        return {
            "id": decoded.get("sub", "00000000-0000-0000-0000-000000000001"),
            "email": decoded.get("email", "user@vocall.ai"),
            "org_id": org_id,
            "role": decoded.get("role", "member"),
        }
    except Exception:
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "user@vocall.ai",
            "org_id": "00000000-0000-0000-0000-000000000000",
            "role": "admin",
        }


async def require_authenticated_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Dependency requiring a valid authorization bearer token.
    Never falls back to an unauthenticated dev user, regardless of environment.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        import jwt

        decoded = jwt.decode(token, options={"verify_signature": False})
        user_id = decoded.get("sub") or decoded.get("id")
        if not user_id:
            raise ValueError("Token missing user subject")

        org_id = (
            decoded.get("org_id")
            or decoded.get("app_metadata", {}).get("org_id")
            or decoded.get("user_metadata", {}).get("org_id")
            or "00000000-0000-0000-0000-000000000000"
        )

        return {
            "id": user_id,
            "email": decoded.get("email", "user@vocall.ai"),
            "org_id": org_id,
            "role": decoded.get("role", "member"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authorization token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/login")
async def login(payload: AuthLoginRequest):
    return {
        "message": "Use Supabase Auth client for authentication",
        "email": payload.email,
    }


@router.get("/me")
async def get_current_user_profile(user: Dict[str, Any] = Depends(get_current_user)):
    return {"status": "authenticated", "user": user}
