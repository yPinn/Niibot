"""Static contract for migration 156 (stream-schedule token trigger FK fix)."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_token_trigger_skips_channels_that_do_not_exist_yet():
    sql = (_VERSIONS / "156_fix_stream_schedule_token_trigger.sql").read_text(encoding="utf-8")

    # Replaces 149's function in place (the triggers keep pointing at it).
    assert "CREATE OR REPLACE FUNCTION fn_enqueue_stream_schedule_publish()" in sql
    # A first sign-in writes the token before the channels row exists — the
    # tokens branch must return early instead of hitting the queue's FK.
    tokens_branch = sql[
        sql.index("IF TG_TABLE_NAME = 'tokens' THEN") : sql.index("ELSIF TG_OP = 'DELETE'")
    ]
    assert "NOT EXISTS (SELECT 1 FROM channels WHERE channel_id = NEW.user_id)" in tokens_branch
    assert tokens_branch.index("NOT EXISTS") < tokens_branch.index(
        "target_channel_id := NEW.user_id"
    )
    # Every other source still enqueues exactly as in 149.
    assert "INSERT INTO stream_schedule_publish_queue (channel_id)" in sql


def test_dev_console_tracebacks_never_print_locals():
    import structlog

    from shared.logging_setup import _build_formatter

    formatter = _build_formatter([], console=True)
    renderers = [p for p in formatter.processors if isinstance(p, structlog.dev.ConsoleRenderer)]
    assert renderers, "console formatter has no ConsoleRenderer"
    exc_formatter = renderers[0]._exception_formatter
    assert getattr(exc_formatter, "show_locals", None) is False
