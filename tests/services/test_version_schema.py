"""Tests for VersionInfo schema."""

from vibelens.schemas.system import VersionInfo


def test_version_info_roundtrip():
    info = VersionInfo(
        current="1.0.4",
        latest="1.0.5",
        update_available=True,
        is_dev_build=False,
        install_method="uv",
        install_commands={
            "uv": "uv tool upgrade vibelens",
            "pip": "pip install -U vibelens",
            "npx": "npm install -g @chats-lab/vibelens@latest",
        },
    )
    dumped = info.model_dump()
    assert dumped["current"] == "1.0.4"
    assert dumped["is_dev_build"] is False
    assert dumped["install_method"] == "uv"


def test_version_info_accepts_null_latest():
    info = VersionInfo(
        current="1.0.4",
        latest=None,
        update_available=False,
        is_dev_build=False,
        install_method="unknown",
        install_commands={"uv": "", "pip": "", "npx": ""},
    )
    assert info.latest is None
