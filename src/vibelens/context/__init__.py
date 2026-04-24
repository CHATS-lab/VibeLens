"""Context extraction — compress trajectory groups into LLM-ready text.

Public API:
    - ContextExtractor (ABC), MetadataExtractor, SummaryExtractor, DetailExtractor
    - ContextParams, PRESET_CONCISE, PRESET_MEDIUM, PRESET_DETAIL
    - build_batches
    - build_metadata_block, format_user_prompt, format_agent_message
    - format_context_batch, truncate_digest_to_fit, CONTEXT_TOKEN_BUDGET
"""

from vibelens.context.base import ContextExtractor
from vibelens.context.batcher import build_batches
from vibelens.context.extractors import (
    DetailExtractor,
    MetadataExtractor,
    SummaryExtractor,
)
from vibelens.context.formatter import (
    CONTEXT_TOKEN_BUDGET,
    build_metadata_block,
    format_agent_message,
    format_context_batch,
    format_user_prompt,
    shorten_path,
    summarize_tool_args,
    truncate_digest_to_fit,
)
from vibelens.context.params import (
    PRESET_CONCISE,
    PRESET_DETAIL,
    PRESET_MEDIUM,
    ContextParams,
)
from vibelens.context.sampler import sample_contexts

__all__ = [
    "ContextExtractor",
    "MetadataExtractor",
    "SummaryExtractor",
    "DetailExtractor",
    "ContextParams",
    "PRESET_CONCISE",
    "PRESET_MEDIUM",
    "PRESET_DETAIL",
    "CONTEXT_TOKEN_BUDGET",
    "build_batches",
    "build_metadata_block",
    "format_context_batch",
    "format_user_prompt",
    "format_agent_message",
    "sample_contexts",
    "shorten_path",
    "summarize_tool_args",
    "truncate_digest_to_fit",
]
