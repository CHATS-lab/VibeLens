"""Cross-parser contract test for activation-only skill detection.

Each parser owns its skill-activation tool name(s) as a module-local
constant. This test pins the per-parser sets so any drift breaks one
obvious test rather than silently changing field coverage.
"""

from vibelens.ingest.parsers import claude as claude_parser
from vibelens.ingest.parsers import codebuddy as codebuddy_parser
from vibelens.ingest.parsers import gemini as gemini_parser
from vibelens.ingest.parsers import hermes as hermes_parser
from vibelens.ingest.parsers import opencode as opencode_parser


def test_per_parser_skill_tool_names() -> None:
    """Each parser declares its own activation-tool constant.

    Adding a new dedicated activation tool is a deliberate edit on a
    specific parser; this test catches accidental drift.
    """
    assert frozenset({"Skill"}) == claude_parser._SKILL_TOOL_NAMES
    assert frozenset({"Skill"}) == codebuddy_parser._SKILL_TOOL_NAMES
    assert frozenset({"activate_skill"}) == gemini_parser._SKILL_TOOL_NAMES
    assert frozenset({"skill"}) == opencode_parser._SKILL_TOOL_NAMES
    assert frozenset({"skill_view"}) == hermes_parser._SKILL_TOOL_NAMES
