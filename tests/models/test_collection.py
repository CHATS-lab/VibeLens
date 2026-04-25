"""Tests for ExtensionCollection / ExtensionCollectionItem models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vibelens.models.collection import ExtensionCollection, ExtensionCollectionItem
from vibelens.models.enums import AgentExtensionType


def test_collection_item_valid() -> None:
    item = ExtensionCollectionItem(extension_type=AgentExtensionType.SKILL, name="pandas-helper")
    assert item.name == "pandas-helper"
    assert item.extension_type == AgentExtensionType.SKILL
    assert item.pinned_version is None


def test_collection_item_rejects_invalid_name() -> None:
    """Names must be kebab-case."""
    with pytest.raises(ValidationError):
        ExtensionCollectionItem(extension_type=AgentExtensionType.SKILL, name="Bad Name!")


def test_collection_valid() -> None:
    now = datetime.now(timezone.utc)
    collection = ExtensionCollection(
        name="data-stack",
        description="Python data stack",
        items=[
            ExtensionCollectionItem(extension_type=AgentExtensionType.SKILL, name="pandas-helper"),
            ExtensionCollectionItem(extension_type=AgentExtensionType.COMMAND, name="format-csv"),
        ],
        tags=["data", "python"],
        created_at=now,
        updated_at=now,
    )
    assert collection.name == "data-stack"
    assert len(collection.items) == 2


def test_collection_rejects_duplicate_items() -> None:
    """Same (extension_type, name) twice in items[] is rejected."""
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        ExtensionCollection(
            name="dup",
            description="",
            items=[
                ExtensionCollectionItem(extension_type=AgentExtensionType.SKILL, name="alpha"),
                ExtensionCollectionItem(extension_type=AgentExtensionType.SKILL, name="alpha"),
            ],
            tags=[],
            created_at=now,
            updated_at=now,
        )
