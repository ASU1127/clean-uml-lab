"""Bounded crossing-first tradeoff and independent endpoint-prefix ablation.

Class frames and complete semantic model stay fixed. Crossings are never traded
for node penetration, shared tracks or contacts. Geometry is diagnostic only.
"""
import copy
import math

from route_candidates import router
from fan_layout import points
from qualifier_layout import edge_geometry
from cached_route_metrics import CachedMeasure
from joint_labels import solve as legacy_solve
from path_labels import solve as prefix_solve

LIMITS = dict(max_edges=100, max_route_options_per_edge=192,
              max_label_solves_per_edge=12, solver_limit=10000, passes=1,
              total_extra_bends=2, total_length_factor=1.03,
              longest_route_factor=1.05, individual_length_factor=1.35,
              individual_extra_length=80)


def visible_scene(model, graph):
    edges = []
    for edge in graph['edges']:
        ps = [(p['x'], p['y']) for p in points(edge)]
        if edge.get('qualifier_sizes'):
            ps, _ = edge_geometry(graph, edge, model)
        edges.append(dict(index=int(edge['id'].split('_')[1]), points=ps))
    return dict(width=graph['width'], height=graph['height'], edges=edges)


def improve(model, graph, tradeoff=False, prefix=False):
    g = copy.deepcopy(graph)
    proposals = router(g['children'], g['edges'])
    cached = CachedMeasure()

    def geometry(value):
        scene = visible_scene(model, value)
        result = cached(scene)
        result['longest_route'] = max((sum(math.dist(a, b) for a, b in
                                             zip(e['points'], e['points'][1:]))
                                       for e in scene['edges']), default=0)
        return result

    before = geometry(g)
    trace = dict(limits=LIMITS, tradeoff=tradeoff, prefix=prefix,
                 events=[], label_solver_calls=0, new_layout_calls=0,
                 before=before, browser_calls_inside_search=0)
    priorities = dict(composition=0, aggregation=1, association=2,
                      generalization=3, realization=3, dependency=4)
    crossing_edges = {i for x in before['crossing_locations'] for i in x['edges']}
    def order_key(e):
        index = int(e['id'].split('_')[1])
        return ((0 if index in crossing_edges else 1) if tradeoff else 0,
                priorities[model['relations'][index]['kind']],
                -len(points(e)), e['id'])
    order = [e['id'] for e in sorted(g['edges'], key=order_key)]
    for eid in order[:LIMITS['max_edges']]:
        edge = next(e for e in g['edges'] if e['id'] == eid)
        current = geometry(g)
        edge_length = sum(math.dist((a['x'], a['y']), (b['x'], b['y']))
                          for a, b in zip(points(edge), points(edge)[1:]))
        ranked = []
        rejected = dict(crossings=0, contacts=0, shared=0, budget=0,
                        no_improvement=0, qualifier_geometry=0)
        for ps in proposals(edge):
            trial = copy.deepcopy(g)
            moved = next(e for e in trial['edges'] if e['id'] == eid)
            moved['sections'] = [dict(startPoint=ps[0], bendPoints=ps[1:-1], endPoint=ps[-1])]
            try:
                score = geometry(trial)
            except ValueError:
                rejected['qualifier_geometry'] += 1
                continue
            if score['proper_crossings'] > current['proper_crossings']:
                rejected['crossings'] += 1
                continue
            if score['other_contacts'] > current['other_contacts']:
                rejected['contacts'] += 1
                continue
            if score['shared_track_length'] > current['shared_track_length'] + .001:
                rejected['shared'] += 1
                continue
            removing_crossing = tradeoff and score['proper_crossings'] < current['proper_crossings']
            if removing_crossing:
                proposal_length = sum(math.dist((a['x'], a['y']), (b['x'], b['y']))
                                      for a, b in zip(ps, ps[1:]))
                admissible = (score['bends'] <= before['bends'] + LIMITS['total_extra_bends'] and
                              score['route_length'] <= before['route_length'] * LIMITS['total_length_factor'] and
                              score['longest_route'] <= before['longest_route'] * LIMITS['longest_route_factor'] + 1e-6 and
                              proposal_length <= max(edge_length * LIMITS['individual_length_factor'],
                                                     edge_length + LIMITS['individual_extra_length']))
                if not admissible:
                    rejected['budget'] += 1
                    continue
            else:
                if score['bends'] > current['bends'] or score['route_length'] > current['route_length']:
                    rejected['budget'] += 1
                    continue
                if (score['bends'], score['route_length']) >= (current['bends'], current['route_length']):
                    rejected['no_improvement'] += 1
                    continue
            key = ((score['proper_crossings'], score['bends'], score['route_length'])
                   if tradeoff else (score['bends'], score['route_length']))
            ranked.append((key, trial, score))
        ranked.sort(key=lambda x: x[0])
        accepted = False
        attempts = []
        for _, trial, score in ranked[:LIMITS['max_label_solves_per_edge']]:
            trace['label_solver_calls'] += 1
            preserved = {e['id'] for e in g['edges'] if e['id'] != eid}
            note = {}
            if prefix:
                solved = prefix_solve(trial, model=model, preserve_edges=preserved,
                                      traverse=True, affinity_guard=False,
                                      limit=LIMITS['solver_limit'], trace=note)
            else:
                solved = legacy_solve(trial, model=model, preserve_edges=preserved,
                                      limit=LIMITS['solver_limit'])
            attempts.append(dict(solved=solved, crossings=score['proper_crossings'],
                                 bends=score['bends'], length=score['route_length'], solver=note))
            if solved:
                g = trial
                accepted = True
                break
        trace['events'].append(dict(edge=eid, feasible_geometry_options=len(ranked),
                                    rejected=rejected, attempts=attempts, accepted=accepted))
    trace.update(after=geometry(g), changed=any(e['accepted'] for e in trace['events']),
                 route_cache_hits=cached.hits, route_cache_misses=cached.misses)
    assert g['children'] == graph['children']
    return g, trace
