"""Personalization-specific enumerations."""

from vibelens.utils.compat import StrEnum


class PersonalizationMode(StrEnum):
    """Personalization analysis mode."""

    CREATION = "creation"
    EVOLUTION = "evolution"
    RECOMMENDATION = "recommendation"
