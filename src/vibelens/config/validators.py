"""Configuration validators for optional integrations."""

from vibelens.config.settings import Settings


def validate_mongodb_config(settings: Settings) -> str:
    """Validate that MongoDB is configured and return the URI.

    Args:
        settings: Application settings to validate.

    Raises:
        ValueError: If mongodb_uri is not configured.

    Returns:
        The MongoDB connection URI.
    """
    if not settings.mongodb_uri:
        raise ValueError(
            "MongoDB is not configured — set VIBELENS_MONGODB_URI environment variable"
            " or mongodb.uri in vibelens.yaml"
        )
    return settings.mongodb_uri
