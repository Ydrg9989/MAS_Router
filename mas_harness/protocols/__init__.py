"""Protocol registry.

Importing this package registers every protocol, so the runner and the go/no-go report can
enumerate them without knowing the module layout.
"""

# Imported for their registration side effects.
from . import aggregation as _aggregation  # noqa: F401
from . import conformity as _conformity  # noqa: F401
from . import debate as _debate  # noqa: F401
from . import expert as _expert  # noqa: F401
from . import governance as _governance  # noqa: F401
from .base import (
    AGGREGATOR,
    FACILITATOR,
    ProtocolContext,
    ProtocolInfo,
    ProtocolResult,
    available_protocols,
    get_protocol,
    protocol_card,
)

# The five MVP protocols of the research report, in the order it lists them. These are
# baselines: they describe how existing systems allocate influence.
MVP_PROTOCOLS = [
    "single_expert",
    "independent_majority",
    "debate_vote",
    "independent_judge",
    "expert_verifier",
]

# Protocols 6 and 7: the report's proposed interventions, run only after the pilot clears the
# go/no-go gate. Each is paired with the MVP baseline it differs from by one rule.
PROPOSED_PROTOCOLS = ["expert_veto", "chair_information_seeking"]

# The baseline each proposed protocol must be compared against. Reporting a proposed protocol
# without its pair would confound the governance rule with the extra calls it makes.
PROPOSED_PAIRS = {
    "expert_veto": "expert_verifier",
    "chair_information_seeking": "independent_judge",
}

# Protocols that make no model calls, so an episode over them is free (D-009).
FREE_PROTOCOLS = frozenset({"single_expert", "independent_majority"})

__all__ = [
    "AGGREGATOR",
    "FACILITATOR",
    "FREE_PROTOCOLS",
    "MVP_PROTOCOLS",
    "PROPOSED_PAIRS",
    "PROPOSED_PROTOCOLS",
    "ProtocolContext",
    "ProtocolInfo",
    "ProtocolResult",
    "available_protocols",
    "get_protocol",
    "protocol_card",
]
