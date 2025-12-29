"""Twitch service layer"""

import logging
from urllib.parse import quote

import httpx
from config import API_URL, CLIENT_ID, CLIENT_SECRET

logger = logging.getLogger(__name__)

if not CLIENT_SECRET:
    raise ValueError("CLIENT_SECRET environment variable must be set")

BROADCASTER_SCOPES = [
    "user:read:email",
    "channel:read:subscriptions",
    "bits:read",
    "channel:read:redemptions",
    "moderator:read:followers",
]


def generate_oauth_url() -> str:
    redirect_uri = f"{API_URL}/api/auth/twitch/callback"
    scope_string = "+".join(s.replace(":", "%3A") for s in BROADCASTER_SCOPES)
    encoded_redirect_uri = quote(redirect_uri, safe="")

    return (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect_uri}"
        f"&response_type=code"
        f"&scope={scope_string}"
        f"&force_verify=true"
    )


async def exchange_code_for_token(code: str) -> tuple[bool, str | None, dict | None]:
    try:
        redirect_uri = f"{API_URL}/api/auth/twitch/callback"

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                }
            )

            if token_response.status_code != 200:
                logger.error(f"Failed to exchange code for token: {token_response.status_code}")
                logger.error(f"Response: {token_response.text}")
                return False, "token_exchange_failed", None

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")

            if not access_token:
                logger.error("No access_token in response")
                return False, "no_access_token", None

            user_response = await client.get(
                "https://api.twitch.tv/helix/users",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": CLIENT_ID
                }
            )

            if user_response.status_code != 200:
                logger.error(f"Failed to get user info: {user_response.status_code}")
                return False, "user_fetch_failed", None

            user_data = user_response.json()
            users = user_data.get("data", [])

            if not users:
                logger.error("No user data in response")
                return False, "no_user_data", None

            user_id = users[0].get("id")

            if not user_id:
                logger.error("No user_id in user data")
                return False, "no_user_id", None

            logger.info(f"Successfully exchanged code for token, user_id: {user_id}")

            return True, None, {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user_id": user_id
            }

    except httpx.TimeoutException:
        logger.error("Timeout while exchanging code for token")
        return False, "timeout", None
    except Exception as e:
        logger.exception(f"Unexpected error exchanging code: {e}")
        return False, "exchange_failed", None


async def save_token_to_database(user_id: str, access_token: str, refresh_token: str | None) -> bool:
    try:
        from services.database import get_database_pool

        pool = await get_database_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO tokens (user_id, token, refresh)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    token = EXCLUDED.token,
                    refresh = EXCLUDED.refresh
                """,
                user_id,
                access_token,
                refresh_token or ""
            )

        logger.info(f"Saved token to database for user_id: {user_id}")
        return True

    except Exception as e:
        logger.exception(f"Error saving token to database: {e}")
        return False


async def get_monitored_channels(user_id: str) -> list[dict]:
    try:
        from services.database import get_database_pool

        pool = await get_database_pool()

        async with pool.acquire() as connection:
            token_row = await connection.fetchrow(
                "SELECT token FROM tokens WHERE user_id = $1",
                user_id
            )

            if not token_row:
                logger.warning(f"No token found for user_id: {user_id}")
                return []

            access_token = token_row["token"]

            channel_rows = await connection.fetch(
                "SELECT DISTINCT channel_id, channel_name FROM channels WHERE enabled = true"
            )

            logger.info(f"Found {len(channel_rows)} enabled channels in database")

            if not channel_rows:
                logger.info("No monitored channels found")
                return []

            channel_ids = [row["channel_id"] for row in channel_rows]

        async with httpx.AsyncClient(timeout=10.0) as client:
            users_response = await client.get(
                "https://api.twitch.tv/helix/users",
                params={"id": channel_ids},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": CLIENT_ID
                }
            )

            if users_response.status_code != 200:
                logger.error(f"Failed to fetch user info: {users_response.status_code}")
                logger.error(f"Response: {users_response.text}")
                return []

            users_data = users_response.json().get("data", [])
            logger.info(f"Twitch API returned {len(users_data)} users")

            channels_info = {}
            for user in users_data:
                channels_info[user["login"]] = {
                    "id": user["id"],
                    "name": user["login"],
                    "display_name": user["display_name"],
                    "avatar": user["profile_image_url"],
                    "is_live": False
                }

            user_ids = [user["id"] for user in users_data]
            if user_ids:
                streams_response = await client.get(
                    "https://api.twitch.tv/helix/streams",
                    params={"user_id": user_ids},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Client-Id": CLIENT_ID
                    }
                )

                if streams_response.status_code == 200:
                    streams_data = streams_response.json().get("data", [])

                    for stream in streams_data:
                        user_id_str = stream["user_id"]
                        for channel in channels_info.values():
                            if channel["id"] == user_id_str:
                                channel["is_live"] = True
                                channel["viewer_count"] = stream["viewer_count"]
                                channel["game_name"] = stream["game_name"]
                                break

        result = [channel for channel in channels_info.values() if channel["id"] != user_id]
        result.sort(key=lambda x: (not x["is_live"], x["display_name"]))

        logger.info(f"Found {len(result)} monitored channels for user {user_id} (excluding self)")
        return result

    except Exception as e:
        logger.exception(f"Error getting monitored channels: {e}")
        return []
