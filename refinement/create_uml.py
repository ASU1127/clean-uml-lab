"""Optional one-call generation with measured end-label refinement.

Needs the local Clean UML core, Puppeteer Core and Chrome/Chromium/Edge. Existing
complete generation output can also be refined into a separate new directory.
"""
import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def save(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', nargs='?')
    parser.add_argument('--generation-dir')
    parser.add_argument('--core-dir', default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('--requirements')
    parser.add_argument('--root')
    parser.add_argument('--node', default='node')
    parser.add_argument('--browser')
    parser.add_argument('--puppeteer-module', default='puppeteer-core')
    parser.add_argument('--sharp-module')
    parser.add_argument('--elk-module')
    parser.add_argument('--fontconfig')
    parser.add_argument('--no-align', action='store_true')
    parser.add_argument('--no-refine', action='store_true')
    parser.add_argument('--no-cache-distances', action='store_true')
    args = parser.parse_args()
    if bool(args.model) == bool(args.generation_dir):
        parser.error('Supply exactly one model or --generation-dir')
    core = Path(args.core_dir).resolve()
    if Path(args.puppeteer_module).exists():
        args.puppeteer_module = str(Path(args.puppeteer_module).resolve())
    if not (core/'prototype.py').is_file() or not (core/'review_svg.cjs').is_file():
        parser.error('--core-dir must be the matching Clean UML skill directory')
    sys.path[:0] = [str(Path(__file__).resolve().parent), str(core), str(core/'runtime/scripts')]
    from tree_layout import draw
    from drawio_export import export_drawio
    from check_exports import verify
    from audit import audit_svg
    from marker_labels import findings
    from label_metadata import annotated
    from measured_labels import improve
    from render_cache_fast import RenderCache
    from affinity_review import bind, assess
    started = time.perf_counter()
    out = Path(args.output).resolve()
    if out.exists():
        parser.error('Output exists; choose a new directory')
    out.mkdir(parents=True)
    if args.model:
        from prototype import run
        generated = out/'initial'
        setup = argparse.Namespace(model=args.model, output=str(generated), root=args.root,
                                   requirements=args.requirements, node=args.node,
                                   sharp_module=args.sharp_module, elk_module=args.elk_module,
                                   fontconfig=args.fontconfig, vector_only=True)
        if not run(setup):
            save(out/'run.json', dict(status='generation_failed', repairs=0, png_exports=0))
            return 2
    else:
        generated = Path(args.generation_dir).resolve()
    prior = json.loads((generated/'run.json').read_text(encoding='utf-8-sig'))
    if not prior.get('selected_valid'):
        raise ValueError('The input generation must have passed its complete automatic checks')
    selected = (generated/prior['selected']).resolve()
    if not selected.is_relative_to(generated):
        raise ValueError('Selected graph path escapes its generation directory')
    model_path, graph_path, metrics_path = generated/'model.json', selected/'final-layout.json', generated/'baseline/metrics.json'
    sources = {str(p): digest(p) for p in (model_path, graph_path, metrics_path, generated/'diagram.svg', generated/'diagram.drawio')}
    model = json.loads(model_path.read_text(encoding='utf-8-sig'))
    graph = json.loads(graph_path.read_text(encoding='utf-8-sig'))
    metrics = json.loads(metrics_path.read_text(encoding='utf-8-sig'))
    owner = {n['id']: n['id'] for n in graph['children']}
    for node in graph['children']:
        owner.update({p['id']: node['id'] for p in node.get('ports', [])})
    for edge in graph['edges']:
        edge['sources'] = [owner[edge['sources'][0]]]
        edge['targets'] = [owner[edge['targets'][0]]]
    original_svg, original_scene = draw(model, metrics, graph)
    original_svg = annotated(original_svg, graph)
    if audit_svg(original_svg, model)['findings'] or findings(original_svg):
        raise ValueError('Matched generation graph does not pass the native SVG checks')
    verify(generated/'diagram.drawio', model)
    save(out/'model.json', model)
    measurement = out/'measurement-input'
    measurement.mkdir()
    (measurement/'diagram.svg').write_bytes(original_svg)
    browser_calls = 0
    def measure(svg_path, destination):
        nonlocal browser_calls
        browser_calls += 1
        if browser_calls > 2:
            raise ValueError('Browser measurement budget exceeded')
        command = [args.node, str(core/'review_svg.cjs'), str(svg_path), '--model', str(out/'model.json'),
                   '--engine', 'clean', '--output', str(destination), '--python', sys.executable,
                   '--puppeteer-module', args.puppeteer_module]
        if args.browser:
            command += ['--browser', args.browser]
        process = subprocess.run(command, capture_output=True, timeout=90)
        destination.with_suffix('.log').write_bytes(process.stdout+process.stderr)
        if process.returncode not in (0, 2):
            raise RuntimeError('Offline measurement failed: '+process.stderr.decode(errors='replace')[-600:])
        provenance = json.loads((destination/'provenance.json').read_text(encoding='utf-8'))
        if not provenance.get('completed') or not provenance.get('source_unchanged'):
            raise ValueError('Incomplete measurement provenance')
        return json.loads((destination/'scene.json').read_text(encoding='utf-8'))
    measured = measure(measurement/'diagram.svg', out/'baseline-review')
    cache = RenderCache(original_svg, model, measured, cache_distances=not args.no_cache_distances)
    g, svg, scene, trace = improve(model, metrics, graph, cache,
                                 align=not args.no_align, refine=not args.no_refine)
    proposal = measurement/'proposal.svg'
    proposal.write_bytes(svg)
    final_measured = measure(proposal, out/'final-review')
    projected = cache.project(svg)
    if len(final_measured['texts']) != len(projected['texts']):
        raise ValueError('Final fragment count differs from cached typography')
    error = max((abs(a[k]-b[k]) for a, b in zip(final_measured['texts'], projected['texts'])
                 for k in ('x', 'y', 'width', 'height')), default=0)
    baseline_review = assess(bind(original_svg, model, measured))
    review = assess(bind(svg, model, final_measured))
    bounds = json.loads((out/'final-review/review.json').read_text(encoding='utf-8'))
    fallback = error > .03 or bool(bounds['label_label_conflicts'] or bounds['label_classifier_conflicts']) or len(review['proximity_warnings']) > len(baseline_review['proximity_warnings'])
    if fallback:
        g, svg, scene = graph, original_svg, original_scene
        review = baseline_review
    (out/'diagram.svg').write_bytes(svg)
    (out/'diagram.drawio').write_bytes(export_drawio(model, scene, svg))
    verify(out/'diagram.drawio', model)
    save(out/'final-layout.json', g)
    save(out/'refinement.json', trace)
    save(out/'proximity-review.json', review)
    sharp = str(Path(args.sharp_module).resolve()) if args.sharp_module else str(core/'runtime/node_modules/sharp')
    environment = os.environ.copy()
    if args.fontconfig:
        environment['FONTCONFIG_FILE'] = str(Path(args.fontconfig).resolve())
    subprocess.run([args.node, str(core/'runtime/scripts/rasterize.cjs'), sharp,
                    str(out/'diagram.svg'), str(out/'diagram.png')], check=True, capture_output=True,
                   timeout=90, env=environment)
    result = dict(status='needs_review' if review['proximity_warnings'] else 'checks_passed',
                  baseline_proximity_warnings=len(baseline_review['proximity_warnings']),
                  final_proximity_warnings=len(review['proximity_warnings']),
                  fallback_to_original=fallback, cache_projection_error_px=error,
                  browser_measurements=browser_calls, png_exports=1,
                  initial_png_exports=prior.get('png_exports'), layout_calls=prior.get('layout_calls'),
                  label_solves=trace['label_solves'], cache_stats=cache.stats, repairs=0,
                  seconds=time.perf_counter()-started,
                  source_unchanged=all(digest(Path(p)) == h for p, h in sources.items()),
                  human_readability='not_certified',
                  scope='Optional measured native end-label refinement. Complete facts, class placement and paths retained; no crossing or width reduction is claimed. Two offline font measurements; no browser calls or PNGs during label search. With an existing generation input its previous raster work remains separate.')
    save(out/'run.json', result)
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Clean UML</title><style>body{font:16px Arial;margin:20px}img{max-width:100%}</style><a href="diagram.drawio">draw.io</a> · <a href="diagram.svg">SVG</a> · <a href="run.json">检查记录</a><p>标签距离提示：'+str(result['baseline_proximity_warnings'])+' → '+str(result['final_proximity_warnings'])+'。请检查仍有提示的关系。</p><img src="diagram.png" alt="UML 类图">', encoding='utf-8')
    print(json.dumps({'output': str(out), **result}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
