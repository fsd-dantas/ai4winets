"""Independent evidence calculations on plain records. No solver imports."""

from itertools import product


def evaluate(problem, assignment):
    """Check an assignment against map inputs, without consulting solver status/cost."""
    domains = problem['domains']
    pairs = [] if assignment is None else list(assignment)
    values = dict(pairs)
    duplicates = len(values) != len(pairs)
    missing = sorted(set(domains) - set(values))
    extra = sorted(set(values) - set(domains))
    invalid = sorted(n for n in values if n in domains and values[n] not in domains[n])
    complete = not (missing or extra or duplicates) and assignment is not None
    domain_valid = complete and not invalid
    conflicts = [list(edge) for edge in problem['edges']
                 if all(n in values and values[n] in domains[n] for n in edge)
                 and values[edge[0]] == values[edge[1]]]
    unary = sum(problem['scores'][n][domains[n].index(values[n])] for n in domains) if domain_valid else None
    return {'complete':complete,'domain_valid':domain_valid,'feasible':domain_valid and not conflicts,
            'missing':missing,'extra':extra,'duplicates':duplicates,'invalid':invalid,
            'conflicts':conflicts,'conflict_count':len(conflicts),
            'conflict_rate':len(conflicts)/len(problem['edges']) if domain_valid and problem['edges'] else None,
            'unary_cost':unary,'objective':unary if domain_valid and not conflicts else None}


def independent_choice(problem):
    return [[n,min(problem['domains'][n],key=lambda c:(problem['scores'][n][problem['domains'][n].index(c)],c))]
            for n in sorted(problem['domains'])]


def exact_reference(problem, *, max_assignments=65536):
    """Bounded independent enumerator for map constraints, never used by an agent."""
    if type(max_assignments) is not int or max_assignments < 1:
        raise ValueError('Reference budget must be positive')
    names = sorted(problem['domains'])
    size = 1
    for n in names:
        size *= len(problem['domains'][n])
    if size > max_assignments:
        return {'status':'budget_exceeded','cost':None,'assignment':None,'required':size,'checked':0}
    best, chosen = None, None
    for channels in product(*(sorted(problem['domains'][n]) for n in names)):
        values = dict(zip(names,channels))
        if any(values[a] == values[b] for a,b in problem['edges']):
            continue
        cost = sum(problem['scores'][n][problem['domains'][n].index(values[n])] for n in names)
        if best is None or cost < best:
            best,chosen = cost,list(zip(names,channels))
    return {'status':'infeasible' if best is None else 'optimal_cost','cost':best,
            'assignment':chosen,'required':size,'checked':size}
