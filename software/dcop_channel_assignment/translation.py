"""Translate wireless planning into generic DCOP inputs."""

from .dcop import Cost, DcopInstance, Factor, Variable, inequality_factor
from .wireless import ChannelPlanningScenario
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .geography import GeographicScenario


def to_dcop(scenario: 'ChannelPlanningScenario | GeographicScenario') -> DcopInstance:
    variables = tuple(Variable(region.ap_id, scenario.channels)
                      for region in sorted(scenario.regions, key=lambda r: r.ap_id))
    by_id = {v.id: v for v in variables}
    scores = dict(scenario.scores)
    factors = [Factor(f"unary-{i}", (v.id,), (v.domain,),
                      tuple(Cost(c) for c in scores[v.id]))
               for i, v in enumerate(variables)]
    factors.extend(inequality_factor(f"edge-{i}", by_id[a], by_id[b])
                   for i, (a, b) in enumerate(scenario.edges))
    return DcopInstance(variables, tuple(factors))
