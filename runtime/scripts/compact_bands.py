"""Bounded whitespace compression preserving class boxes and label sizes."""
import copy
from fan_layout import points, safe
from tree_layout import draw
from route_metrics import measure


def improve(model, metrics, graph, axes=('y', 'x')):
    events = []
    for axis in axes:
        extent = 'height' if axis == 'y' else 'width'
        attempts = 0
        for _ in range(3):
            intervals = sorted((item[axis], item[axis] + item[extent])
                               for item in list(graph['children']) +
                               [label for edge in graph['edges'] for label in edge.get('labels', [])])
            merged = []
            for lo, hi in intervals:
                if merged and lo <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], hi)
                else:
                    merged.append([lo, hi])
            gaps = sorted(((a[1], b[0]) for a, b in zip(merged, merged[1:])
                           if b[0] - a[1] > 52), key=lambda pair: -(pair[1] - pair[0]))
            before = measure(draw(model, metrics, graph)[1])
            changed = False
            for lo, hi in gaps:
                for remaining in (36, (hi - lo) * .65):
                    delta = hi - lo - remaining
                    if delta < 16 or attempts >= 16:
                        continue
                    attempts += 1
                    def shift(value):
                        return (value if value <= lo else value - delta if value >= hi
                                else lo + (value - lo) * remaining / (hi - lo))
                    trial = copy.deepcopy(graph)
                    for node in trial['children']:
                        node[axis] = shift(node[axis])
                    for edge in trial['edges']:
                        for point in points(edge):
                            point[axis] = shift(point[axis])
                        for label in edge.get('labels', []):
                            label[axis] = shift(label[axis])
                    trial[extent] -= delta
                    after = measure(draw(model, metrics, trial)[1])
                    stretch = lambda r: max(r['width'] / r['height'], r['height'] / r['width'])
                    if any(after[k] > before[k] for k in ('bends', 'route_length', 'area')):
                        continue
                    if stretch(after) > max(3.5, stretch(before)):
                        continue
                    # Nonlinear coordinate compression can change diagonal intersections;
                    # recompute the actual geometry instead of assuming topology survives.
                    if safe(model, metrics, graph, trial):
                        graph = trial
                        events.append(dict(axis=axis, lo=lo, hi=hi, removed=delta))
                        changed = True
                        break
                if changed or attempts >= 16:
                    break
            if not changed or attempts >= 16:
                break
    return graph, events
