# Five-region hand-checkable trace

Map: a-b-d-c-a is the single cycle, and e is attached to b. All unary costs are zero.
Root a explores b, then d, then c; b subsequently explores e. The non-tree edge is a-c.

Let I(x,y) be forbidden if x=y, otherwise zero. The local derivations are:

- U_c(a,d) = min_c [I(c,a) + I(c,d)] = 0 for every context: at most two of four colors are excluded.
- U_d(a,b) = min_d [I(d,b) + U_c(a,d)] = 0 for every context.
- U_e(b) = min_e I(e,b) = 0 for every context.
- U_b(a) = min_b [I(b,a) + U_d(a,b) + U_e(b)] = 0 for every context.
- U_a() = min_a U_b(a) = 0. Ties choose the lowest available color.

VALUE chooses a=c1, b=c2, d=c1, c=c2, e=c1. Every border has different endpoints.
The following complete transcript is generated from the saved run. It can be checked against those derivations.

## 1: dfs_explore a -> b

```json
{"path": ["a"]}
```

## 2: dfs_explore b -> d

```json
{"path": ["a", "b"]}
```

## 3: dfs_explore d -> c

```json
{"path": ["a", "b", "d"]}
```

## 4: dfs_return c -> d

```json
{"separator": ["a", "d"]}
```

## 5: dfs_return d -> b

```json
{"separator": ["a", "b"]}
```

## 6: dfs_explore b -> e

```json
{"path": ["a", "b"]}
```

## 7: dfs_return e -> b

```json
{"separator": ["b"]}
```

## 8: dfs_return b -> a

```json
{"separator": ["a"]}
```

## 9: dfs_explore a -> c

```json
{"path": ["a"]}
```

## 10: dfs_seen c -> a

```json
{}
```

## 11: util c -> d

Scope: ['a', 'd']

| Context | Minimum cost |
| --- | --- |
| ('c1', 'c1') | 0 |
| ('c1', 'c2') | 0 |
| ('c1', 'c3') | 0 |
| ('c1', 'c4') | 0 |
| ('c2', 'c1') | 0 |
| ('c2', 'c2') | 0 |
| ('c2', 'c3') | 0 |
| ('c2', 'c4') | 0 |
| ('c3', 'c1') | 0 |
| ('c3', 'c2') | 0 |
| ('c3', 'c3') | 0 |
| ('c3', 'c4') | 0 |
| ('c4', 'c1') | 0 |
| ('c4', 'c2') | 0 |
| ('c4', 'c3') | 0 |
| ('c4', 'c4') | 0 |

## 12: util e -> b

Scope: ['b']

| Context | Minimum cost |
| --- | --- |
| ('c1',) | 0 |
| ('c2',) | 0 |
| ('c3',) | 0 |
| ('c4',) | 0 |

## 13: util d -> b

Scope: ['a', 'b']

| Context | Minimum cost |
| --- | --- |
| ('c1', 'c1') | 0 |
| ('c1', 'c2') | 0 |
| ('c1', 'c3') | 0 |
| ('c1', 'c4') | 0 |
| ('c2', 'c1') | 0 |
| ('c2', 'c2') | 0 |
| ('c2', 'c3') | 0 |
| ('c2', 'c4') | 0 |
| ('c3', 'c1') | 0 |
| ('c3', 'c2') | 0 |
| ('c3', 'c3') | 0 |
| ('c3', 'c4') | 0 |
| ('c4', 'c1') | 0 |
| ('c4', 'c2') | 0 |
| ('c4', 'c3') | 0 |
| ('c4', 'c4') | 0 |

## 14: util b -> a

Scope: ['a']

| Context | Minimum cost |
| --- | --- |
| ('c1',) | 0 |
| ('c2',) | 0 |
| ('c3',) | 0 |
| ('c4',) | 0 |

## 15: value a -> b

```json
{"values": [["a", "c1"]]}
```

## 16: value b -> d

```json
{"values": [["a", "c1"], ["b", "c2"]]}
```

## 17: value b -> e

```json
{"values": [["b", "c2"]]}
```

## 18: value d -> c

```json
{"values": [["a", "c1"], ["d", "c1"]]}
```

## Independent verdict

{"complete": true, "conflict_count": 0, "conflict_rate": 0.0, "conflicts": [], "domain_valid": true, "duplicates": false, "extra": [], "feasible": true, "invalid": [], "missing": [], "objective": 0, "unary_cost": 0}
