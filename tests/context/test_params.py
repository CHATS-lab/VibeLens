"""Tests for src/vibelens/context/params.py."""

import dataclasses

import pytest

from vibelens.context.params import (
    PRESET_CONCISE,
    PRESET_DETAIL,
    PRESET_MEDIUM,
    PRESET_RECOMMENDATION,
    ContextParams,
)


def test_context_params_is_frozen() -> None:
    """ContextParams is a frozen dataclass and rejects attribute mutation."""
    params = ContextParams(
        user_prompt_max_chars=100,
        user_prompt_head_chars=80,
        user_prompt_tail_chars=20,
        bash_command_max_chars=50,
        tool_arg_max_chars=50,
        error_truncate_chars=100,
        include_non_error_obs=False,
        observation_max_chars=0,
        agent_message_max_chars=0,
        agent_message_head_chars=0,
        agent_message_tail_chars=0,
        shorten_home_prefix=True,
        path_max_segments=2,
    )
    assert dataclasses.is_dataclass(params)
    with pytest.raises(dataclasses.FrozenInstanceError):
        params.user_prompt_max_chars = 999  # type: ignore[misc]
    print("PASS: ContextParams is frozen — mutation raises FrozenInstanceError")


def test_preset_recommendation_values() -> None:
    """PRESET_RECOMMENDATION has maximum-compression values."""
    p = PRESET_RECOMMENDATION
    assert p.user_prompt_max_chars == 500
    assert p.user_prompt_head_chars == 400
    assert p.user_prompt_tail_chars == 100
    assert p.bash_command_max_chars == 0
    assert p.tool_arg_max_chars == 0
    assert p.error_truncate_chars == 200
    assert p.include_non_error_obs is False
    assert p.observation_max_chars == 0
    assert p.agent_message_max_chars == 0
    assert p.shorten_home_prefix is True
    assert p.path_max_segments == 2
    print(
        f"PASS: PRESET_RECOMMENDATION values correct — "
        f"user_prompt_max_chars={p.user_prompt_max_chars}"
    )


def test_preset_ordering_by_compression() -> None:
    """Presets are ordered from most to least compressed by user_prompt_max_chars."""
    limits = [
        PRESET_RECOMMENDATION.user_prompt_max_chars,
        PRESET_CONCISE.user_prompt_max_chars,
        PRESET_MEDIUM.user_prompt_max_chars,
        PRESET_DETAIL.user_prompt_max_chars,
    ]
    assert limits == sorted(limits), (
        f"Expected ascending order but got {limits}"
    )
    print(f"PASS: compression ordering correct — {limits}")


def test_preset_detail_includes_observations() -> None:
    """PRESET_DETAIL enables non-error observation inclusion."""
    assert PRESET_DETAIL.include_non_error_obs is True
    assert PRESET_DETAIL.observation_max_chars > 0
    print(
        "PASS: PRESET_DETAIL includes observations — "
        f"observation_max_chars={PRESET_DETAIL.observation_max_chars}"
    )


def test_preset_medium_excludes_observations() -> None:
    """PRESET_MEDIUM does not include non-error observations."""
    assert PRESET_MEDIUM.include_non_error_obs is False
    assert PRESET_MEDIUM.observation_max_chars == 0
    print("PASS: PRESET_MEDIUM excludes observations")


def test_custom_params() -> None:
    """ContextParams can be instantiated with arbitrary custom values."""
    custom = ContextParams(
        user_prompt_max_chars=9999,
        user_prompt_head_chars=7000,
        user_prompt_tail_chars=2999,
        bash_command_max_chars=500,
        tool_arg_max_chars=300,
        error_truncate_chars=2000,
        include_non_error_obs=True,
        observation_max_chars=400,
        agent_message_max_chars=1000,
        agent_message_head_chars=700,
        agent_message_tail_chars=300,
        shorten_home_prefix=False,
        path_max_segments=0,
    )
    assert custom.user_prompt_max_chars == 9999
    assert custom.include_non_error_obs is True
    assert custom.shorten_home_prefix is False
    assert custom.path_max_segments == 0
    print(
        f"PASS: custom ContextParams instantiated — "
        f"user_prompt_max_chars={custom.user_prompt_max_chars}"
    )
