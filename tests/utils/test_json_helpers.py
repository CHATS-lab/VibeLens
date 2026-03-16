"""Tests for vibelens.utils.json_helpers."""

from vibelens.utils.json_helpers import (
    coerce_json_field,
    coerce_to_list,
    coerce_to_string,
    deterministic_id,
    extract_text_from_blocks,
)


class TestCoerceToString:
    """Test coerce_to_string() polymorphic dispatch."""

    def test_list_delegates_to_extract(self):
        blocks = [{"type": "text", "text": "line1"}, {"type": "text", "text": "line2"}]
        assert coerce_to_string(blocks) == "line1\nline2"

    def test_dict_serialized_as_json(self):
        result = coerce_to_string({"key": "value"})
        assert '"key"' in result and '"value"' in result


class TestCoerceToList:
    """Test coerce_to_list() edge cases."""

    def test_string_wraps_as_text_block(self):
        result = coerce_to_list("hello")
        assert result == [{"type": "text", "text": "hello"}]

    def test_empty_string_returns_empty(self):
        assert coerce_to_list("") == []


class TestExtractTextFromBlocks:
    """Test extract_text_from_blocks() mixed-type handling."""

    def test_non_text_blocks_skipped(self):
        blocks = [
            {"type": "text", "text": "keep"},
            {"type": "image", "source": "data"},
            {"type": "text", "text": "also keep"},
        ]
        assert extract_text_from_blocks(blocks) == "keep\nalso keep"

    def test_bare_strings_extracted(self):
        assert extract_text_from_blocks(["hello", "world"]) == "hello\nworld"


class TestCoerceJsonField:
    """Test coerce_json_field() heuristic decoding."""

    def test_whitespace_padded_json(self):
        result = coerce_json_field('  {"key": "val"}  ')
        assert result == {"key": "val"}

    def test_non_json_string_returns_none(self):
        assert coerce_json_field("just text") is None


class TestDeterministicId:
    """Test deterministic_id() contract."""

    def test_same_inputs_produce_same_id(self):
        id_a = deterministic_id("msg", "session-1", "0")
        id_b = deterministic_id("msg", "session-1", "0")
        assert id_a == id_b

    def test_hex_truncated_to_24_chars(self):
        result = deterministic_id("msg", "x")
        _, hex_part = result.split("-", 1)
        assert len(hex_part) == 24
