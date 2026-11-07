"""Harness v0: the check-based agent. Importing this module registers it with the CLI."""

from ..systems import SYSTEMS
from .investigator import agent_system, investigate

SYSTEMS["agent"] = agent_system

__all__ = ["agent_system", "investigate"]
