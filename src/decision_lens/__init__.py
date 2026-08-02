"""DecisionLens — an evidence-grounded AI decision-support agent.

DecisionLens helps product managers turn fragmented evidence into a traceable,
challengeable, and testable product recommendation. It supports the decision
process; the product manager remains accountable for the decision itself.

Architecture — one orchestrator, two kinds of component:

    connectors/   retrieve authorized evidence. They do not interpret it.
    skills/       interpret evidence. They do not retrieve it.
    orchestrator  coordinates the controlled workflow and owns nothing else.

There is deliberately no agent-per-data-source and no multi-agent topology. A
single coordinator with inspectable stages is what makes the output verifiable,
and verifiability is the property this prototype exists to test.

Built so far: the typed domain model (`decision_lens.models`) and the evidence-source
contract (`decision_lens.connectors`). Still to come: the local-file connector, the
model-provider boundary, the analysis skills, and the orchestrator. See
docs/05-decision-log.md for the build sequence and the reasoning behind it.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
