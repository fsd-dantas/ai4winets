"""Mobile-cell partitions; stability is ordinary unary cost, outside the solver."""

from dataclasses import dataclass, replace

from .evaluation import evaluate
from .execution import run
from .wireless import ChannelPlanningScenario, Region


@dataclass(frozen=True)
class MobileCellSequence:
    epochs: tuple[ChannelPlanningScenario, ...]
    mobile_id: str = 'mobile'

    def __post_init__(self):
        object.__setattr__(self,'epochs',tuple(self.epochs))
        if len(self.epochs)<3 or len({e.id for e in self.epochs}) != len(self.epochs):
            raise ValueError('At least three uniquely named validated epochs required')
        fixed = [{r.ap_id:r.id for r in e.regions if r.ap_id != self.mobile_id} for e in self.epochs]
        if any(ids != fixed[0] for ids in fixed):
            raise ValueError('Fixed region/AP identities must persist across epochs')
        if any(e.channels != self.epochs[0].channels for e in self.epochs):
            raise ValueError('Channel domain must remain stable')
        if any(c>100 for e in self.epochs for _,cs in e.scores for c in cs):
            raise ValueError('Base scores must be within declared 0..100 scale')


def mobile_sequence():
    epochs = []
    for label,host in [('baseline',None),('arrival',5),('move',6),('departure',None)]:
        regions = []
        for i in range(12):
            x,y = (i%4)*10,(i//4)*10
            regions.append(Region(f'region-{i:02d}',f'ap-{i:02d}',(x,y,x+(7 if i==host else 10),y+10)))
            if i==host:
                regions.append(Region('mobile-region','mobile',(x+7,y,x+10,y+10)))
        epochs.append(ChannelPlanningScenario(label,tuple(regions),('c1','c2','c3','c4'),
                                              tuple((r.ap_id,(0,100,100,100) if r.ap_id=='mobile' else (0,10,20,30)) for r in regions)))
    return MobileCellSequence(tuple(epochs))


def stability_scenario(epoch, previous, *, penalty, mobile_id):
    if type(penalty) is not int or penalty<0:
        raise ValueError('Nonnegative integer stability penalty required')
    if not evaluate(previous['problem'],previous['assignment'])['feasible']:
        raise ValueError('Previous epoch must have an independently valid assignment')
    old = dict(previous['assignment'])
    scores = tuple((n,tuple(c+(penalty if n!=mobile_id and n in old and ch!=old[n] else 0)
                           for ch,c in zip(epoch.channels,cs))) for n,cs in epoch.scores)
    return replace(epoch,scores=scores)


def run_epochs(sequence, *, stable, max_entries=1_000_000):
    records, summaries = [],[]
    for epoch in sequence.epochs:
        s = 101*len(epoch.regions) if stable and records else 0
        current = stability_scenario(epoch,records[-1],penalty=s,mobile_id=sequence.mobile_id) if records else epoch
        record = run(current,max_entries=max_entries)
        if not record['evaluation']['feasible']:
            records.append(record)
            summaries.append({'epoch':epoch.id,'status':record['status'],'reassignments':None})
            break  # Never carry an invalid or interrupted plan into another epoch.
        chosen = dict(record['assignment'])
        old = dict(records[-1]['assignment']) if records else {}
        common = set(old).intersection(chosen)
        fixed = common-{sequence.mobile_id}
        changed = sorted(n for n in fixed if old[n]!=chosen[n])
        base = sum(cs[epoch.channels.index(chosen[n])] for n,cs in epoch.scores)
        summaries.append({'epoch':epoch.id,'status':record['status'],'penalty':s,
                          'reassignments':len(changed),'changed_fixed_aps':changed,
                          'all_survivor_reassignments':sum(old[n]!=chosen[n] for n in common),
                          'base_cost':base,'objective':record['cost'],
                          'conflicts':record['evaluation']['conflict_count']})
        records.append(record)
    return records,summaries
