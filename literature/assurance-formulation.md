# Provenance of the service assurance constraint

**Type:** evidence synthesis. **Status:** sources identified; primary texts not yet consulted.

## The constraint

The repository states its organising requirement as

$$\Pr\left(D_i \leq D_i^{\max}\right) \geq 1 - \epsilon_i$$

for a critical service $i$, where $D_i$ is end-to-end delay, $D_i^{\max}$ is the deadline and $\epsilon_i$ is
the allowable violation probability.

This note records where that constraint comes from, because an uncited formula reads as an original
formulation. It is not one. It is the standard statistical delay bound.

## What each source supplies

| Source | What it supplies | What it does not supply |
| --- | --- | --- |
| 3GPP TS 22.261 | The normative definition: reliability is the proportion of packets delivered within the time constraint the service requires | Any particular deadline or budget |
| 3GPP TS 23.501 | Per-flow structure: each 5QI carries its own Packet Delay Budget and Packet Error Rate | Values for services outside the standardised set |
| Wu and Negi (2003) | The wireless link model expressed in delay-violation-probability terms | An end-to-end, multi-hop or multi-RAT formulation |
| Fidler and Rizk (2015) | The general framework for probabilistic delay bounds | A wireless-specific channel model |
| Bennis, Debbah and Poor (2018) | The argument that reliability requirements demand tail-oriented rather than average-based design | The constraint itself |
| IEC 61850-5 | Transfer-time classes that give $D_i^{\max}$ concrete values in substation communications | Any statement about violation probability |

## Relationships between the sources

The 3GPP definition and the formula are the **same statement in two forms**. 3GPP expresses it as a percentage
of packets meeting a time constraint; the formula expresses it as a probability with an explicit violation
budget $\epsilon_i$. Nothing is added by the change of form, and no source should be credited with more than
its form contributes.

The per-service index $i$ is not decorative. It reflects the 5QI structure, in which each QoS flow carries its
own delay budget and error rate, rather than one network-wide requirement.

**The formula supplies the form, never the values.** $D_i^{\max}$ and $\epsilon_i$ are domain inputs. For
substation communications the deadlines derive from IEC 61850-5 transfer-time classes; for any other service
class they must be derived and attributed separately. A deadline that appears in a scenario definition without
a cited origin is a stipulated value, and must be declared as such.

## Open verification tasks

- [ ] Consult TS 22.261 directly; record clause number and the release cited.
- [ ] Consult TS 23.501 directly; confirm the 5QI table reference. This entry is currently **unverified**.
- [ ] Consult IEC 61850-5 directly; confirm edition and the transfer-time class values. Present values come
      from vendor and review literature only.
- [ ] Confirm whether IEC 61850-5's application-to-application transfer-time definition is compatible with the
      delay measured in simulation. If it is not, any comparison against those classes is invalid until the
      measurement boundary is reconciled.
- [ ] Establish whether an end-to-end, multi-hop formulation is needed, since the wireless link model is
      single-hop. A per-link bound does not compose into an end-to-end bound without further argument.

The last two are not bookkeeping. Each could invalidate a comparison that otherwise looks sound.
