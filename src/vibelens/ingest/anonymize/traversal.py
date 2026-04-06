"""Deep traversal of Trajectory trees for field-level text transformation.

Walks the ATIF Trajectory structure and applies a text transform function
to all fields that may contain sensitive data (messages, paths, arguments,
extras), while leaving structural fields (IDs, timestamps, metrics) untouched.
"""

from collections.abc import Callable
from typing import Any

from vibelens.models.trajectories.trajectory import Trajectory

# Top-level Trajectory keys whose string values should be transformed
_TRAJECTORY_TEXT_KEYS = {"project_path", "first_message"}

# Step keys whose string values should be transformed
_STEP_TEXT_KEYS = {"message", "reasoning_content"}

# Keys at any level inside ``extra`` dicts are always transformed
# TrajectoryRef keys to transform
_REF_TEXT_KEYS = {"trajectory_path"}


def traverse_trajectory(trajectory: Trajectory, transform: Callable[[str], str]) -> Trajectory:
    """Apply a text transform to all sensitive fields in a Trajectory.

    Serializes the trajectory to a dict, walks all fields that may contain
    user data (messages, paths, arguments, extras), applies ``transform``
    to every string value, then validates back into a Trajectory model.

    Structural fields (session_id, step_id, tool_call_id, timestamps,
    metrics, function_name) are intentionally left untouched.

    Args:
        trajectory: Source trajectory (not modified in place).
        transform: A ``str -> str`` function applied to each sensitive string.

    Returns:
        A new Trajectory instance with transformed text fields.
    """
    data = trajectory.model_dump(mode="json")

    # Top-level text fields
    for key in _TRAJECTORY_TEXT_KEYS:
        if isinstance(data.get(key), str):
            data[key] = transform(data[key])

    data["extra"] = _transform_extra(data.get("extra"), transform)

    # Trajectory refs
    for ref_key in ("prev_trajectory_ref", "parent_trajectory_ref", "next_trajectory_ref"):
        data[ref_key] = _transform_ref(data.get(ref_key), transform)

    # Steps
    data["steps"] = [_transform_step(s, transform) for s in data["steps"]]

    return Trajectory.model_validate(data)


def _transform_value(value: Any, transform: Callable[[str], str]) -> Any:
    """Recursively apply *transform* to all strings in nested dicts/lists."""
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, dict):
        return {k: _transform_value(v, transform) for k, v in value.items()}
    if isinstance(value, list):
        return [_transform_value(item, transform) for item in value]
    return value


def _transform_extra(
    extra: dict[str, Any] | None, transform: Callable[[str], str]
) -> dict[str, Any] | None:
    """Transform all string values inside an ``extra`` dict recursively."""
    if extra is None:
        return None
    return _transform_value(extra, transform)


def _transform_content_parts(message: str | list, transform: Callable[[str], str]) -> str | list:
    """Transform text within a message that may be a string or ContentPart list."""
    if isinstance(message, str):
        return transform(message)
    # list[ContentPart] serialized as list of dicts
    result = []
    for part in message:
        if isinstance(part, dict):
            part = dict(part)
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                part["text"] = transform(part["text"])
            # Non-text content parts (images, PDFs) are left untouched
        result.append(part)
    return result


def _transform_ref(ref_data: dict | None, transform: Callable[[str], str]) -> dict | None:
    """Transform sensitive fields in a TrajectoryRef dict."""
    if ref_data is None:
        return None
    ref_data = dict(ref_data)
    for key in _REF_TEXT_KEYS:
        if isinstance(ref_data.get(key), str):
            ref_data[key] = transform(ref_data[key])
    ref_data["extra"] = _transform_extra(ref_data.get("extra"), transform)
    return ref_data


def _transform_observation_result(obs: dict, transform: Callable[[str], str]) -> dict:
    """Transform sensitive fields in a serialized ObservationResult."""
    obs = dict(obs)
    content = obs.get("content")
    if content is not None:
        obs["content"] = _transform_content_parts(content, transform)
    obs["extra"] = _transform_extra(obs.get("extra"), transform)
    # Transform trajectory paths inside subagent refs
    sub_refs = obs.get("subagent_trajectory_ref")
    if isinstance(sub_refs, list):
        obs["subagent_trajectory_ref"] = [_transform_ref(r, transform) for r in sub_refs]
    return obs


def _transform_tool_call(tc_data: dict, transform: Callable[[str], str]) -> dict:
    """Transform sensitive fields in a serialized ToolCall."""
    tc_data = dict(tc_data)
    args = tc_data.get("arguments")
    if args is not None:
        tc_data["arguments"] = _transform_value(args, transform)
    tc_data["extra"] = _transform_extra(tc_data.get("extra"), transform)
    return tc_data


def _transform_step(step_data: dict, transform: Callable[[str], str]) -> dict:
    """Transform sensitive fields in a serialized Step."""
    step_data = dict(step_data)
    for key in _STEP_TEXT_KEYS:
        value = step_data.get(key)
        if value is None:
            continue
        step_data[key] = _transform_content_parts(value, transform)
    step_data["extra"] = _transform_extra(step_data.get("extra"), transform)
    # Tool calls
    if "tool_calls" in step_data:
        step_data["tool_calls"] = [
            _transform_tool_call(tc, transform) for tc in step_data["tool_calls"]
        ]
    # Observation results
    obs = step_data.get("observation")
    if isinstance(obs, dict) and "results" in obs:
        obs = dict(obs)
        obs["results"] = [_transform_observation_result(r, transform) for r in obs["results"]]
        step_data["observation"] = obs
    return step_data
