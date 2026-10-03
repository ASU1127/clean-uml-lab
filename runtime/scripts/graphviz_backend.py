"""Experimental bounded Graphviz layout. No cached example coordinates required."""
import json
import math
import subprocess
from pathlib import Path
from tree_layout import tree_graph
from joint_labels import solve


def quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def _pass(model, metrics, out, dot, root, reference=None):
    out.mkdir(parents=True, exist_ok=False)
    graph = tree_graph(model, metrics, routing='ORTHOGONAL', root=root, sized=True)
    owners = {n['id']: n['id'] for n in graph['children']}
    for node in graph['children']:
        owners.update({p['id']: node['id'] for p in node.get('ports', [])})
    # First pass determines branch order. Later passes reserve endpoint-label space.
    spacing = 'nodesep=0.65,ranksep=0.85' if reference is None else 'nodesep=0.91,ranksep=2.4'
    lines = ['digraph G {', f'graph [rankdir=TB,splines=polyline,{spacing},pad=0];',
             'node [shape=box,fixedsize=true,label="",margin=0];',
             'edge [dir=none,fontname="Arial",fontsize=16,labelfontname="Arial",labelfontsize=16];']
    slots = {n['id']: {'in': [], 'out': []} for n in graph['children']}
    for edge in graph['edges']:
        a, b = owners[edge['sources'][0]], owners[edge['targets'][0]]
        if a != b:
            slots[a]['out'].append((edge['id'], b))
            slots[b]['in'].append((edge['id'], a))
    ports = {}
    for node in graph['children']:
        width, height = node['width'], node['height']
        attrs = {'width': width / 72, 'height': height / 72}
        if reference is not None:
            rows = {side: sorted(edges, key=lambda p: (reference[p[1]], p[1], p[0]))
                    for side, edges in slots[node['id']].items()}
            count = max(1, *(len(edges) for edges in rows.values()))
            fields = []
            for side in ('in', 'out'):
                cells = {}
                for i, (eid, _) in enumerate(rows[side]):
                    slot = min(count - 1, int((i + .5) * count / len(rows[side])))
                    name = f'{side}{i}'
                    cells[slot] = name
                    ports[eid, side] = name + (':n' if side == 'in' else ':s')
                fields.append('{' + '|'.join('<' + cells[j] + '> ' if j in cells else ' ' for j in range(count)) + '}')
            attrs.update(shape='record', fontsize=1, width=math.ceil(width)/72,
                         height=math.ceil(height)/72, label='{' + fields[0] + '| |' + fields[1] + '}')
        lines.append(quote(node['id']) + ' [' + ','.join(k + '=' + quote(v) for k, v in attrs.items()) + '];')
    for edge in graph['edges']:
        attrs = {'id': edge['id']}
        if (edge['id'], 'out') in ports:
            attrs.update(tailport=ports[edge['id'], 'out'], headport=ports[edge['id'], 'in'])
        for label in edge['labels']:
            side = label['id'].rsplit('_', 1)[-1]
            tail = (side == 'source') != edge.get('semanticReverse', False)
            attrs['label' if side == 'center' else 'taillabel' if tail else 'headlabel'] = '\n'.join(label['lines'])
        a, b = owners[edge['sources'][0]], owners[edge['targets'][0]]
        lines.append(quote(a) + ' -> ' + quote(b) + ' [' + ','.join(k + '=' + quote(v) for k, v in attrs.items()) + '];')
    lines.append('}')
    (out / 'input.dot').write_text('\n'.join(lines), encoding='utf-8')
    process = subprocess.run([str(dot), '-Tjson0', str(out / 'input.dot'), '-o', str(out / 'raw.json')],
                             capture_output=True, timeout=30)
    (out / 'dot.log').write_bytes(process.stdout + process.stderr)
    process.check_returncode()
    raw = json.loads((out / 'raw.json').read_text(encoding='utf-8'))
    xmin, ymin, xmax, ymax = map(float, raw['bb'].split(','))
    graph.update(width=xmax-xmin+48, height=ymax-ymin+48)

    def xy(value):
        x, y = map(float, value.split(','))
        return {'x': x-xmin+24, 'y': ymax-y+24}

    nodes = {n['id']: n for n in graph['children']}
    for obj in raw.get('objects', []):
        node = nodes[obj['name']]
        point = xy(obj['pos'])
        width, height = float(obj['width'])*72, float(obj['height'])*72
        node.update(width=width, height=height, x=point['x']-width/2, y=point['y']-height/2)
        node.pop('ports', None)
    edges = {e['id']: e for e in graph['edges']}
    for obj in raw.get('edges', []):
        edge = edges[obj['id']]
        a, b = owners[edge['sources'][0]], owners[edge['targets'][0]]
        edge.update(sources=[a], targets=[b])
        points = [xy(token) for token in obj['pos'].split() if len(token.split(',')) == 2]
        if a == b:
            node = nodes[a]
            x, y, h = node['x']+node['width'], node['y'], node['height']
            # Respect the layout engine's reserved loop envelope. Keep label legs
            # near the top/bottom corners rather than crossing adjacent nodes.
            extent = max(p['x'] for p in points)
            span = max(24, extent-x)
            points = [{'x': x, 'y': y+2}, {'x': x+span, 'y': y+2},
                      {'x': x+span, 'y': y+h-2}, {'x': x, 'y': y+h-2}]
        else:
            clean = []
            for point in points:
                if clean and math.hypot(point['x']-clean[-1]['x'], point['y']-clean[-1]['y']) < .1:
                    continue
                clean.append(point)
                while len(clean) > 2:
                    u, v, w = clean[-3:]
                    dx, dy = w['x']-u['x'], w['y']-u['y']
                    length = math.hypot(dx, dy)
                    if length and abs((v['x']-u['x'])*dy-(v['y']-u['y'])*dx)/length < .2:
                        clean.pop(-2)
                    else:
                        break
            points = clean
        if len(points) < 2:
            raise ValueError('Graphviz returned a missing or degenerate route')
        edge['sections'] = [{'startPoint': points[0], 'bendPoints': points[1:-1], 'endPoint': points[-1]}]
        for label in edge['labels']:
            side = label['id'].rsplit('_', 1)[-1]
            tail = (side == 'source') != edge.get('semanticReverse', False)
            point = xy(obj['lp' if side == 'center' else 'tail_lp' if tail else 'head_lp'])
            label.update(x=point['x']-label['width']/2, y=point['y']-label['height']/2)
    return graph


def layout(model, metrics, output, dot='dot', root=None, passes=3):
    """Return graph and trace; callers must audit before accepting the result.

    The fixed budget is 2 or 3 Graphviz invocations, never a retry-until-pass loop.
    No PNG or visual-model call occurs here. Input model order should be canonical.
    """
    if passes not in (2, 3):
        raise ValueError('Graphviz experiment supports exactly 2 or 3 passes')
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    version = subprocess.run([str(dot), '-V'], capture_output=True, timeout=10)
    version.check_returncode()
    reference = None
    for i in range(passes):
        graph = _pass(model, metrics, out / f'pass-{i+1}', dot, root, reference)
        reference = {n['id']: n['x']+n['width']/2 for n in graph['children']}
    solved = solve(graph, limit=10000, model=model)
    label_calls = 1
    if not solved:
        # A root self-loop can need labels above the original canvas. Give the
        # solver one bounded margin-only fallback; no node/edge relative moves.
        import copy
        trial = copy.deepcopy(graph)
        margin = max((max(l['width'], l['height']) for e in graph['edges'] for l in e['labels']), default=0)+16
        items = list(trial['children'])
        for e in trial['edges']:
            s = e['sections'][0]
            items += [s['startPoint'], *s.get('bendPoints', []), s['endPoint'], *e['labels']]
        for item in items:
            item['x'] += margin
            item['y'] += margin
        trial['width'] += 2*margin
        trial['height'] += 2*margin
        label_calls += 1
        if solve(trial, limit=10000, model=model):
            # Crop unused margin after placement, keeping 24 pixels around all
            # boxes and routes. Translation preserves crossings and hierarchy.
            left = min(i['x'] for i in items)-24
            top = min(i['y'] for i in items)-24
            right = max(i['x']+i.get('width', 0) for i in items)+24
            bottom = max(i['y']+i.get('height', 0) for i in items)+24
            for item in items:
                item['x'] -= left
                item['y'] -= top
            trial.update(width=right-left, height=bottom-top)
            graph, solved = trial, True
    trace = {'backend': 'graphviz-experimental', 'layout_calls': passes,
             'graphviz_version': (version.stdout+version.stderr).decode(errors='replace').strip(),
             'label_solved': solved, 'cached_example_coordinates': False,
             'label_solver_calls': label_calls,
             'spacing_points': {'horizontal': .91*72, 'vertical': 2.4*72}}
    (out/'trace.json').write_text(json.dumps(trace, indent=2), encoding='utf-8')
    return graph, trace


def main():
    import argparse
    import hashlib
    import os
    import time
    from clean_uml import canonical, verify_requirements
    from lane_layout import measurements
    from tree_layout import draw
    from drawio_export import export_drawio
    from audit import audit_svg
    from marker_labels import findings
    from route_metrics import measure
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model')
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('--dot', default='dot')
    parser.add_argument('--passes', type=int, choices=[2, 3], default=3)
    parser.add_argument('--root')
    parser.add_argument('--requirements')
    parser.add_argument('--node', default='node')
    parser.add_argument('--sharp-module', default='sharp')
    parser.add_argument('--fontconfig')
    args = parser.parse_args()
    start = time.perf_counter()
    source = Path(args.model).read_bytes()
    model = canonical(json.loads(source.decode('utf-8-sig')))
    requirements = verify_requirements(model, args.requirements)
    if args.root and args.root not in {n['id'] for n in model['nodes']}:
        parser.error('Unknown root ID')
    scripts = Path(__file__).resolve().parent
    env = os.environ.copy()
    if args.fontconfig:
        env['FONTCONFIG_FILE'] = str(Path(args.fontconfig).resolve())
    # Resolve dependencies before creating output, using the skill's directory.
    resolution = subprocess.run([args.node, '-e',
        'process.stdout.write(require.resolve(process.argv[1],{paths:[process.argv[2]]}))',
        args.sharp_module, str(scripts.parent)], capture_output=True, text=True, timeout=15)
    resolution.check_returncode()
    sharp = resolution.stdout.strip()
    subprocess.run([args.dot, '-V'], capture_output=True, check=True, timeout=10)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)

    def save(name, data):
        (out/name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    (out/'original-model.json').write_bytes(source)
    save('model.json', model)
    save('requirements-check.json', requirements)
    if args.requirements:
        (out/'requirements.json').write_bytes(Path(args.requirements).read_bytes())
    save('measure-request.json', measurements(model))
    subprocess.run([args.node, str(scripts/'measure.cjs'), sharp, str(out/'measure-request.json'),
                    str(out/'metrics.json')], env=env, check=True, capture_output=True, timeout=60)
    metrics = json.loads((out/'metrics.json').read_text(encoding='utf-8'))
    graph, trace = layout(model, metrics, out/'graphviz', args.dot, args.root, args.passes)
    svg, scene = draw(model, metrics, graph)
    audit, markers, routes = audit_svg(svg, model), findings(svg), measure(scene)
    hierarchy = all(scene['nodes'][r['target']]['y'] < scene['nodes'][r['source']]['y']
                    for r in model['relations'] if r['kind'] in ('generalization', 'realization'))
    review = (not trace['label_solved'] or not hierarchy or audit['findings'] or markers or
              any(routes[k] for k in ('proper_crossings', 'other_contacts', 'shared_track_length')))
    (out/'diagram.svg').write_bytes(svg)
    (out/'diagram.drawio').write_bytes(export_drawio(model, scene, svg))
    save('final-layout.json', graph)
    save('layout.json', scene)
    save('visual-audit.json', audit)
    save('marker-label-audit.json', {'after': markers})
    save('route-metrics.json', routes)
    subprocess.run([args.node, str(scripts/'rasterize.cjs'), sharp, str(out/'diagram.svg'),
                    str(out/'diagram.png')], env=env, check=True, capture_output=True, timeout=60)
    result = dict(trace, status='needs_review' if review else 'checks_passed',
                  human_readability='not_certified', inheritance_above=hierarchy,
                  png_exports=1, visual_model_calls=0, seconds=time.perf_counter()-start,
                  input_sha256=hashlib.sha256(source).hexdigest(), requirements=requirements,
                  limitations=['Experimental class-diagram backend',
                               'Known crossing regressions and self-loop label failures',
                               'Geometry checks do not certify business facts or aesthetics'])
    save('run.json', result)
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Clean UML experiment</title>'
        '<style>body{font:16px system-ui;margin:24px}img{max-width:100%}</style>'
        '<p>Graphviz 实验后端 · '+result['status']+' · <a href="diagram.drawio">draw.io</a> · '
        '<a href="diagram.svg">SVG</a> · <a href="run.json">运行记录</a></p>'
        '<img src="diagram.png" alt="UML class diagram">', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
