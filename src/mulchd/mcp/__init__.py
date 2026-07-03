from .tier1 import tier1_manager, tier1_server
from .tier2 import tier2_manager, tier2_server
from .tier3 import tier3_manager, tier3_server

tier_servers = {
    "tier1": tier1_server,
    "tier2": tier2_server,
    "tier3": tier3_server,
}

tier_managers = {
    "tier1": tier1_manager,
    "tier2": tier2_manager,
    "tier3": tier3_manager,
}

__all__ = ["tier_servers", "tier_managers", "tier1_manager", "tier2_manager", "tier3_manager"]
