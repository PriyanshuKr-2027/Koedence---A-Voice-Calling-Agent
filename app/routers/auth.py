from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
import httpx
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Auth"])


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None


async def require_authenticated_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """
    Validates JWT token against SUPABASE_JWT_SECRET (or Supabase Auth service),
    verifies signature, exp, and aud, and derives org_id from profiles or token claims.
    Rejects forged, unsigned, expired, or org-less tokens.
    """
    if not authorization:
        if settings.ALLOW_DEV_AUTH:
            if settings.ENVIRONMENT.lower() == "production":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication token required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            dev_org = "00000000-0000-0000-0000-000000000001"
            return {
                "id": "00000000-0000-0000-0000-000000000001",
                "email": "dev@vocall.ai",
                "org_id": dev_org,
                "role": "admin",
            }
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

    import jwt

    decoded: Dict[str, Any] = {}

    if settings.SUPABASE_JWT_SECRET:
        try:
            decoded = jwt.decode(
                token,
                key=settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_signature": True, "verify_exp": True, "verify_aud": False},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.DecodeError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format or signature",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authorization token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        aud = decoded.get("aud")
        if aud and aud != "authenticated":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        from app.services.supabase_client import supabase
        if supabase:
            try:
                user_resp = supabase.auth.get_user(token)
                if not user_resp or not getattr(user_resp, "user", None):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid authorization token",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                u = user_resp.user
                decoded = {
                    "sub": getattr(u, "id", None),
                    "email": getattr(u, "email", "user@vocall.ai"),
                    "app_metadata": getattr(u, "app_metadata", {}),
                    "user_metadata": getattr(u, "user_metadata", {}),
                    "aud": getattr(u, "aud", "authenticated"),
                    "role": getattr(u, "role", "authenticated"),
                }
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Token verification failed: {exc}",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization token: SUPABASE_JWT_SECRET not configured",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user_id = decoded.get("sub") or decoded.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Derive org_id ONLY from verified token claim or profiles table
    org_id = (
        decoded.get("org_id")
        or decoded.get("app_metadata", {}).get("org_id")
        or decoded.get("user_metadata", {}).get("org_id")
    )
    if not org_id:
        from app.services.supabase_client import supabase
        if supabase:
            try:
                p_res = supabase.table("profiles").select("org_id").eq("id", str(user_id)).single().execute()
                if p_res.data and p_res.data.get("org_id"):
                    org_id = p_res.data["org_id"]
            except Exception:
                pass

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to any organization",
        )

    return {
        "id": str(user_id),
        "email": decoded.get("email", "user@vocall.ai"),
        "org_id": str(org_id),
        "role": decoded.get("role", "member"),
    }


get_current_user = require_authenticated_user


@router.post("/login")
async def login(payload: AuthLoginRequest):
    """
    Authenticates user credentials using Supabase Auth REST API.
    """
    supabase_url = settings.NEXT_PUBLIC_SUPABASE_URL
    anon_key = settings.NEXT_PUBLIC_SUPABASE_ANON_KEY or settings.SUPABASE_SERVICE_ROLE_KEY

    if supabase_url and anon_key:
        endpoint = f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
        headers = {
            "apikey": anon_key,
            "Content-Type": "application/json",
        }
        body = {
            "email": payload.email,
            "password": payload.password,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(endpoint, headers=headers, json=body)
                if res.status_code == 200:
                    data = res.json()
                    user_data = data.get("user", {})
                    org_id = (
                        user_data.get("user_metadata", {}).get("org_id")
                        or user_data.get("app_metadata", {}).get("org_id")
                        or "00000000-0000-0000-0000-000000000000"
                    )
                    return {
                        "access_token": data.get("access_token"),
                        "token_type": "bearer",
                        "expires_in": data.get("expires_in"),
                        "refresh_token": data.get("refresh_token"),
                        "user": {
                            "id": user_data.get("id"),
                            "email": user_data.get("email"),
                            "org_id": org_id,
                        },
                    }
                else:
                    error_data = res.json()
                    raise HTTPException(
                        status_code=res.status_code,
                        detail=error_data.get("error_description") or error_data.get("msg") or "Authentication failed",
                    )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Supabase Auth service unreachable: {exc}",
            )

    # Dev/Mock login mode when Supabase credentials are missing
    return {
        "access_token": f"dev_mock_token_{payload.email}",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": payload.email,
            "org_id": "00000000-0000-0000-0000-000000000000",
        },
    }


@router.get("/me")
async def get_current_user_profile(user: Dict[str, Any] = Depends(get_current_user)):
    return {"status": "authenticated", "user": user}
