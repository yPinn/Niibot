"""Authentication API routes"""

import logging
import os

from config import API_URL, CLIENT_ID, FRONTEND_URL
from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import RedirectResponse
from services import auth as auth_service
from services import twitch as twitch_service
from services import user as user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.get("/twitch/oauth")
async def get_twitch_oauth_url():
    if not CLIENT_ID:
        raise HTTPException(status_code=500, detail="CLIENT_ID not configured")

    oauth_url = twitch_service.generate_oauth_url()
    return {
        "oauth_url": oauth_url,
        "redirect_uri": f"{API_URL}/api/auth/twitch/callback"
    }


@router.get("/twitch/callback")
async def twitch_oauth_callback(code: str | None = None, error: str | None = None, scope: str | None = None):
    if error:
        logger.error(f"OAuth error from Twitch: {error}")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error={error}")

    if not code:
        logger.error("No OAuth code received from Twitch")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=no_code")

    success, error_msg, token_data = await twitch_service.exchange_code_for_token(code)

    if not success or not token_data:
        logger.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error={error_msg}")

    user_id = token_data["user_id"]
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")

    save_success = await twitch_service.save_token_to_database(user_id, access_token, refresh_token)

    if not save_success:
        logger.error("Failed to save token to database")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=save_token_failed")

    token = auth_service.create_access_token(user_id)

    response = RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
    is_production = os.getenv("ENV", "development") == "production"
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        secure=is_production,
        samesite="strict" if is_production else "lax",
        max_age=30*24*60*60
    )

    logger.info(f"User {user_id} logged in successfully")
    return response


@router.get("/user")
async def get_current_user(auth_token: str | None = Cookie(None)):
    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_info = await user_service.get_user_info(user_id)

    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return user_info


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(
        key="auth_token",
        path="/",
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return {"message": "Logged out successfully"}
