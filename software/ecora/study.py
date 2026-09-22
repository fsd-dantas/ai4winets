"""Reading the knowledge a study decides with, so it is data and not code.

The world became data when scenarios did. What decides over that world stayed in Python:
the rule inventory, the planner's configuration, the coordination policy, the predicate
projection and the frozen assembly were module constants. That made three implemented
mechanisms unreachable without editing the package. A rule conflict could not arise
because no two rules in the inventory could both hold; a plan was always one action
because the assembly declared one goal over one fluent; and the arbitration and multi-step
machinery, both tested, never ran outside their tests.

A study file supplies all of it. Changing what the system knows is an edit to a file, and
a different file is a different study rather than a tuned version of the same one.

The freeze is deliberately not loosened. Goals, costs and budgets are frozen with a study
so that an arm cannot be tuned after its results are seen, and that property is what makes
the arm comparisons worth anything. Loading them from a file changes where they are
written, not when they may change: a run still binds one study, the assembly still
governs what may be assembled, and switching studies is an explicit act that produces a
different study hash rather than a quiet edit to the one already being measured.
"""

import json
from pathlib import Path

from .contracts import digest, require

STUDIES = Path(__file__).resolve().parents[2] / "studies"

# Every section a study must supply. A file missing one is refused when it is read rather
# than part-way through a run, and a file carrying an unknown one is refused too: a
# misspelled section that was silently ignored would leave the default in place while
# appearing to have changed it.
SECTIONS = ("projection", "rules", "planner", "eco", "predicate_map", "oracle", "nulls",
            "assembly")
META = ("study_id", "revision", "note")


class Study:
    """One declared body of decision knowledge, addressed by the digest of its content."""

    def __init__(self, data):
        require(isinstance(data, dict), "a study is a JSON object")
        missing = [name for name in SECTIONS if name not in data]
        require(not missing, f"study is missing: {', '.join(missing)}")
        unknown = [name for name in data if name not in SECTIONS + META]
        require(not unknown, f"study declares unknown sections: {', '.join(sorted(unknown))}")
        for name in META:
            require(name in data, f"a study declares its {name}")
        self.data = data
        self.content_hash = digest(data)
        for name in SECTIONS:
            setattr(self, name, data[name])
        self.study_id = data["study_id"]
        self.revision = data["revision"]
        self.note = data["note"]
        self._check()

    def _check(self):
        """What has to hold before a run starts rather than be discovered during one."""
        rules = self.rules["rules"]
        identifiers = [rule["rule_id"] for rule in rules]
        require(len(set(identifiers)) == len(identifiers), "a rule identifier is declared twice")
        concluded = {rule["concludes"] for rule in rules}
        for rule in rules:
            for other in rule.get("contradicts", []):
                require(other in concluded,
                        f"{rule['rule_id']} contradicts {other}, which no rule concludes")
        require(self.rules.get("activation_budget", 0) > 0,
                "a rule inventory declares a positive activation budget")
        goals = self.assembly["planning"]["goals"]
        require(goals, "a study declares at least one planning goal")
        require(len(set(goals)) == len(goals), "a planning goal is declared twice")
        for goal in goals:
            require(len(goal.split(":")) == 3,
                    f"a goal is fluent:site:value; {goal} is not")
        # A predicate the rules can never produce cannot become a planning precondition,
        # so a mapping from one is a declaration that will never fire.
        for label in self.predicate_map:
            require(label in concluded,
                    f"the predicate map names {label}, which no rule concludes")

    def arbitrable(self):
        """The contradicting rule pairs whose conditions can both hold.

        A pair whose conditions are mutually exclusive can never conflict, so the
        arbitration it declares is unreachable. Reporting that is how a study says whether
        it can demonstrate conflict rather than merely declare rules that contradict.
        """
        rules = {rule["rule_id"]: rule for rule in self.rules["rules"]}
        authors = {rule["concludes"]: rule for rule in self.rules["rules"]}
        pairs = []
        for rule in self.rules["rules"]:
            for other in rule.get("contradicts", []):
                against = authors.get(other)
                if against is None or rule["rule_id"] >= against["rule_id"]:
                    continue
                if _overlapping(rule.get("condition"), against.get("condition")):
                    pairs.append((rule["rule_id"], against["rule_id"],
                                  "equal_priority" if rule["priority"] == against["priority"]
                                  else "priority_inhibition"))
        return sorted(pairs)


def _overlapping(one, other):
    """Whether two rule conditions can hold at once.

    Conditions over different metrics are independent, so both can hold. Over the same
    metric, equality on different values and a threshold split at the same boundary are
    the mutually exclusive cases; anything else is treated as able to overlap, because a
    pair wrongly reported as arbitrable is a weaker error than one wrongly reported safe.
    """
    if one is None or other is None:
        return True
    if one["metric"] != other["metric"]:
        return True
    ops, values = {one["op"], other["op"]}, (one["value"], other["value"])
    if ops == {"eq"} and values[0] != values[1]:
        return False
    if ops in ({"ge", "lt"}, {"gt", "le"}) and values[0] == values[1]:
        return False
    return True


def load(path):
    """Read one study file."""
    return Study(json.loads(Path(path).read_text(encoding="utf-8")))


def resolve(name):
    """A study by identifier under `studies/`, or by path to a file anywhere."""
    path = Path(name)
    if not path.exists():
        path = STUDIES / f"{name}.json"
    require(path.exists(), f"no study file at {name}")
    return load(path)


def catalogue(directory=STUDIES):
    """Every study file in a directory, by identifier, in a stable order."""
    found = {}
    for path in sorted(Path(directory).glob("*.json")):
        study = load(path)
        require(study.study_id not in found, f"two files declare {study.study_id}")
        found[study.study_id] = study
    return found
