"""Manage Twitch EventSub Conduits"""
import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")


async def get_app_token():
    """Get app access token from Twitch"""
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as resp:
            data = await resp.json()
            return data.get("access_token")


async def list_conduits():
    """List all existing conduits"""
    token = await get_app_token()

    url = "https://api.twitch.tv/helix/eventsub/conduits"
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            conduits = data.get("data", [])

            print(f"\n=== Found {len(conduits)} Conduit(s) ===\n")
            for i, conduit in enumerate(conduits, 1):
                print(f"{i}. Conduit ID: {conduit['id']}")
                print(f"   Shard Count: {conduit['shard_count']}")
                print()

            return conduits


async def delete_conduit(conduit_id: str):
    """Delete a specific conduit"""
    token = await get_app_token()

    url = f"https://api.twitch.tv/helix/eventsub/conduits?id={conduit_id}"
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=headers) as resp:
            if resp.status == 204:
                print(f"✓ Deleted conduit: {conduit_id}")
            else:
                error = await resp.text()
                print(f"✗ Failed to delete conduit: {error}")


async def delete_all_conduits():
    """Delete all conduits"""
    conduits = await list_conduits()

    if not conduits:
        print("No conduits to delete.")
        return

    confirm = input(f"\nAre you sure you want to delete ALL {len(conduits)} conduit(s)? (yes/no): ")
    if confirm.lower() != "yes":
        print("Cancelled.")
        return

    for conduit in conduits:
        await delete_conduit(conduit['id'])

    print(f"\n✓ Deleted all {len(conduits)} conduit(s)")


async def main():
    print("=== Twitch Conduit Manager ===\n")
    print("1. List all conduits")
    print("2. Delete all conduits")
    print("3. Exit")

    choice = input("\nEnter your choice (1-3): ")

    if choice == "1":
        await list_conduits()
    elif choice == "2":
        await delete_all_conduits()
    elif choice == "3":
        print("Exiting...")
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())
