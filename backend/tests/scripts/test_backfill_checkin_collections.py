"""Safety and argument-contract tests for the collection backfill CLI."""

from __future__ import annotations

from dataclasses import replace

import backfill_checkin_collections as cli
import pytest

from shared.collection_backfill import BackfillReport


def test_parser_defaults_to_a_report_only_production_preview() -> None:
    args = cli.build_parser().parse_args([])

    assert args.env == "prod"
    assert args.batch_size == 100
    assert args.apply is False
    assert args.dry_run is False
    assert args.yes is False
    assert cli.is_dry_run(args) is True


def test_parser_supports_explicit_staging_apply_and_dry_run() -> None:
    apply_args = cli.build_parser().parse_args(["--env", "staging", "--batch-size", "7", "--apply"])
    dry_args = cli.build_parser().parse_args(["--env", "staging", "--dry-run"])

    assert apply_args.env == "staging"
    assert apply_args.batch_size == 7
    assert cli.is_dry_run(apply_args) is False
    assert cli.is_dry_run(dry_args) is True

    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--apply", "--dry-run"])


@pytest.mark.parametrize("value", ["0", "1001", "not-a-number"])
def test_parser_rejects_an_invalid_batch_size(value: str) -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--batch-size", value])


@pytest.mark.asyncio
@pytest.mark.parametrize("env_args", [[], ["--env", "staging"]])
async def test_every_apply_refuses_before_opening_the_database_without_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    env_args: list[str],
) -> None:
    args = cli.build_parser().parse_args([*env_args, "--apply"])
    opened = False

    def refuse(_prompt: str, assume_yes: bool = False) -> bool:
        assert assume_yes is False
        return False

    def forbidden_db_conn(_env: str):
        nonlocal opened
        opened = True
        raise AssertionError("database must not be opened")

    monkeypatch.setattr(cli, "confirm", refuse)
    monkeypatch.setattr(cli, "db_conn", forbidden_db_conn)

    assert await cli._run(args) == 2
    assert opened is False


@pytest.mark.asyncio
async def test_default_preview_reports_candidates_without_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = cli.build_parser().parse_args([])
    expected = BackfillReport(scanned=3, inserted=0, skipped=3, remaining=3, failures=0)

    class FakeConnectionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_exc: object) -> None:
            return None

    async def fake_backfill(_conn: object, *, batch_size: int, dry_run: bool) -> BackfillReport:
        assert batch_size == 100
        assert dry_run is True
        return expected

    monkeypatch.setattr(cli, "db_conn", lambda env: FakeConnectionContext())
    monkeypatch.setattr(cli, "backfill_checkin_collections", fake_backfill)
    monkeypatch.setattr(
        cli,
        "confirm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not prompt")),
    )

    assert await cli._run(args) == 0
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "scanned=3" in output
    assert "inserted=0" in output
    assert "skipped=3" in output
    assert "remaining=3" in output
    assert "failures=0" in output
    assert "entropy" not in output.lower()


@pytest.mark.asyncio
async def test_apply_returns_failure_when_rows_remain_or_a_viewer_transaction_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = cli.build_parser().parse_args(["--env", "staging", "--apply", "--yes"])
    successful = BackfillReport(scanned=2, inserted=2, skipped=0, remaining=0, failures=0)

    class FakeConnectionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_exc: object) -> None:
            return None

    result = successful

    async def fake_backfill(_conn: object, *, batch_size: int, dry_run: bool) -> BackfillReport:
        assert dry_run is False
        return result

    monkeypatch.setattr(cli, "db_conn", lambda env: FakeConnectionContext())
    monkeypatch.setattr(cli, "backfill_checkin_collections", fake_backfill)

    assert await cli._run(args) == 0
    result = replace(successful, remaining=1)
    assert await cli._run(args) == 1
    result = replace(successful, failures=1)
    assert await cli._run(args) == 1
