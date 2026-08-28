"""Backfill Matcher overlap tables from existing chatter_stats data.

Uses data already collected by the bot in chatter_stats to compute
channel_overlap_summary and channel_overlap_viewers for the Matcher feature.

    npm run nb -- twitch backfill-matcher [--days 7,30,90] [--dry-run]
    uv run --directory backend python scripts/twitch_backfill_matcher.py [...]
"""

from __future__ import annotations

import argparse
import asyncio

import asyncpg
from _lib import add_env_arg, ensure_backend_on_path, load_env, utf8_stdio

ensure_backend_on_path()
utf8_stdio()

from api.core.config import get_settings  # noqa: E402

WINDOWS = [7, 30, 90]


async def show_chatter_stats_summary(conn: asyncpg.Connection, home_channel_id: str) -> list[str]:
    """Print chatter_stats breakdown and return list of partner channel IDs."""
    rows = await conn.fetch(
        """
        SELECT
            channel_id,
            COUNT(DISTINCT user_id)                                          AS unique_chatters,
            COUNT(DISTINCT session_id)                                       AS sessions,
            MAX(last_message_at)                                             AS latest_activity
        FROM chatter_stats
        GROUP BY channel_id
        ORDER BY unique_chatters DESC
        """
    )

    print("\n[chatter_stats 資料概覽]")
    print(f"  {'channel_id':<20} {'chatters':>10} {'sessions':>10}  latest_activity")
    print("  " + "-" * 65)
    partner_ids: list[str] = []
    for r in rows:
        marker = "← home" if r["channel_id"] == home_channel_id else "← partner"
        print(
            f"  {r['channel_id']:<20} {r['unique_chatters']:>10,} {r['sessions']:>10,}"
            f"  {r['latest_activity'].strftime('%Y-%m-%d %H:%M')}  {marker}"
        )
        if r["channel_id"] != home_channel_id:
            partner_ids.append(r["channel_id"])

    print(f"\n  發現 {len(partner_ids)} 個 partner 頻道可計算 overlap")
    return partner_ids


async def show_existing_overlap(conn: asyncpg.Connection, home_channel_id: str) -> None:
    """Print current state of overlap tables."""
    summary_count = await conn.fetchval(
        "SELECT COUNT(*) FROM channel_overlap_summary WHERE home_channel_id = $1",
        home_channel_id,
    )
    viewer_count = await conn.fetchval(
        "SELECT COUNT(*) FROM channel_overlap_viewers WHERE home_channel_id = $1",
        home_channel_id,
    )
    print("\n[現有 overlap 資料]")
    print(f"  channel_overlap_summary : {summary_count} 筆")
    print(f"  channel_overlap_viewers : {viewer_count} 筆")


async def backfill_overlap(
    conn: asyncpg.Connection,
    home_channel_id: str,
    partner_ids: list[str],
    days: int,
) -> int:
    """Compute overlap for all partner channels for a given window. Returns count computed."""
    count = 0
    for partner_id in partner_ids:
        try:
            await _compute_channel_overlap(conn, home_channel_id, partner_id, days)
            count += 1
        except Exception as e:
            print(f"    [!] partner {partner_id} 計算失敗: {e}")
    return count


async def _compute_channel_overlap(
    conn: asyncpg.Connection,
    home_channel_id: str,
    partner_channel_id: str,
    days: int,
) -> None:
    """Replicate _overlap_mixin._compute_channel_overlap for standalone use."""
    viewer_rows = await conn.fetch(
        """
        WITH partner_chatters AS (
            SELECT
                cs.user_id,
                MAX(cs.username)                                            AS username,
                MAX(cs.display_name)                                        AS display_name,
                COUNT(DISTINCT cs.session_id)::SMALLINT                    AS sessions,
                COALESCE(SUM(cs.message_count), 0)                         AS messages,
                COALESCE(SUM(cs.watch_seconds), 0)                         AS watch_sec,
                MAX(cs.last_message_at)                                     AS last_seen
            FROM chatter_stats cs
            WHERE cs.channel_id = $1
              AND cs.last_message_at >= NOW() - ($3 * INTERVAL '1 day')
            GROUP BY cs.user_id
        ),
        home_chatters AS (
            SELECT
                cs.user_id,
                COUNT(DISTINCT cs.session_id)::SMALLINT                    AS sessions,
                COALESCE(SUM(cs.message_count), 0)                         AS messages
            FROM chatter_stats cs
            WHERE cs.channel_id = $2
              AND cs.last_message_at >= NOW() - ($3 * INTERVAL '1 day')
            GROUP BY cs.user_id
        )
        SELECT
            pc.user_id,
            pc.username,
            pc.display_name,
            pc.sessions                        AS partner_sessions,
            pc.messages                        AS partner_messages,
            pc.watch_sec                       AS partner_watch_sec,
            pc.last_seen                       AS partner_last_seen,
            COALESCE(hc.sessions, 0)::SMALLINT AS home_sessions,
            COALESCE(hc.messages, 0)           AS home_messages,
            ROUND(
                (
                    (pc.sessions * 3.0
                     + LN(GREATEST(pc.messages, 1)) * 1.5
                     + (pc.watch_sec / 3600.0) * 0.5)
                    * CASE
                        WHEN hc.user_id IS NULL THEN 1.0
                        WHEN hc.sessions < 3    THEN 0.5
                        ELSE                         0.1
                      END
                )::numeric
            , 2) AS potential_score
        FROM partner_chatters pc
        LEFT JOIN home_chatters hc ON pc.user_id = hc.user_id
        """,
        partner_channel_id,
        home_channel_id,
        days,
    )

    if not viewer_rows:
        print(f"      {partner_channel_id}: 無 chatter 資料（{days}d 內），跳過")
        return

    await conn.executemany(
        """
        INSERT INTO channel_overlap_viewers (
            home_channel_id, partner_channel_id, user_id,
            username, display_name,
            partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
            home_sessions, home_messages, potential_score, computed_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
        ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
            username          = EXCLUDED.username,
            display_name      = EXCLUDED.display_name,
            partner_sessions  = EXCLUDED.partner_sessions,
            partner_messages  = EXCLUDED.partner_messages,
            partner_watch_sec = EXCLUDED.partner_watch_sec,
            partner_last_seen = EXCLUDED.partner_last_seen,
            home_sessions     = EXCLUDED.home_sessions,
            home_messages     = EXCLUDED.home_messages,
            potential_score   = EXCLUDED.potential_score,
            computed_at       = NOW()
        """,
        [
            (
                home_channel_id,
                partner_channel_id,
                r["user_id"],
                r["username"],
                r["display_name"],
                r["partner_sessions"],
                r["partner_messages"],
                r["partner_watch_sec"],
                r["partner_last_seen"],
                r["home_sessions"],
                r["home_messages"],
                r["potential_score"],
            )
            for r in viewer_rows
        ],
    )

    partner_total = len(viewer_rows)
    shared = sum(1 for r in viewer_rows if r["home_sessions"] > 0)
    exclusive = partner_total - shared
    home_total = int(
        await conn.fetchval(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM chatter_stats
            WHERE channel_id = $1
              AND last_message_at >= NOW() - ($2 * INTERVAL '1 day')
            """,
            home_channel_id,
            days,
        )
        or 0
    )
    overlap_pct = round(shared / partner_total * 100, 2) if partner_total else 0.0

    await conn.execute(
        """
        INSERT INTO channel_overlap_summary (
            home_channel_id, partner_channel_id, window_days,
            partner_unique_chatters, home_unique_chatters,
            shared_chatters, exclusive_to_partner, overlap_pct, computed_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        ON CONFLICT (home_channel_id, partner_channel_id, window_days) DO UPDATE SET
            partner_unique_chatters = EXCLUDED.partner_unique_chatters,
            home_unique_chatters    = EXCLUDED.home_unique_chatters,
            shared_chatters         = EXCLUDED.shared_chatters,
            exclusive_to_partner    = EXCLUDED.exclusive_to_partner,
            overlap_pct             = EXCLUDED.overlap_pct,
            computed_at             = NOW()
        """,
        home_channel_id,
        partner_channel_id,
        days,
        partner_total,
        home_total,
        shared,
        exclusive,
        overlap_pct,
    )

    print(
        f"      {partner_channel_id}: {partner_total} chatters, "
        f"{shared} 共同 / {exclusive} 潛在, overlap {overlap_pct}%"
    )


async def main(target_days: list[int], dry_run: bool) -> None:
    settings = get_settings()

    print("=" * 60)
    print("Matcher Overlap 回填腳本")
    print("=" * 60)
    if dry_run:
        print("  [DRY-RUN] 只預覽資料，不寫入")

    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        # Get home channel
        channels = await conn.fetch(
            "SELECT channel_id, channel_name FROM channels WHERE enabled = TRUE ORDER BY created_at"
        )
        if not channels:
            print("\n[X] 沒有啟用的頻道")
            return

        all_channel_ids = {ch["channel_id"] for ch in channels}

        print("\n[啟用頻道]")
        for ch in channels:
            print(f"  {ch['channel_name']} ({ch['channel_id']})")

        # All distinct channel_ids that have chatter data
        chatter_channel_ids: set[str] = {
            r["channel_id"]
            for r in await conn.fetch("SELECT DISTINCT channel_id FROM chatter_stats")
        }

        # Home channels = enabled channels that also have chatter data
        home_channels = [ch for ch in channels if ch["channel_id"] in chatter_channel_ids]
        if not home_channels:
            print("\n[X] 啟用頻道裡沒有任何 chatter 資料")
            return

        print(f"\n  將對 {len(home_channels)} 個頻道各自計算 overlap")

        if dry_run:
            for ch in home_channels:
                partner_ids = [
                    cid
                    for cid in chatter_channel_ids
                    if cid != ch["channel_id"] and cid in all_channel_ids
                ]
                print(f"\n  {ch['channel_name']}: {len(partner_ids)} 個 partner 可計算")
            print("\n[DRY-RUN] 結束，未寫入任何資料")
            return

        # Run backfill for every home channel
        total_summary = 0
        total_viewers = 0
        for ch in home_channels:
            home_channel_id = ch["channel_id"]
            partner_ids = [
                cid
                for cid in chatter_channel_ids
                if cid != home_channel_id and cid in all_channel_ids
            ]
            if not partner_ids:
                print(f"\n  {ch['channel_name']}: 沒有 partner 資料，跳過")
                continue

            print(f"\n{'=' * 40}")
            print(f"  home: {ch['channel_name']} ({home_channel_id})")
            print(f"  partners: {len(partner_ids)} 個")
            print(f"  windows: {target_days}")

            for days in target_days:
                print(f"\n  --- {days}d ---")
                count = await backfill_overlap(conn, home_channel_id, partner_ids, days)
                print(f"  [{days}d] 完成 {count}/{len(partner_ids)}")

        total_summary = await conn.fetchval("SELECT COUNT(*) FROM channel_overlap_summary")
        total_viewers = await conn.fetchval("SELECT COUNT(*) FROM channel_overlap_viewers")
        print("\n" + "=" * 60)
        print("[完成]")
        print(f"  channel_overlap_summary : {total_summary} 筆")
        print(f"  channel_overlap_viewers : {total_viewers} 筆")
        print("=" * 60)

    finally:
        await conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill Matcher overlap tables.")
    parser.add_argument(
        "--days",
        default=",".join(map(str, WINDOWS)),
        help="comma-separated windows (default 7,30,90)",
    )
    parser.add_argument("--dry-run", action="store_true")
    add_env_arg(parser)
    return parser


def run(args: argparse.Namespace) -> int:
    load_env(args.env)
    try:
        target_days = [int(d) for d in str(args.days).split(",")]
    except ValueError:
        print(f"Invalid --days value: {args.days!r}  (例: --days 7,30,90)")
        return 1
    asyncio.run(main(target_days, args.dry_run))
    return 0


def _main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
