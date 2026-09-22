# System contracts

**Status:** executable contract foundation implemented; simulator and decision methods planned

Index of the contracts that define the research system: what it observes, what it may do, how it decides, and the boundaries between its parts. Each contract is normative for the experiments that claim to implement it. This directory holds the specification; `software/` holds the code that must satisfy it.

ECoRA is **Expert Coordination, Resolution, and Assurance**, the planned simulation-based research architecture described in [docs/ECoRA](../docs/ECoRA/README.md). Its stages are interfaces with configurable Null, Proposed and Oracle providers.

Read these normative design specifications before pipeline implementation:

- [Interfaces](interfaces.md): serialisation, logging, provider substitution, stage datasets and replay.
- [Telemetry contract](telemetry-contract.md): observable evidence, missingness, locality and privileged Oracle access.
- [Action contract](action-contract.md): allowed effects, safety, authority, receipts and execution arms.
- [Simulator adapter](simulator-adapter.md): the seven calls a world must answer, and how a simulator
  in another process answers them without weakening the privilege boundary.

The [Python contract package](../software/README.md) implements schemas, frozen-study
admission, provider substitution, boundary logging and provenance checks, with synthetic
fixtures and executable tests. The remaining documents here are placeholders; simulator,
research providers and causal replay are not implemented by this foundation.
