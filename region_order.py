"""Bounded whole-region order search; local node geometry stays rigid."""
import copy
from route_metrics import measure

def improve(placed, pairs):
    g = copy.deepcopy(placed)
    nodes = {n['id']: n for n in g['children']}
    def score():
        centers = {k: (n['x'] + n['width']/2, n['y'] + n['height']/2) for k,n in nodes.items()}
        m = measure(dict(width=g['width'], height=g['height'], edges=[dict(index=i, points=[centers[a], centers[b]]) for i,(a,b) in enumerate(pairs)]))
        return m['proper_crossings'], m['route_length']
    rows = {}
    for n in nodes.values():
        rows.setdefault(round(n['y'], 5), []).append(n['id'])
    before = best = score()
    accepted = trials = 0
    for _ in range(4):
        changed = False
        for ids in rows.values():
            order = sorted(ids, key=lambda k: nodes[k]['x'])
            for a,b in zip(order, order[1:]):
                na,nb = nodes[a],nodes[b]
                ax,bx = na['x'],nb['x']
                gap = bx - ax - na['width']
                if gap < 0:
                    continue
                na['x'],nb['x'] = ax + nb['width'] + gap, ax
                trials += 1
                overlapping = any(x['x'] < y['x']+y['width'] and y['x'] < x['x']+x['width'] and x['y'] < y['y']+y['height'] and y['y'] < x['y']+x['height'] for i,x in enumerate(g['children']) for y in g['children'][i+1:])
                s = score()
                if not overlapping and s < best:
                    best = s
                    accepted += 1
                    changed = True
                    break
                na['x'],nb['x'] = ax,bx
        if not changed:
            break
    return g, dict(before=before, after=best, trials=trials, accepted=accepted)
