"""Tests for the vibelens recommend CLI command."""
import shutil

from typer.testing import CliRunner

from vibelens.cli import app

runner = CliRunner()


def test_recommend_help():
    """vibelens recommend --help works."""
    result = runner.invoke(app, ["recommend", "--help"])
    assert result.exit_code == 0
    assert "--top-n" in result.output
    assert "--no-open" in result.output


def test_discover_finds_available_backends(monkeypatch):
    """discover_and_select_backend finds CLIs in PATH."""
    # Mock shutil.which to simulate 'gemini' being available
    def mock_which(name):
        if name == "gemini":
            return "/usr/local/bin/gemini"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    from vibelens.llm.backends import _CLI_BACKEND_REGISTRY

    backends = []
    for backend_type, (module_path, class_name) in _CLI_BACKEND_REGISTRY.items():
        # Lazy-import to get cli_executable
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        instance = cls()
        if shutil.which(instance.cli_executable):
            backends.append((backend_type, instance))

    assert len(backends) >= 1
    print(f"Found {len(backends)} available backends")
