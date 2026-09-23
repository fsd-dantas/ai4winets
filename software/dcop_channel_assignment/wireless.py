"""Synthetic rectangular coverage maps, with exact boundary-derived adjacency."""

from dataclasses import dataclass
from itertools import combinations

from .dcop import identifier


@dataclass(frozen=True)
class Region:
    id: str
    ap_id: str
    bounds: tuple[int, int, int, int]

    def __post_init__(self):
        identifier(self.id)
        identifier(self.ap_id)
        object.__setattr__(self, "bounds", tuple(self.bounds))
        if len(self.bounds) != 4 or any(type(x) is not int for x in self.bounds):
            raise ValueError("Bounds must contain four integer coordinates")
        x0, y0, x1, y1 = self.bounds
        if x0 >= x1 or y0 >= y1:
            raise ValueError("Regions require positive area")


@dataclass(frozen=True)
class ChannelPlanningScenario:
    id: str
    regions: tuple[Region, ...]
    channels: tuple[str, ...]
    scores: tuple[tuple[str, tuple[int, ...]], ...]

    def __post_init__(self):
        identifier(self.id)
        object.__setattr__(self, "regions", tuple(self.regions))
        object.__setattr__(self, "channels", tuple(self.channels))
        object.__setattr__(self, "scores", tuple((ap, tuple(costs)) for ap, costs in self.scores))
        if not self.regions or len({r.id for r in self.regions}) != len(self.regions):
            raise ValueError("Regions must be nonempty and uniquely identified")
        aps = {r.ap_id for r in self.regions}
        if len(aps) != len(self.regions):
            raise ValueError("Each region must own a unique AP")
        if len(self.channels) != 4 or len(set(self.channels)) != 4:
            raise ValueError("This model requires four distinct abstract channels")
        for channel in self.channels:
            identifier(channel)
        if len(self.scores) != len(aps) or {ap for ap, _ in self.scores} != aps:
            raise ValueError("Scores must cover each AP exactly once")
        for _, costs in self.scores:
            if len(costs) != len(self.channels):
                raise ValueError("Scores must cover every channel")
            if any(type(c) is not int or c < 0 for c in costs):
                raise ValueError("Scores must be nonnegative integers")
        # Interior-disjoint rectangles with segment adjacency define a planar map.
        for left, right in combinations(self.regions, 2):
            dx, dy = self._overlap(left, right)
            if dx > 0 and dy > 0:
                raise ValueError("Region interiors must not overlap")
        reached = {self.regions[0].ap_id}
        while True:
            expanded = reached | {a for a, b in self.edges if b in reached}
            expanded |= {b for a, b in self.edges if a in reached}
            if expanded == reached:
                break
            reached = expanded
        if reached != aps:
            raise ValueError("The boundary-adjacency graph must be connected")

    @staticmethod
    def _overlap(left: Region, right: Region) -> tuple[int, int]:
        a, b, c, d = left.bounds
        e, f, g, h = right.bounds
        return min(c, g) - max(a, e), min(d, h) - max(b, f)

    @property
    def edges(self) -> tuple[tuple[str, str], ...]:
        edges = []
        for left, right in combinations(self.regions, 2):
            dx, dy = self._overlap(left, right)
            if (dx == 0 and dy > 0) or (dy == 0 and dx > 0):
                edges.append(tuple(sorted((left.ap_id, right.ap_id))))
        return tuple(sorted(edges))
