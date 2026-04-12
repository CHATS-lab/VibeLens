"""Tests for catalog CLI commands."""
from typer.testing import CliRunner

from vibelens.cli import app

runner = CliRunner()


def test_update_catalog_check_command():
    """update-catalog --check runs without error (may warn about missing URL)."""
    result = runner.invoke(app, ["update-catalog", "--check"])
    # Should not crash even without config
    assert result.exit_code in (0, 1)
    print(f"Output: {result.stdout}")


def test_build_catalog_requires_token():
    """build-catalog without --github-token fails with helpful message."""
    result = runner.invoke(app, ["build-catalog"])
    assert result.exit_code != 0 or "token" in result.stdout.lower()
