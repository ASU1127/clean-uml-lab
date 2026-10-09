"""Independent path-prefix sampling and relation-affinity label constraints.

Both switches off reproduce the release joint solver. Affinity is a visual
proximity heuristic, not UML Property ownership or human comprehension proof.
"""
import math

from tree_layout import hits_box
from fan_layout import points, box, overlap
from qualifier_layout import edge_geometry
from joint_labels import marker_boxes

POLICY = {'max_endpoint_arclength': 140, 'max_endpoint_fraction': .45,
          'affinity_margin': 4, 'solver_limit': 10000}


def point_segment(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    den = dx*dx+dy*dy
    t = min(1., max(0., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def segment_box_distance(a, b, rectangle):
    if hits_box(a, b, rectangle):
        return 0.
    def point_box(p):
        return math.hypot(max(rectangle[0]-p[0], 0., p[0]-rectangle[2]),
                          max(rectangle[1]-p[1], 0., p[1]-rectangle[3]))
    corners = [(rectangle[x], rectangle[y]) for x in (0, 2) for y in (1, 3)]
    return min(point_box(a), point_box(b), *(point_segment(p, a, b) for p in corners))


def affinity(rectangle, eid, routed):
    own = min((segment_box_distance(a, b, rectangle) for a, b in routed[eid]), default=math.inf)
    foreign = [(min(segment_box_distance(a, b, rectangle) for a, b in segments), other)
               for other, segments in routed.items() if other != eid and segments]
    nearest, competitor = min(foreign, default=(math.inf, None))
    return {'own_distance': own, 'other_distance': nearest, 'other_edge': competitor,
            'margin': nearest-own, 'risk': nearest-own < POLICY['affinity_margin']-1e-6}


def solve(g, model=None, preserve_edges=(), traverse=False, affinity_guard=False,
          limit=10000, trace=None):
    labels = [(e, l) for e in g['edges'] for l in e.get('labels', [])]
    nodes = [box(n, 3) for n in g['children']]
    log = trace if trace is not None else {}
    log.update(traverse=traverse, affinity_guard=affinity_guard, labels=len(labels),
               rejected_affinity=0, failed_label=None, search_states=0)
    if model is not None:
        try:
            nodes += marker_boxes(g, model)
        except ValueError as exc:
            log['error'] = str(exc)
            return False
    def routed_points(e):
        if model is not None and e.get('qualifier_sizes'):
            ps, _ = edge_geometry(g, e, model)
            if e.get('semanticReverse', False):
                ps = list(reversed(ps))
            return [dict(x=x, y=y) for x, y in ps]
        return points(e)
    try:
        routed = {e['id']: [((a['x'], a['y']), (b['x'], b['y']))
                           for a, b in zip(routed_points(e), routed_points(e)[1:])]
                  for e in g['edges']}
    except ValueError as exc:
        log['error'] = str(exc)
        return False
    routes = [segment for segments in routed.values() for segment in segments]
    options = []
    for e, label in labels:
        side = label['id'].rsplit('_', 1)[-1]
        tail = (side == 'source') != e.get('semanticReverse', False)
        segments = routed[e['id']]
        if side != 'center' and not tail:
            segments = [(b, a) for a, b in reversed(segments)]
        candidates = []
        def append(x, y):
            rectangle = (x-2, y-2, x+label['width']+2, y+label['height']+2)
            if x < 0 or y < 0 or rectangle[2] > g['width'] or rectangle[3] > g['height']:
                return
            if any(overlap(rectangle, n) for n in nodes) or any(hits_box(a, b, rectangle) for a, b in routes):
                return
            if affinity_guard and affinity(rectangle, e['id'], routed)['risk']:
                log['rejected_affinity'] += 1
                return
            candidate = (x, y, rectangle)
            if candidate not in candidates:
                candidates.append(candidate)
        if e['id'] in preserve_edges:
            append(label['x'], label['y'])
        def around(a, b, distance):
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx, dy)
            if length < 1:
                return
            ux, uy = dx/length, dy/length
            nx, ny = -uy, ux
            offset = abs(nx)*label['width']/2+abs(ny)*label['height']/2+8
            for sign in (1, -1):
                x = a[0]+ux*distance+sign*nx*offset-label['width']/2
                y = a[1]+uy*distance+sign*ny*offset-label['height']/2
                append(x, y)
        # Retain the complete release candidate order when switches are off.
        for a, b in (segments if side == 'center' else segments[:1]):
            length = math.dist(a, b)
            ds = [length*f for f in (.5, .35, .65, .2, .8)] if side == 'center' else [min(d, length*.45) for d in (30, 46, 64, 84, 110, 140, 16)]
            for d in ds:
                around(a, b, d)
        if traverse and side != 'center':
            total = sum(math.dist(a, b) for a, b in segments)
            cap = min(POLICY['max_endpoint_arclength'], total*POLICY['max_endpoint_fraction'])
            for distance in (16, 30, 46, 64, 84, 110, 140):
                if distance > cap+1e-6:
                    continue
                walked = 0.
                for a, b in segments:
                    length = math.dist(a, b)
                    if walked+length >= distance:
                        around(a, b, distance-walked)
                        break
                    walked += length
        if not candidates:
            log['failed_label'] = label['id']
            log['failed_first_segment_length'] = math.dist(*segments[0]) if segments else None
            return False
        options.append(candidates)
    chosen = {}
    def search(todo):
        if not todo:
            return True
        log['search_states'] += 1
        if log['search_states'] > limit:
            return False
        available = {i: [c for c in options[i] if all(not overlap(c[2], p[2]) for p in chosen.values())] for i in todo}
        i = min(todo, key=lambda i: (len(available[i]), labels[i][1]['id']))
        for candidate in available[i]:
            chosen[i] = candidate
            if search(todo-{i}):
                return True
            del chosen[i]
        return False
    if not search(set(range(len(labels)))):
        log['search_failed'] = True
        return False
    for i, (_, label) in enumerate(labels):
        label['x'], label['y'] = chosen[i][:2]
    log['solved'] = True
    return True


def findings(g, model=None):
    routed = {}
    for edge in g['edges']:
        ps = points(edge)
        if model is not None and edge.get('qualifier_sizes'):
            visible, _ = edge_geometry(g, edge, model)
            if edge.get('semanticReverse', False):
                visible = list(reversed(visible))
            ps = [dict(x=x, y=y) for x, y in visible]
        routed[edge['id']] = [((a['x'], a['y']), (b['x'], b['y'])) for a, b in zip(ps, ps[1:])]
    result = []
    for edge in g['edges']:
        for label in edge.get('labels', []):
            value = affinity(box(label, 2), edge['id'], routed)
            if value['risk']:
                result.append({'label': label['id'], 'edge': edge['id'], 'text': '\n'.join(label['lines']), **value})
    return result
