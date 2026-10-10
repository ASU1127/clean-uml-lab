"""Bounded label translation using measured fragments on unchanged routes."""
import copy
import math
import xml.etree.ElementTree as ET

from affinity_review import assess, POLICY as PROXIMITY
from audit import audit_svg
from fan_layout import overlap
from joint_labels import marker_boxes
from marker_labels import findings
from path_labels import segment_box_distance
from tree_layout import hits_box
from render_cache import fragments

LIMITS = dict(max_target_labels=12, max_positions_per_label=96, max_search_states=10000,
              max_endpoint_arclength=140, max_endpoint_fraction=.45,
              node_clearance=3, marker_clearance=2, passes=1)


def improve(model, graph, svg, cache, measured_domains=True, dense_prefix=True):
    """Change label x/y only; retain typography, frames, paths and every fact."""
    g = copy.deepcopy(graph)
    initial = cache.review(svg)
    log = dict(limits=LIMITS, measured_domains=measured_domains, dense_prefix=dense_prefix,
               before=len(initial['proximity_warnings']), after=len(initial['proximity_warnings']),
               accepted=False, domains=[], evaluated_positions=0, search_states=0,
               browser_calls_inside_search=0, new_layout_calls=0)
    labels = {l['id']: l for e in g['edges'] for l in e.get('labels', [])}
    targets = list(dict.fromkeys(w['label_id'] for w in sorted(initial['proximity_warnings'],
                                key=lambda w: (w['margin'], w['text_index'])) if w.get('label_id')))
    targets = [lid for lid in targets if lid in labels][:LIMITS['max_target_labels']]
    if not targets:
        return g, svg, log
    projected = cache.project(svg)
    elements = fragments(ET.fromstring(svg))
    groups = {lid: [i for i, t in enumerate(projected['texts']) if t.get('label_id') == lid]
              for lid in labels}
    paths = {edge['index']: list(zip(edge['points'], edge['points'][1:]))
             for edge in projected['edges']}
    nodes = [(n['x'] - 3, n['y'] - 3, n['x'] + n['width'] + 3, n['y'] + n['height'] + 3)
             for n in g['children']]
    markers = marker_boxes(g, model)

    def nominal(index, dx=0, dy=0):
        text = elements[index]
        x, y = float(text.get('x')) + dx, float(text.get('y')) + dy
        return (x, y - float(text.get('font-size')) * .75,
                x + float(text.get('textLength')), y)

    def rect(text, dx=0, dy=0, pad=0):
        return (text['x'] + dx - pad, text['y'] + dy - pad,
                text['x'] + dx + text['width'] + pad, text['y'] + dy + text['height'] + pad)

    fixed = [(rect(t), nominal(i)) for i, t in enumerate(projected['texts'])
             if not t.get('node') and t.get('label_id') not in targets]
    original_warning_counts = {lid: sum(w.get('label_id') == lid for w in initial['proximity_warnings'])
                               for lid in targets}

    def option(lid, x, y, fallback=False):
        label, indices = labels[lid], groups[lid]
        dx, dy = x - label['x'], y - label['y']
        actual = [rect(projected['texts'][i], dx, dy) for i in indices]
        native = [nominal(i, dx, dy) for i in indices]
        if measured_domains:
            guards = actual
        else:
            guards = [(x - 2, y - 2, x + label['width'] + 2, y + label['height'] + 2)]
        if not fallback:
            if any(b[0] < 0 or b[1] < 0 or b[2] > g['width'] or b[3] > g['height']
                   for b in actual + native):
                return None
            if any(overlap(b, n) for b in guards + native for n in nodes + markers):
                return None
            if any(hits_box(a, b, guard) for segments in paths.values()
                   for a, b in segments for guard in guards + native):
                return None
            if any(overlap(a, f) or overlap(n, fn) for a, n in zip(actual, native) for f, fn in fixed):
                return None
        moved_texts = []
        for i in indices:
            moved_texts.append({**projected['texts'][i], 'x': projected['texts'][i]['x'] + dx,
                               'y': projected['texts'][i]['y'] + dy})
        count = len(assess(dict(edges=projected['edges'], texts=moved_texts))['proximity_warnings'])
        if not measured_domains and not fallback:
            eid = projected['texts'][indices[0]]['relation']
            rectangle = guards[0]
            own = min(segment_box_distance(a, b, rectangle) for a, b in paths[eid])
            other = min((segment_box_distance(a, b, rectangle) for key, segments in paths.items()
                         if key != eid for a, b in segments), default=math.inf)
            if other - own < 4 - 1e-6:
                return None
        return dict(x=x, y=y, actual=actual, native=native, warnings=count,
                    moved=int(abs(dx) + abs(dy) > 1e-8), distance=math.hypot(dx, dy))

    domains = {}
    for lid in targets:
        label, indices = labels[lid], groups[lid]
        if not indices:
            raise ValueError('Measured label fragments missing: ' + lid)
        owner = projected['texts'][indices[0]]['relation']
        side = lid.rsplit('_', 1)[-1]
        segments = paths[owner]
        if side == 'target':
            segments = [(b, a) for a, b in reversed(segments)]
        if measured_domains:
            bs = [rect(projected['texts'][i]) for i in indices]
            ox = (min(b[0] for b in bs) + max(b[2] for b in bs)) / 2 - label['x']
            oy = (min(b[1] for b in bs) + max(b[3] for b in bs)) / 2 - label['y']
            width = max(b[2] for b in bs) - min(b[0] for b in bs)
            height = max(b[3] for b in bs) - min(b[1] for b in bs)
        else:
            ox, oy, width, height = label['width'] / 2, label['height'] / 2, label['width'], label['height']
        total = sum(math.dist(a, b) for a, b in segments)
        cap = total if side == 'center' else min(140, total * .45)
        distances = ([total * f for f in (.5, .35, .65, .2, .8)] if side == 'center' else
                     list(range(16, 141, 8)) if dense_prefix else [16, 30, 46, 64, 84, 110, 140])
        coords = [(label['x'], label['y'])]
        for distance in distances:
            if distance > cap + 1e-6:
                continue
            walked = 0.
            for a, b in segments:
                length = math.dist(a, b)
                if length and walked + length >= distance:
                    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
                    nx, ny = -uy, ux
                    for clearance in ((6, 10) if dense_prefix else (8,)):
                        offset = abs(nx) * width / 2 + abs(ny) * height / 2 + clearance
                        for sign in (1, -1):
                            coords.append((a[0] + ux * (distance - walked) + sign * nx * offset - ox,
                                           a[1] + uy * (distance - walked) + sign * ny * offset - oy))
                    break
                walked += length
        unique = list(dict.fromkeys(coords))[:LIMITS['max_positions_per_label']]
        candidates = []
        for index, (x, y) in enumerate(unique):
            log['evaluated_positions'] += 1
            candidate = option(lid, x, y, fallback=index == 0)
            if candidate:
                candidates.append(candidate)
        candidates.sort(key=lambda c: (c['warnings'], c['moved'], c['distance']))
        domains[lid] = candidates
        log['domains'].append(dict(label=lid, evaluated=len(unique), feasible=len(candidates),
                                   minimum_warnings=min(c['warnings'] for c in candidates)))
    chosen, best = {}, {lid: option(lid, labels[lid]['x'], labels[lid]['y'], fallback=True) for lid in targets}
    best_score = (sum(original_warning_counts.values()), 0, 0.)

    def compatible(candidate):
        return all(not any(overlap(a, b) for a in candidate['actual'] for b in old['actual']) and
                   not any(overlap(a, b) for a in candidate['native'] for b in old['native'])
                   for old in chosen.values())

    def search(todo, cost):
        nonlocal best, best_score
        if log['search_states'] >= LIMITS['max_search_states']:
            return
        log['search_states'] += 1
        if not todo:
            if cost < best_score:
                best, best_score = dict(chosen), cost
            return
        lower = tuple(cost[i] + sum(min(c[('warnings', 'moved', 'distance')[i]] for c in domains[lid])
                                  for lid in todo) for i in range(3))
        if lower >= best_score:
            return
        available = {lid: [c for c in domains[lid] if compatible(c)] for lid in todo}
        lid = min(todo, key=lambda name: (len(available[name]), name))
        for candidate in available[lid]:
            value = (cost[0] + candidate['warnings'], cost[1] + candidate['moved'], cost[2] + candidate['distance'])
            if value[0] > best_score[0]:
                continue
            chosen[lid] = candidate
            search(todo - {lid}, value)
            del chosen[lid]

    search(set(targets), (0, 0, 0.))
    root = ET.fromstring(svg)
    texts = fragments(root)
    for lid, candidate in best.items():
        dx, dy = candidate['x'] - labels[lid]['x'], candidate['y'] - labels[lid]['y']
        labels[lid].update(x=candidate['x'], y=candidate['y'])
        for index in groups[lid]:
            texts[index].set('x', str(float(texts[index].get('x')) + dx))
            texts[index].set('y', str(float(texts[index].get('y')) + dy))
    proposal = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    new = cache.review(proposal)
    accept = (not new['unmapped_fragments'] and len(new['proximity_warnings']) < log['before'] and
              not audit_svg(proposal, model)['findings'] and not findings(proposal))
    log.update(accepted=accept, proposed_warnings=len(new['proximity_warnings']),
               changed_labels=sum(c['moved'] for c in best.values()), exhausted=log['search_states'] >= 10000)
    if accept:
        log['after'] = len(new['proximity_warnings'])
        return g, proposal, log
    return copy.deepcopy(graph), svg, log
