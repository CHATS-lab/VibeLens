"""Trajectory anonymization — pluggable redaction of sensitive data.

Provides a base class for anonymizers and a rule-based implementation
that detects credentials, PII, and usernames in file paths.
"""

from vibelens.config.anonymize import AnonymizeConfig
from vibelens.ingest.anonymize.base import AnonymizeResult, BaseAnonymizer

__all__ = ["AnonymizeConfig", "AnonymizeResult", "BaseAnonymizer"]
