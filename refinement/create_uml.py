"""One-call generation with bounded routes and measured end-label refinement.

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
    parser.add_argument('--no-alignment-score-reuse', action='store_true', help='Recheck unchanged alignment scores')
    parser.add_argument('--no-affected-alignment', action='store_true', help='Try end alignment even on clear label blocks')
    parser.add_argument('--no-font-domains', action='store_true', help='Ablate measured label-position domains entirely')
    parser.add_argument('--no-measured-fragments', action='store_true', help='Use nominal label-block geometry in position domains')
    parser.add_argument('--no-dense-prefix', action='store_true', help='Use sparse endpoint-prefix positions in label domains')
    parser.add_argument('--no-routes', action='store_true', help='Ablate all new routing; retain the label-only workflow')
    parser.add_argument('--no-prefix-routing', action='store_true', help='Ablate path-prefix sampling in the routing solver')
    parser.add_argument('--no-crossing-tradeoff', action='store_true', help='Ablate crossing reduction with bounded detour growth')
    args = parser.parse_args()
    if bool(args.model) == bool(args.generation_dir):
        parser.error('Supply exactly one model or --generation-dir')
    core = Path(args.core_dir).resolve()
    if args.puppeteer_module == 'puppeteer-core':
        local_modules = [Path(__file__).resolve().parent/'node_modules/puppeteer-core',
                         core/'runtime/node_modules/puppeteer-core']
        args.puppeteer_module = next((str(p) for p in local_modules if p.is_dir()), args.puppeteer_module)
    if Path(args.puppeteer_module).exists():
        args.puppeteer_module = str(Path(args.puppeteer_module).resolve())
    if not (core/'prototype.py').is_file() or not (core/'review_svg.cjs').is_file():
        parser.error('--core-dir must be the matching Clean UML skill directory')
    sys.path[:0] = [str(Path(__file__).resolve().parent), str(core/'refinement'), str(core), str(core/'runtime/scripts')]
    from tree_layout import draw
    from drawio_export import export_drawio
    from check_exports import verify
    from audit import audit_svg
    from marker_labels import findings
    from label_metadata import annotated
    from measured_labels import improve
    from render_cache_fast import RenderCache
    from affinity_review import bind, assess
    from measured_labels import score
    from font_domains import improve as improve_font_domains
    from bounded_routes import improve as improve_routes
    from route_metrics import measure as route_metrics
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
        if browser_calls > 4:
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
    def refine_labels(value, typography):
        result_graph, result_svg, result_scene, result_trace = improve(
            model, metrics, value, typography, align=not args.no_align, refine=not args.no_refine,
            reuse_alignment_score=not args.no_alignment_score_reuse,
            affected_alignment_only=not args.no_affected_alignment)
        result_trace['pre_font_score'] = score(typography.review(result_svg))
        if not args.no_refine and not args.no_font_domains:
            result_graph, result_svg, font_trace = improve_font_domains(
                model, result_graph, result_svg, typography,
                measured_domains=not args.no_measured_fragments,
                dense_prefix=not args.no_dense_prefix)
            _, result_scene = draw(model, metrics, result_graph)
            result_trace['font_domains'] = font_trace
            result_trace['label_solves'] += bool(font_trace['domains'])
            result_trace['after'] = score(typography.review(result_svg))
        else:
            result_trace['font_domains'] = dict(enabled=False)
        return result_graph, result_svg, result_scene, result_trace

    g, svg, scene, trace = refine_labels(graph, cache)
    old_g, old_svg, old_scene, old_trace, old_cache = g, svg, scene, trace, cache
    (measurement/'original-refined.svg').write_bytes(old_svg)
    save(out/'original-refinement.json', old_trace)
    original_refined_review = cache.review(svg)
    routing = dict(enabled=not args.no_routes, changed=False, accepted=False,
                   label_solver_calls=0, new_layout_calls=0)
    route_refinement = None
    label_solves = trace['label_solves']
    if not args.no_routes:
        routed, routing = improve_routes(model, graph,
                                        tradeoff=not args.no_crossing_tradeoff,
                                        prefix=not args.no_prefix_routing)
        routing['enabled'] = True
        if routing['changed']:
            route_svg, route_scene = draw(model, metrics, routed)
            route_svg = annotated(route_svg, routed)
            if audit_svg(route_svg, model)['findings'] or findings(route_svg):
                raise ValueError('Bounded route proposal failed complete native geometry checks')
            route_file = measurement/'routed.svg'
            route_file.write_bytes(route_svg)
            route_measured = measure(route_file, out/'routed-review')
            route_cache = RenderCache(route_svg, model, route_measured,
                                      cache_distances=not args.no_cache_distances)
            rg, rsvg, rscene, route_refinement = refine_labels(routed, route_cache)
            label_solves += route_refinement['label_solves']
            proposed_review = route_cache.review(rsvg)
            # Typography caches are tied to separately measured fixed routes.
            # A geometric improvement cannot license worse measured ambiguity.
            routing['original_refined_score'] = score(original_refined_review)
            routing['legacy_original_refined_score'] = old_trace['pre_font_score']
            routing['routed_refined_score'] = score(proposed_review)
            # Preserve routes admitted by the existing workflow. Better labels
            # on its unselected original route must not remove that geometric
            # improvement. New routes still cannot worsen the legacy control.
            routing['accepted'] = score(proposed_review) <= tuple(old_trace['pre_font_score'])
            if routing['accepted']:
                g, svg, scene, trace, cache = rg, rsvg, rscene, route_refinement, route_cache
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
    fallback = error > .03 or bool(bounds['label_label_conflicts'] or bounds['label_classifier_conflicts']) or score(review) > score(cache.review(svg))
    selected_review = 'final-review'
    fallback_to_original = False
    if fallback:
        if routing.get('accepted'):
            fallback_file = measurement/'fallback.svg'
            fallback_file.write_bytes(old_svg)
            fallback_measured = measure(fallback_file, out/'fallback-review')
            fallback_bounds = json.loads((out/'fallback-review/review.json').read_text(encoding='utf-8'))
            fallback_projected = old_cache.project(old_svg)
            fallback_error = max((abs(a[k]-b[k]) for a, b in zip(fallback_measured['texts'], fallback_projected['texts'])
                                  for k in ('x', 'y', 'width', 'height')), default=0)
            fallback_review = assess(bind(old_svg, model, fallback_measured))
            if fallback_error <= .03 and not (fallback_bounds['label_label_conflicts'] or fallback_bounds['label_classifier_conflicts']) and score(fallback_review) <= score(baseline_review):
                g, svg, scene, trace, cache = old_g, old_svg, old_scene, old_trace, old_cache
                review = fallback_review
                selected_review = 'fallback-review'
                routing['accepted'] = False
            else:
                fallback_to_original = True
        else:
            fallback_to_original = True
        if fallback_to_original:
            g, svg, scene = graph, original_svg, original_scene
            review = baseline_review
            selected_review = 'baseline-review'
            routing['accepted'] = False
    (out/'diagram.svg').write_bytes(svg)
    (out/'diagram.drawio').write_bytes(export_drawio(model, scene, svg))
    verify(out/'diagram.drawio', model)
    save(out/'final-layout.json', g)
    save(out/'refinement.json', trace)
    save(out/'routing.json', routing)
    if route_refinement is not None:
        save(out/'routed-refinement.json', route_refinement)
    save(out/'proximity-review.json', review)
    geometry = route_metrics(scene)
    save(out/'route-metrics.json', geometry)
    sharp = str(Path(args.sharp_module).resolve()) if args.sharp_module else str(core/'runtime/node_modules/sharp')
    environment = os.environ.copy()
    if args.fontconfig:
        environment['FONTCONFIG_FILE'] = str(Path(args.fontconfig).resolve())
    subprocess.run([args.node, str(core/'runtime/scripts/rasterize.cjs'), sharp,
                    str(out/'diagram.svg'), str(out/'diagram.png')], check=True, capture_output=True,
                   timeout=90, env=environment)
    result = dict(status='needs_review' if review['proximity_warnings'] or geometry['proper_crossings'] or geometry['other_contacts'] else 'checks_passed',
                  baseline_proximity_warnings=len(baseline_review['proximity_warnings']),
                  final_proximity_warnings=len(review['proximity_warnings']),
                  fallback_to_original=fallback_to_original, fallback_from_route_proposal=fallback,
                  selected_review=selected_review, cache_projection_error_px=error,
                  browser_measurements=browser_calls, png_exports=1,
                  initial_png_exports=prior.get('png_exports'), layout_calls=prior.get('layout_calls'),
                  new_layout_calls=prior.get('layout_calls', 0) if args.model else 0,
                  label_solves=label_solves, route_label_solves=routing['label_solver_calls'],
                  alignment_score_reuse=not args.no_alignment_score_reuse,
                  affected_alignment_only=not args.no_affected_alignment,
                  alignment_review_calls=sum(t.get('alignment_review_calls', 0) for t in [old_trace] + ([route_refinement] if route_refinement is not None else [])),
                  clear_alignment_groups_skipped=sum(t.get('clear_alignment_groups_skipped', 0) for t in [old_trace] + ([route_refinement] if route_refinement is not None else [])),
                  font_domains_enabled=not args.no_refine and not args.no_font_domains,
                  measured_fragments=not args.no_measured_fragments,
                  dense_prefix=not args.no_dense_prefix,
                  font_domain_search_states=sum(t.get('font_domains', {}).get('search_states', 0)
                      for t in [old_trace] + ([route_refinement] if route_refinement is not None else [])),
                  font_domain_evaluated_positions=sum(t.get('font_domains', {}).get('evaluated_positions', 0)
                      for t in [old_trace] + ([route_refinement] if route_refinement is not None else [])),
                  routes_changed=routing['changed'], routes_accepted=routing.get('accepted', False),
                  original_crossings=route_metrics(original_scene)['proper_crossings'],
                  final_crossings=geometry['proper_crossings'],
                  original_bends=route_metrics(original_scene)['bends'], final_bends=geometry['bends'],
                  cache_stats=cache.stats, repairs=0,
                  seconds=time.perf_counter()-started,
                  source_unchanged=all(digest(Path(p)) == h for p, h in sources.items()),
                  human_readability='not_certified',
                  scope='Bounded fixed-class routing with independently switchable crossing tradeoff, prefix labels and measured label domains. Original and routed typography are measured separately; cached translations never cross a geometry change. Admission uses the legacy original-route label score; new label domains cannot revoke its admitted route. Final measurement must match the selected cached result. Two or three offline font measurements normally, at most four including fallback. Complete facts and class frames retained; no width or human-preference claim. One final PNG, no browser/PNG calls during searches. Prior work of a supplied generation remains separate.')
    save(out/'run.json', result)
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Clean UML</title><style>body{font:16px Arial;margin:20px}img{max-width:100%}</style><a href="diagram.drawio">draw.io</a> · <a href="diagram.svg">SVG</a> · <a href="run.json">检查记录</a><p>交叉：'+str(result['final_crossings'])+'；标签距离提示：'+str(result['final_proximity_warnings'])+'。请检查仍有提示的关系。</p><img src="diagram.png" alt="UML 类图">', encoding='utf-8')
    print(json.dumps({'output': str(out), **result}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
