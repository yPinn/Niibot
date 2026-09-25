"""Generate fake session + viewer data for development.

    npm run nb -- db seed [channel_id] [n_sessions]        # n_sessions default 15
    uv run --directory backend python -m scripts.db.seed [channel_id] [n_sessions]

channel_id defaults to the owner channel. ~10 of every 15 accounts use real
Twitch logins so chatter/event data looks realistic.

Tables written:
  stream_sessions, chatter_stats, stream_events,
  command_stats, viewer_channel_status, viewer_attendance_streaks
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts._lib import (  # noqa: E402
    ensure_backend_on_path,
    load_env,
    require_dev_database,
    utf8_stdio,
)

ensure_backend_on_path()
utf8_stdio()

import asyncpg  # noqa: E402
from api.core.config import get_settings  # noqa: E402

# ── Account pool ───────────────────────────────────────────────────────────────
# Each entry drives realistic chatter_stats + event generation.
#
# Fields
# -------
# attend     : probability of attending any given session  (0–1)
# msg_lo/hi  : message count range per session
# watch_ratio: fraction of session duration watched        (0–1)
# is_mod/vip : channel role flags  — mutually exclusive on Twitch
# sub_tier   : "1000"|"2000"|"3000"|None
# bits_chance: probability of cheering in an attended session (0–1)
# bits_lo/hi : cheer amount range (bits)

REAL_ACCOUNTS: list[dict[str, Any]] = [
    # ── High chatter · tier-2 sub · full attendance ─────────────────────────
    dict(
        id="36128773",
        username="ola0323",
        display="歐拉今天不是很想練習",
        attend=0.90,
        msg_lo=180,
        msg_hi=330,
        watch_ratio=0.92,
        is_mod=False,
        is_vip=False,
        sub_tier="2000",
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── Medium chatter · tier-1 sub · occasional cheer ──────────────────────
    dict(
        id="117691767",
        username="rexyz2z",
        display="rexyz2z",
        attend=0.65,
        msg_lo=100,
        msg_hi=220,
        watch_ratio=0.80,
        is_mod=False,
        is_vip=False,
        sub_tier="1000",
        bits_chance=0.35,
        bits_lo=100,
        bits_hi=300,
    ),
    # ── Casual viewer · no sub ──────────────────────────────────────────────
    dict(
        id="65359374",
        username="luming1228",
        display="嚕嚕閔",
        attend=0.55,
        msg_lo=45,
        msg_hi=100,
        watch_ratio=0.60,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── Recent / new account · late joiner pattern ──────────────────────────
    dict(
        id="1075248331",
        username="capoo_xiang",
        display="_咖波波_",
        attend=0.40,
        msg_lo=15,
        msg_hi=50,
        watch_ratio=0.45,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── Frequent cheerer · occasional chatter · partner streamer ────────────
    dict(
        id="109156102",
        username="san_mou",
        display="三毛毛毛",
        attend=0.50,
        msg_lo=70,
        msg_hi=200,
        watch_ratio=0.75,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.60,
        bits_lo=300,
        bits_hi=2000,
    ),
    # ── 2011 old account · ultra lurker · rare appearance ───────────────────
    dict(
        id="21018499",
        username="iceice12",
        display="古月謠",
        attend=0.20,
        msg_lo=5,
        msg_hi=20,
        watch_ratio=0.85,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── Regular viewer · moderate activity ──────────────────────────────────
    dict(
        id="35760596",
        username="m950101",
        display="M950101",
        attend=0.60,
        msg_lo=60,
        msg_hi=120,
        watch_ratio=0.70,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── High chatter · active recent viewer ─────────────────────────────────
    dict(
        id="193691668",
        username="after_moon",
        display="午後的月亮",
        attend=0.70,
        msg_lo=150,
        msg_hi=260,
        watch_ratio=0.90,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── Channel MOD · NOT VIP ────────────────────────────────────────────────
    dict(
        id="797358387",
        username="hsuyi1222",
        display="想睡覺_",
        attend=0.72,
        msg_lo=130,
        msg_hi=230,
        watch_ratio=0.93,
        is_mod=True,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── VIP · gift sub donor · NOT MOD ──────────────────────────────────────
    dict(
        id="794077634",
        username="kariouo",
        display="kariouo",
        attend=0.55,
        msg_lo=100,
        msg_hi=200,
        watch_ratio=0.85,
        is_mod=False,
        is_vip=True,
        sub_tier=None,
        bits_chance=0.25,
        bits_lo=1000,
        bits_hi=5000,
    ),
]

FAKE_ACCOUNTS: list[dict[str, Any]] = [
    # ── Max-message presence (scatter-plot top-left) ─────────────────────────
    dict(
        id="77777771",
        username="power_chatter",
        display="超級聊天王",
        attend=0.95,
        msg_lo=300,
        msg_hi=440,
        watch_ratio=0.95,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.30,
        bits_lo=200,
        bits_hi=800,
    ),
    # ── Low message · high watch · big cheer (scatter-plot bottom-right) ─────
    dict(
        id="77777772",
        username="bigbits_fan",
        display="小奇點大戶",
        attend=0.40,
        msg_lo=20,
        msg_hi=50,
        watch_ratio=0.98,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.80,
        bits_lo=10000,
        bits_hi=50000,
    ),
    # ── Gift sub whale · tier-3 self-sub ─────────────────────────────────────
    dict(
        id="77777773",
        username="gift_whale",
        display="贈禮鯨魚",
        attend=0.45,
        msg_lo=40,
        msg_hi=90,
        watch_ratio=0.80,
        is_mod=False,
        is_vip=False,
        sub_tier="3000",
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── Near-zero messages · always present (extreme lurker) ─────────────────
    dict(
        id="77777774",
        username="lurk_master",
        display="靜默守望者",
        attend=0.70,
        msg_lo=3,
        msg_hi=12,
        watch_ratio=0.99,
        is_mod=False,
        is_vip=False,
        sub_tier=None,
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
    # ── Loyal tier-1 subscriber · stable attendance ───────────────────────────
    dict(
        id="77777775",
        username="sub_loyal",
        display="忠實訂閱者",
        attend=0.75,
        msg_lo=70,
        msg_hi=110,
        watch_ratio=0.88,
        is_mod=False,
        is_vip=False,
        sub_tier="1000",
        bits_chance=0.00,
        bits_lo=0,
        bits_hi=0,
    ),
]

# 10 real + 5 fake = 15 total  →  66.7 % real
ALL_ACCOUNTS = REAL_ACCOUNTS + FAKE_ACCOUNTS

# gift-sub donors (used to emit gift-sub events)
_GIFT_DONORS = {"77777773", "794077634"}

# ── Content pools ──────────────────────────────────────────────────────────────
GAMES = [
    {"id": "509658", "name": "Just Chatting"},
    {"id": "21779", "name": "League of Legends"},
    {"id": "516575", "name": "VALORANT"},
    {"id": "27471", "name": "Minecraft"},
    {"id": "511224", "name": "Apex Legends"},
    {"id": "32982", "name": "Grand Theft Auto V"},
    {"id": "29595", "name": "Dota 2"},
    {"id": "488552", "name": "Overwatch 2"},
]

TITLES = [
    "Chill 放鬆日",
    "練習賽直播",
    "晚間遊戲",
    "Late Night Gaming",
    "週末下午場",
    "新遊戲初見",
    "週年慶特別直播",
    "純聊天場",
    "排位衝分！",
    "觀眾互動場",
    "Road to Diamond",
    "周末連線",
]

COMMANDS = ["!lurk", "!discord", "!clip", "!今日", "!game", "!title", "!uptime"]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _rand_offset(min_s: int, max_s: int) -> timedelta:
    return timedelta(seconds=random.randint(min_s, max_s))


# ── Core seeder ────────────────────────────────────────────────────────────────


async def seed_test_data(channel_id: str | None = None, n_sessions: int = 15) -> None:
    load_env("dev")
    settings = get_settings()
    require_dev_database(settings.database_url)
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        if not channel_id:
            # Prefer owner channel (llazypilot) so Insights shows data for the logged-in user.
            owner_id = settings.owner_id
            if owner_id:
                row = await conn.fetchrow(
                    "SELECT channel_id FROM channels WHERE channel_id = $1", owner_id
                )
                if row:
                    channel_id = row["channel_id"]
            if not channel_id:
                row = await conn.fetchrow(
                    "SELECT channel_id FROM channels WHERE enabled = true ORDER BY created_at LIMIT 1"
                )
                if not row:
                    print("No channels found in database.")
                    return
                channel_id = row["channel_id"]

        ch_row = await conn.fetchrow(
            "SELECT channel_name FROM channels WHERE channel_id = $1", channel_id
        )
        ch_name = ch_row["channel_name"] if ch_row else channel_id
        print(f"Seeding channel: {ch_name} ({channel_id})")
        print(
            f"Accounts: {len(REAL_ACCOUNTS)} real + {len(FAKE_ACCOUNTS)} fake = {len(ALL_ACCOUNTS)} total\n"
        )

        now = datetime.now(UTC)
        session_metas: list[dict[str, Any]] = []

        # ── 1. Stream sessions ─────────────────────────────────────────────────
        print("── Sessions ──────────────────────────────────────────────────────")
        for _ in range(n_sessions):
            days_ago = random.randint(1, 60)
            hour = random.choices(
                range(24),
                weights=[
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                    11,
                    12,
                    10,
                    8,
                    6,
                    5,
                    4,
                    3,
                    2,
                ],
                k=1,
            )[0]
            started_at = now - timedelta(days=days_ago, hours=hour, minutes=random.randint(0, 59))
            duration_h = round(random.uniform(1.5, 5.5), 2)
            ended_at = started_at + timedelta(hours=duration_h)
            game = random.choice(GAMES)

            row = await conn.fetchrow(
                """
                INSERT INTO stream_sessions
                    (channel_id, started_at, ended_at, title, game_id, game_name,
                     attendance_snapshot_count)
                VALUES ($1, $2, $3, $4, $5, $6, 1)
                RETURNING id
                """,
                channel_id,
                started_at,
                ended_at,
                random.choice(TITLES),
                game["id"],
                game["name"],
            )
            sid: int = row["id"]
            dur_s = int(duration_h * 3600)
            session_metas.append(
                {
                    "id": sid,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "dur_s": dur_s,
                }
            )
            print(f"  {sid}: {game['name']} — {duration_h:.1f}h  ({days_ago}d ago)")

        # ── 2. Viewer data per session ─────────────────────────────────────────
        print("\n── Chatter stats + events ────────────────────────────────────────")

        # Track which session IDs each user appeared in (for streak computation)
        user_sessions: dict[str, list[int]] = {}

        for meta in session_metas:
            sid = meta["id"]
            start: datetime = meta["started_at"]
            dur_s = meta["dur_s"]

            # Select attendees stochastically by attendance probability
            attendees = [acc for acc in ALL_ACCOUNTS if random.random() < acc["attend"]]
            if not attendees:
                attendees = [random.choice(ALL_ACCOUNTS)]

            # ── chatter_stats ──────────────────────────────────────────────────
            for acc in attendees:
                msgs = random.randint(acc["msg_lo"], acc["msg_hi"])
                watch_s = min(
                    int(dur_s * acc["watch_ratio"] * random.uniform(0.85, 1.00)),
                    dur_s,
                )
                last_msg = start + _rand_offset(int(dur_s * 0.50), int(dur_s * 0.95))

                await conn.execute(
                    """
                    INSERT INTO chatter_stats
                        (session_id, channel_id, user_id, username, display_name,
                         message_count, last_message_at, watch_seconds)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (session_id, user_id) DO UPDATE SET
                        message_count   = EXCLUDED.message_count,
                        watch_seconds   = EXCLUDED.watch_seconds,
                        last_message_at = EXCLUDED.last_message_at
                    """,
                    sid,
                    channel_id,
                    acc["id"],
                    acc["username"],
                    acc["display"],
                    msgs,
                    last_msg,
                    watch_s,
                )
                user_sessions.setdefault(acc["id"], []).append(sid)

            # ── stream_events: cheers ──────────────────────────────────────────
            for acc in attendees:
                if acc["bits_chance"] > 0 and random.random() < acc["bits_chance"]:
                    bits = random.randint(acc["bits_lo"], acc["bits_hi"])
                    cheer_at = start + _rand_offset(int(dur_s * 0.15), int(dur_s * 0.85))
                    await conn.execute(
                        """
                        INSERT INTO stream_events
                            (session_id, channel_id, event_type,
                             user_id, username, display_name, metadata, occurred_at)
                        VALUES ($1, $2, 'cheer', $3, $4, $5, $6::jsonb, $7)
                        """,
                        sid,
                        channel_id,
                        acc["id"],
                        acc["username"],
                        acc["display"],
                        f'{{"bits":{bits}}}',
                        cheer_at,
                    )

            # ── stream_events: follows (0–3 per session) ──────────────────────
            follow_pool = [a for a in attendees if random.random() < 0.18]
            for acc in follow_pool[: random.randint(0, 3)]:
                follow_at = start + _rand_offset(60, int(dur_s * 0.30))
                await conn.execute(
                    """
                    INSERT INTO stream_events
                        (session_id, channel_id, event_type,
                         user_id, username, display_name, metadata, occurred_at)
                    VALUES ($1, $2, 'follow', $3, $4, $5, NULL, $6)
                    """,
                    sid,
                    channel_id,
                    acc["id"],
                    acc["username"],
                    acc["display"],
                    follow_at,
                )

            # ── stream_events: self-subs (tier-1/2/3) ─────────────────────────
            sub_pool = [a for a in attendees if a["sub_tier"] and random.random() < 0.35]
            for acc in sub_pool[: random.randint(0, 2)]:
                sub_at = start + _rand_offset(int(dur_s * 0.08), int(dur_s * 0.50))
                await conn.execute(
                    """
                    INSERT INTO stream_events
                        (session_id, channel_id, event_type,
                         user_id, username, display_name, metadata, occurred_at)
                    VALUES ($1, $2, 'subscribe', $3, $4, $5, $6::jsonb, $7)
                    """,
                    sid,
                    channel_id,
                    acc["id"],
                    acc["username"],
                    acc["display"],
                    f'{{"tier":"{acc["sub_tier"]}","is_gift":false}}',
                    sub_at,
                )

            # ── stream_events: gift subs (whale + kariouo) ────────────────────
            for acc in attendees:
                if acc["id"] in _GIFT_DONORS and random.random() < 0.45:
                    gift_count = random.randint(3, 15)
                    gift_at = start + _rand_offset(int(dur_s * 0.25), int(dur_s * 0.70))
                    await conn.execute(
                        """
                        INSERT INTO stream_events
                            (session_id, channel_id, event_type,
                             user_id, username, display_name, metadata, occurred_at)
                        VALUES ($1, $2, 'subscribe', $3, $4, $5, $6::jsonb, $7)
                        """,
                        sid,
                        channel_id,
                        acc["id"],
                        acc["username"],
                        acc["display"],
                        f'{{"tier":"1000","is_gift":true,"gift_count":{gift_count}}}',
                        gift_at,
                    )

            # ── command_stats (2–5 commands per session) ───────────────────────
            for cmd in random.sample(COMMANDS, k=random.randint(2, 5)):
                count = random.randint(8, 65)
                last_used = start + _rand_offset(int(dur_s * 0.25), int(dur_s * 0.95))
                await conn.execute(
                    """
                    INSERT INTO command_stats
                        (session_id, channel_id, command_name, usage_count, last_used_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (session_id, command_name) DO NOTHING
                    """,
                    sid,
                    channel_id,
                    cmd,
                    count,
                    last_used,
                )

            real_count = sum(1 for a in attendees if a["id"] in {r["id"] for r in REAL_ACCOUNTS})
            fake_count = len(attendees) - real_count
            print(
                f"  session {sid}: {len(attendees)} chatters "
                f"({real_count} real / {fake_count} fake)"
            )

        # ── 3. viewer_channel_status ───────────────────────────────────────────
        print("\n── viewer_channel_status ─────────────────────────────────────────")
        for acc in ALL_ACCOUNTS:
            if acc["id"] not in user_sessions:
                continue
            is_sub = acc["sub_tier"] is not None
            gifts_given = 10 if acc["id"] in _GIFT_DONORS else 0

            await conn.execute(
                """
                INSERT INTO viewer_channel_status
                    (channel_id, user_id, username, display_name,
                     is_subscribed, sub_tier, sub_gifted,
                     is_mod, is_vip, is_banned,
                     total_gifts_given, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, FALSE, $7, $8, FALSE, $9, NOW())
                ON CONFLICT (channel_id, user_id) DO UPDATE SET
                    is_subscribed     = EXCLUDED.is_subscribed,
                    sub_tier          = EXCLUDED.sub_tier,
                    is_mod            = EXCLUDED.is_mod,
                    is_vip            = EXCLUDED.is_vip,
                    total_gifts_given = EXCLUDED.total_gifts_given,
                    updated_at        = NOW()
                """,
                channel_id,
                acc["id"],
                acc["username"],
                acc["display"],
                is_sub,
                acc["sub_tier"] if is_sub else None,
                acc["is_mod"],
                acc["is_vip"],
                gifts_given,
            )
            role = "MOD" if acc["is_mod"] else ("VIP" if acc["is_vip"] else "—")
            print(
                f"  {acc['username']:<18} sub={'T' if is_sub else 'F'}"
                f"  role={role}"
                f"  sessions={len(user_sessions[acc['id']])}"
            )

        # ── 4. viewer_attendance_streaks (recomputed from scratch) ────────────
        print("\n── viewer_attendance_streaks ─────────────────────────────────────")
        await conn.execute(
            "DELETE FROM viewer_attendance_streaks WHERE channel_id = $1", channel_id
        )
        await conn.execute(
            """
            INSERT INTO viewer_attendance_streaks
                (channel_id, user_id, streak_count, best_streak, last_session_id, updated_at)
            WITH
            sessions_ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (ORDER BY started_at ASC) AS n
                FROM stream_sessions
                WHERE ended_at IS NOT NULL
                  AND channel_id = $1
                  AND attendance_snapshot_count > 0
            ),
            attendance AS (
                SELECT cs.user_id, cs.session_id, sr.n
                FROM chatter_stats cs
                JOIN sessions_ranked sr ON sr.id = cs.session_id
                WHERE cs.channel_id = $1
            ),
            streaks AS (
                SELECT user_id, session_id, n,
                       n - ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY n) AS grp
                FROM attendance
            ),
            latest AS (
                SELECT user_id, MAX(n) AS last_n FROM attendance GROUP BY user_id
            ),
            cur_grp AS (
                SELECT s.user_id, s.grp
                FROM streaks s
                JOIN latest l ON l.user_id = s.user_id AND l.last_n = s.n
            ),
            cur AS (
                SELECT s.user_id, COUNT(*)::INT AS streak
                FROM streaks s
                JOIN cur_grp cg ON cg.user_id = s.user_id AND cg.grp = s.grp
                GROUP BY s.user_id
            ),
            best AS (
                SELECT user_id, MAX(cnt)::INT AS best
                FROM (
                    SELECT user_id, grp, COUNT(*) AS cnt
                    FROM streaks GROUP BY user_id, grp
                ) g
                GROUP BY user_id
            ),
            last_sid AS (
                SELECT s.user_id, s.session_id
                FROM streaks s
                JOIN latest l ON l.user_id = s.user_id AND l.last_n = s.n
            )
            SELECT $1, c.user_id, c.streak, b.best, ls.session_id, NOW()
            FROM cur c
            JOIN best b    ON b.user_id  = c.user_id
            JOIN last_sid ls ON ls.user_id = c.user_id
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                streak_count    = EXCLUDED.streak_count,
                best_streak     = GREATEST(viewer_attendance_streaks.best_streak, EXCLUDED.best_streak),
                last_session_id = EXCLUDED.last_session_id,
                updated_at      = NOW()
            """,
            channel_id,
        )
        await conn.execute(
            """
            UPDATE viewer_attendance_streaks
            SET streak_count = 0,
                updated_at = NOW()
            WHERE channel_id = $1
              AND last_session_id IS DISTINCT FROM (
                  SELECT id
                  FROM stream_sessions
                  WHERE channel_id = $1
                    AND ended_at IS NOT NULL
                    AND attendance_snapshot_count > 0
                  ORDER BY started_at DESC, id DESC
                  LIMIT 1
              )
            """,
            channel_id,
        )

        streak_count = await conn.fetchval(
            "SELECT COUNT(*) FROM viewer_attendance_streaks WHERE channel_id = $1",
            channel_id,
        )
        print(f"  Recomputed streaks for {streak_count} viewers")

        real_pct = len(REAL_ACCOUNTS) / len(ALL_ACCOUNTS) * 100
        print(
            f"\n✓ Done — {n_sessions} sessions seeded"
            f"  |  real accounts: {len(REAL_ACCOUNTS)}/{len(ALL_ACCOUNTS)} ({real_pct:.0f}%)"
        )

    finally:
        await conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="[dev] generate fake session / viewer data.")
    parser.add_argument("channel_id", nargs="?", help="target channel (default: owner)")
    parser.add_argument("n_sessions", nargs="?", type=int, default=15)
    return parser


def run(args: argparse.Namespace) -> int:
    asyncio.run(seed_test_data(args.channel_id, args.n_sessions))
    return 0


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
