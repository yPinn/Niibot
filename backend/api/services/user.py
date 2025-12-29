"""User service layer"""

import logging

import httpx
from config import CLIENT_ID, CLIENT_SECRET

logger = logging.getLogger(__name__)

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("CLIENT_ID and CLIENT_SECRET must be set")


async def get_user_info(user_id: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            token_response = await client.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "client_credentials"
                }
            )

            if token_response.status_code != 200:
                logger.error(f"Failed to get app access token: {token_response.status_code}")
                return None

            app_token = token_response.json().get("access_token")

            response = await client.get(
                f"https://api.twitch.tv/helix/users?id={user_id}",
                headers={
                    "Client-ID": CLIENT_ID,
                    "Authorization": f"Bearer {app_token}"
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch user from Twitch API: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None

            data = response.json()
            users = data.get("data", [])

            if not users:
                logger.warning(f"No user found for user_id: {user_id}")
                return None

            user = users[0]

            return {
                "id": user.get("id"),
                "name": user.get("login"),
                "display_name": user.get("display_name"),
                "avatar": user.get("profile_image_url")
            }

    except Exception as e:
        logger.exception(f"Error fetching user info: {e}")
        return None
