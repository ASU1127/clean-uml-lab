"""Bounded straightening with stable unaffected label candidates."""
import copy
from fan_layout import points, box, safe
from tree_layout import draw, hits_box
from route_metrics import measure
from joint_labels import solve


def improve(model, metrics, graph):
    nodes = {n['id']: n for n in graph['children']}
    candidates = []
    for edge in graph['edges']:
        source, target = edge['sources'][0], edge['targets'][0]
        if source == target or source not in nodes or target not in nodes:
            continue
        if not edge['sections'][0].get('bendPoints'):
            continue
        a, b = points(edge)[0], points(edge)[-1]
        if not any(hits_box((a['x'], a['y']), (b['x'], b['y']), box(n)) for n in nodes.values()):
            candidates.append(edge['id'])
    events = []
    for eid in sorted(candidates)[:12]:
        before = measure(draw(model, metrics, graph)[1])
        trial = copy.deepcopy(graph)
        edge = next(e for e in trial['edges'] if e['id'] == eid)
        edge['sections'][0]['bendPoints'] = []
        after = measure(draw(model, metrics, trial)[1])
        if any(after[k] > before[k] for k in ('proper_crossings', 'other_contacts', 'shared_track_length', 'bends', 'route_length')):
            continue
        unchanged = {e['id'] for e in graph['edges'] if e['id'] != eid}
        if solve(trial, model=model, preserve_edges=unchanged) and safe(model, metrics, graph, trial):
            graph = trial
            events.append({'edge': eid, 'bends_removed': before['bends'] - after['bends']})
    return graph, events
