"""Deterministic, explicitly non-uniform planar topological map generation."""

import hashlib
import json
import math
import random


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def streams(seed):
    if type(seed) is not int or seed < 0:
        raise ValueError('Seed must be a nonnegative integer')
    return {name: int(hashlib.sha256(f'{name}:{seed}'.encode('ascii')).hexdigest()[:16], 16)
            for name in ('topology', 'cost')}


def make_map(size, density, topology_seed, profile, cost_seed):
    """Generate a connected planar graph, then independently draw integer costs.

    Sparse target: n-1+ceil(n/4). Dense target: 2n. The labels describe
    targets, while each run records the realized edge count and density.
    Rejection by planarity is deterministic. No uniform sampling claim.
    """
    import networkx as nx
    if size not in (10, 12, 16, 20) or density not in ('sparse', 'dense'):
        raise ValueError('Undeclared size or density')
    if profile not in ('shared', 'independent'):
        raise ValueError('Undeclared cost profile')
    names = [f'ap-{i:02d}' for i in range(size)]
    target = size - 1 + math.ceil(size / 4) if density == 'sparse' else 2 * size
    topo_rng = random.Random(topology_seed)
    graph = nx.Graph()
    graph.add_nodes_from(names)
    order = names[:]
    topo_rng.shuffle(order)
    for i in range(1, size):
        graph.add_edge(order[i], order[topo_rng.randrange(i)])
    candidates = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
                  if not graph.has_edge(a, b)]
    topo_rng.shuffle(candidates)
    for a, b in candidates:
        if graph.number_of_edges() >= target:
            break
        graph.add_edge(a, b)
        if not nx.check_planarity(graph)[0]:
            graph.remove_edge(a, b)
    if graph.number_of_edges() != target:
        raise ValueError('Planar generator could not reach declared edge target')
    cost_rng = random.Random(cost_seed)
    if profile == 'shared':
        shared = [cost_rng.randrange(101) for _ in range(4)]
        scores = {n: shared[:] for n in names}
    else:
        scores = {n: [cost_rng.randrange(101) for _ in range(4)] for n in names}
    return {'id': f'generated-{size}-{density}-{topology_seed}-{profile}-{cost_seed}',
            'regions': names, 'borders': [list(e) for e in sorted(tuple(sorted(e)) for e in graph.edges)],
            'scores': scores}


def pilot_cases():
    """Six topology strata x two cost profiles x two paired arms = 24 runs."""
    cases = []
    for size in (10, 16, 20):
        for density in ('sparse', 'dense'):
            seed = size * 100 + (0 if density == 'sparse' else 1)
            named = streams(seed)
            for profile in ('shared', 'independent'):
                # Cost seed differs by profile, but both arms within a pair share it.
                cost_seed = named['cost'] + (0 if profile == 'shared' else 1)
                case = make_map(size, density, named['topology'], profile, cost_seed)
                cases.append({'key': f'n{size}-{density}-{profile}', 'map': case,
                              'size': size, 'density': density, 'profile': profile,
                              'seed': seed, 'streams': {'topology': named['topology'],
                                                       'cost': cost_seed},
                              'realized_edges': len(case['borders']),
                              'realized_density': 2 * len(case['borders']) / (size * (size - 1))})
    return cases
