from enum import StrEnum

from .tier1 import tier1_manager, tier1_server
from .tier2 import tier2_manager, tier2_server


class McpTier(StrEnum):
    TIER1 = "tier1"
    TIER2 = "tier2"
    INVALID_OAUTH_TOKEN = "invalid_oauth_token"


tier_servers = {McpTier.TIER1: tier1_server, McpTier.TIER2: tier2_server}
tier_managers = {McpTier.TIER1: tier1_manager, McpTier.TIER2: tier2_manager}

__all__ = ["McpTier", "tier_servers", "tier_managers", "tier1_manager", "tier2_manager"]
