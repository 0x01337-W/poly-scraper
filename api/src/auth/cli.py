import os
import sys
import click

from src.auth.key_store import ApiKeyStore


def _get_store() -> ApiKeyStore:
    db_path = os.getenv("API_KEY_DB_PATH", "/data/keys.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return ApiKeyStore(db_path)


@click.group()
def cli() -> None:
    """Admin CLI for API key management."""


@cli.command()
@click.argument("key")
@click.option("--plan", "plan_type", default="monthly", show_default=True)
@click.option("--status", default="active", show_default=True, type=click.Choice(["active", "revoked"]))
@click.option("--expires-at", default=None, help="ISO8601 expiration timestamp")
def upsert(key: str, plan_type: str, status: str, expires_at: str | None) -> None:
    """Create or update an API key."""
    store = _get_store()
    store.upsert_key(key, plan_type=plan_type, status=status, expires_at=expires_at)
    click.echo(f"upserted key={key} plan={plan_type} status={status}")


@cli.command()
def list() -> None:  # type: ignore[override]
    """List all API keys."""
    store = _get_store()
    # direct sqlite since store has no method; reuse private for simplicity
    import sqlite3

    conn = sqlite3.connect(store.db_path)
    cur = conn.execute("SELECT key, plan_type, status, created_at, COALESCE(expires_at, '') FROM api_keys ORDER BY created_at DESC")
    rows = cur.fetchall()
    for r in rows:
        click.echo("|".join(str(x) for x in r))


@cli.command()
@click.argument("key")
def revoke(key: str) -> None:
    """Revoke an API key."""
    store = _get_store()
    store.upsert_key(key, status="revoked")
    click.echo(f"revoked key={key}")


if __name__ == "__main__":
    sys.exit(cli())


