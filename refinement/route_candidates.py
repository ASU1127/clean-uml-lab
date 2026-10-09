"""Bounded full-scene, label-feasible routing from alternative class faces."""
import math
from collections import defaultdict

from port_routes import options as old_options
from auxiliary_groups import center, xy, pt
from fan_layout import points, box
from tree_layout import hits_box

LIMITS = {'max_edges': 100, 'max_route_options_per_edge': 192,
          'max_label_solves_per_edge': 12, 'solver_limit': 10000, 'passes': 1}


def router(nodes, edges):
    byid = {n['id']: n for n in nodes}
    groups = defaultdict(list)
    faces = {}
    for e in edges:
        a, b = e['sources'][0], e['targets'][0]
        if a == b:
            continue
        for nid, other in ((a, b), (b, a)):
            n, o = byid[nid], byid[other]
            cx, cy = center(n)
            ox, oy = center(o)
            choices = []
            if ox < n['x']: choices.append('left')
            if ox > n['x']+n['width']: choices.append('right')
            if oy < n['y']: choices.append('top')
            if oy > n['y']+n['height']: choices.append('bottom')
            faces[e['id'], nid] = choices
            for face in choices:
                groups[nid, face].append((oy if face in ('left', 'right') else ox, e['id']))
    slots = {}
    for (nid, face), group in groups.items():
        n = byid[nid]
        span = n['height'] if face in ('left', 'right') else n['width']
        inset = min(12, span/4)
        for i, (_, eid) in enumerate(sorted(group)):
            p = inset+(span-2*inset)*(i+1)/(len(group)+1)
            slots[eid, nid, face] = pt(n['x']+(n['width'] if face == 'right' else 0), n['y']+p) if face in ('left', 'right') else pt(n['x']+p, n['y']+(n['height'] if face == 'bottom' else 0))

    def options(edge):
        a, b = byid[edge['sources'][0]], byid[edge['targets'][0]]
        if a['id'] == b['id']:
            return [points(edge)]
        proposals = old_options(a, b, nodes)
        for af in faces.get((edge['id'], a['id']), []):
            for bf in faces.get((edge['id'], b['id']), []):
                start = slots[edge['id'], a['id'], af]
                end = slots[edge['id'], b['id'], bf]
                proposals += [[start, end], [start, pt(start['x'], end['y']), end], [start, pt(end['x'], start['y']), end]]
        seen, valid = set(), []
        for ps in proposals:
            ps = [p for i, p in enumerate(ps) if i == 0 or math.dist(xy(p), xy(ps[i-1])) > .01]
            if len(ps) < 2 or any(p['x'] < 12 or p['y'] < 12 for p in ps):
                continue
            if any(hits_box(xy(a), xy(b), box(n)) for a, b in zip(ps, ps[1:]) for n in nodes):
                continue
            signature = tuple((round(p['x'], 6), round(p['y'], 6)) for p in ps)
            if signature in seen:
                continue
            seen.add(signature)
            valid.append(ps)
        # Cap after geometric ordering; new direct ports are not lost at the tail
        # of a long enumeration of obstacle-corner alternatives.
        valid.sort(key=lambda ps: (len(ps)-2, sum(math.dist(xy(a), xy(b)) for a, b in zip(ps, ps[1:]))))
        return valid[:LIMITS['max_route_options_per_edge']]
    return options

