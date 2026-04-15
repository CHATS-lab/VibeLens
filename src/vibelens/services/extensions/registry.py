"""Extension handler registry -- maps AgentExtensionType to handlers."""

from vibelens.models.enums import AgentExtensionType
from vibelens.services.extensions.command import CommandHandler
from vibelens.services.extensions.hook import HookHandler
from vibelens.services.extensions.repo import RepoHandler
from vibelens.services.extensions.skill import SkillHandler
from vibelens.services.extensions.subagent import SubagentHandler

_HANDLER_CLASSES = {
    AgentExtensionType.SKILL: SkillHandler,
    AgentExtensionType.SUBAGENT: SubagentHandler,
    AgentExtensionType.COMMAND: CommandHandler,
    AgentExtensionType.HOOK: HookHandler,
    AgentExtensionType.REPO: RepoHandler,
}

_instances: dict[AgentExtensionType, object] = {}


def get_handler(extension_type: AgentExtensionType):
    """Get the handler instance for the given extension type.

    Args:
        extension_type: The type of extension.

    Returns:
        Handler instance (SkillHandler, HookHandler, RepoHandler, etc.)

    Raises:
        ValueError: If no handler is registered for the type.
    """
    if extension_type not in _instances:
        handler_cls = _HANDLER_CLASSES.get(extension_type)
        if handler_cls is None:
            raise ValueError(f"No handler registered for {extension_type}")
        _instances[extension_type] = handler_cls()
    return _instances[extension_type]
