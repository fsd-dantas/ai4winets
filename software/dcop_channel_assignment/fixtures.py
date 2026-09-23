"""Synthetic, deterministic fixtures. No measured radio data."""

from .wireless import ChannelPlanningScenario, Region


def grid_map(rows: int = 3, columns: int = 4, *, preferences: bool = False):
    if any(type(n) is not int or n < 1 for n in (rows, columns)):
        raise ValueError("Grid dimensions must be positive integers")
    regions = tuple(Region(f"region-{y * columns + x:02d}",
                           f"ap-{y * columns + x:02d}", (x, y, x + 1, y + 1))
                    for y in range(rows) for x in range(columns))
    costs = (0, 10, 20, 30) if preferences else (0, 0, 0, 0)
    return ChannelPlanningScenario(
        f"grid-{rows}x{columns}-{'preferences' if preferences else 'coloring'}",
        regions, ("c1", "c2", "c3", "c4"), tuple((r.ap_id, costs) for r in regions))
