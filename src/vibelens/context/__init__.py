"""Context extraction — compress trajectory groups into LLM-ready text.

Public API:
    - ContextExtractor (ABC), MetadataExtractor, SummaryExtractor, DetailExtractor
    - ContextParams, PRESET_RECOMMENDATION, PRESET_CONCISE, PRESET_MEDIUM, PRESET_DETAIL
    - build_batches
    - build_metadata_block, format_user_prompt, format_agent_message
"""

from vibelens.context.base import ContextExtractor
from vibelens.context.batcher import build_batches
from vibelens.context.extractors import (
    DetailExtractor,
    MetadataExtractor,
    SummaryExtractor,
)
from vibelens.context.formatter import (
    build_metadata_block,
    format_agent_message,
    format_user_prompt,
    shorten_path,
    summarize_tool_args,
)
from vibelens.context.params import (
    PRESET_CONCISE,
    PRESET_DETAIL,
    PRESET_MEDIUM,
    PRESET_RECOMMENDATION,
    ContextParams,
)

__all__ = [
    "ContextExtractor",
    "MetadataExtractor",
    "SummaryExtractor",
    "DetailExtractor",
    "ContextParams",
    "PRESET_RECOMMENDATION",
    "PRESET_CONCISE",
    "PRESET_MEDIUM",
    "PRESET_DETAIL",
    "build_batches",
    "build_metadata_block",
    "format_user_prompt",
    "format_agent_message",
    "shorten_path",
    "summarize_tool_args",
]
