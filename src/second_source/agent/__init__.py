"""Model-based systems. Importing this module registers them with the CLI."""

from ..systems import SYSTEMS
from .investigator import agent_system, investigate
from .one_prompt import one_prompt_system

SYSTEMS["agent"] = agent_system
SYSTEMS["one_prompt"] = one_prompt_system

__all__ = ["agent_system", "investigate", "one_prompt_system"]
