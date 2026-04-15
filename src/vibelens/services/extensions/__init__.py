"""Extension management services."""

from vibelens.services.extensions.browse import (
    get_extension_by_id,
    get_extension_metadata,
    install_extension,
    list_extensions,
    resolve_extension_content,
)

__all__ = [
    "get_extension_by_id",
    "get_extension_metadata",
    "install_extension",
    "list_extensions",
    "resolve_extension_content",
]
