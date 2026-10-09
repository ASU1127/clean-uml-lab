"""End-line alignment and label refinement admitted using measured text bounds."""
import copy
import xml.etree.ElementTree as ET

from affinity_review import assess
from targeted_labels import solve
from label_metadata import annotated
from tree_layout import draw
from audit import audit_svg
from marker_labels import findings as marker_findings
from notation import end_lines

NS = '{http://www.w3.org/2000/svg}'
LIMITS = {'max_alignment_groups': 120, 'max_prefix_solves': 1,
          'max_target_solves': 12, 'solver_limit': 10000}


def score(report):
    return (len(report['unmapped_fragments']), len(report['proximity_warnings']),
            len({w['relation'] for w in report['proximity_warnings']}))


def valid(svg, model):
    return not audit_svg(svg, model)['findings'] and not marker_findings(svg)


def end_alignment(svg, model, cache):
    """Right-align short multiplicities on the line-facing side of a block.

    Try only the two in-block horizontal alignments, using cached real fragment
    bounds for admission. Role, multiplicity and endpoint remain unchanged.
    """
    root = ET.fromstring(svg)
    accepted = []
    groups = 0
    for index, relation in enumerate(model['relations']):
        group = root.find(f'.//*[@id="edge_{index}"]')
        remaining = list(group.findall(NS+'text'))
        for side in ('source', 'target', 'center'):
            expected = ([relation['label']] if 'label' in relation else []) if side == 'center' else end_lines(relation, side)
            texts = remaining[:len(expected)]
            remaining = remaining[len(expected):]
            assert [t.text for t in texts] == expected
            if side == 'center' or len(texts) < 2:
                continue
            groups += 1
            if groups > LIMITS['max_alignment_groups']:
                break
            original = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            old = cache.review(original)
            left = min(float(t.get('x')) for t in texts)
            right = max(float(t.get('x'))+float(t.get('textLength')) for t in texts)
            coordinates = [t.get('x') for t in texts]
            # Existing left alignment is the control. Keep this ordinary native
            # grouping; move only the shorter lines inside its existing width.
            for t in texts:
                t.set('x', str(right-float(t.get('textLength'))))
                t.set('data-label-align', 'right')
            trial = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            new = cache.review(trial)
            if score(new) < score(old) and valid(trial, model):
                accepted.append(dict(relation=index, end=side,
                                     before=score(old), after=score(new)))
            else:
                for t, x in zip(texts, coordinates):
                    t.set('x', x)
                    t.attrib.pop('data-label-align', None)
        assert not remaining
    return ET.tostring(root, encoding='utf-8', xml_declaration=True), accepted


def improve(model, metrics, graph, cache, align=False, refine=False):
    g = copy.deepcopy(graph)
    trace = dict(limits=LIMITS, align=align, refine=refine, label_solves=0,
                 alignment_events=[], refine_events=[], actual_browser_calls_inside_search=0)
    def render(trial):
        svg, scene = draw(model, metrics, trial)
        svg = annotated(svg, trial)
        if align:
            svg, alignment_events = end_alignment(svg, model, cache)
        else:
            alignment_events = []
        return svg, scene, alignment_events
    svg, scene, events = render(g)
    trace['alignment_events'] += events
    initial = cache.review(annotated(draw(model, metrics, graph)[0], graph))
    if refine:
        candidate = copy.deepcopy(g)
        trace['label_solves'] += 1
        note = {}
        solved = solve(candidate, model=model, preserve_edges={e['id'] for e in g['edges']}, traverse=True, trace=note)
        if solved:
            next_svg, next_scene, alignment_events = render(candidate)
            old, new = cache.review(svg), cache.review(next_svg)
            accepted = score(new) < score(old) and valid(next_svg, model)
        else:
            accepted = False
        if accepted:
            g, svg, scene = candidate, next_svg, next_scene
            trace['alignment_events'] += alignment_events
        trace['refine_events'].append(dict(kind='prefix', solved=solved, accepted=accepted, solver=note))
        review = cache.review(svg)
        targets = []
        for warning in sorted(review['proximity_warnings'], key=lambda w: (w['margin'], w['text_index'])):
            if warning['label_id'] and warning['label_id'] not in targets:
                targets.append(warning['label_id'])
        for target in targets[:LIMITS['max_target_solves']]:
            old = cache.review(svg)
            if not any(w['label_id'] == target for w in old['proximity_warnings']):
                continue
            candidate = copy.deepcopy(g)
            trace['label_solves'] += 1
            assert trace['label_solves'] <= 1+LIMITS['max_target_solves']
            note = {}
            solved = solve(candidate, model=model, preserve_edges={e['id'] for e in g['edges']},
                           traverse=True, affinity_guard=True, affinity_labels={target}, trace=note)
            if solved:
                next_svg, next_scene, alignment_events = render(candidate)
                new = cache.review(next_svg)
                accepted = score(new) < score(old) and valid(next_svg, model)
            else:
                accepted = False
            if accepted:
                g, svg, scene = candidate, next_svg, next_scene
                trace['alignment_events'] += alignment_events
            trace['refine_events'].append(dict(kind='target', label=target, solved=solved,
                                               accepted=accepted, solver=note))
    final = cache.review(svg)
    assert score(final) <= score(initial)
    assert valid(svg, model)
    trace.update(before=score(initial), after=score(final), new_layout_calls=0)
    return g, svg, scene, trace
