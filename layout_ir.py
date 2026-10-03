"""Coordinate-free layout proposals. Regions never alter UML facts."""
import argparse
import copy
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def identifier(prefix, value):
    return prefix + hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()[:16]


def build(model):
    # Reuse the frozen semantic validator, not its layout or rendered output.
    import sys
    home = Path(__file__).resolve().parent
    scripts = home/'runtime/scripts' if (home/'runtime').exists() else home.parent/'clean-uml-next/scripts'
    if str(scripts) not in sys.path: sys.path.insert(0, str(scripts))
    from compile_model import compile_model
    from type_bindings import normalize_model
    original = model
    model, binding_trace = normalize_model(model)
    compile_model(model,validate_only=True)
    facts = copy.deepcopy(model)
    facts['nodes'].sort(key=lambda n: n['id'])
    facts['relations'].sort(key=canonical)
    occurrences = defaultdict(int)
    relations = []
    for relation in facts['relations']:
        key = canonical(relation)
        ordinal = occurrences[key]
        occurrences[key] += 1
        relations.append({'id': identifier('relation_', [relation, ordinal]), 'fact': relation})
    candidates = []
    for family, kinds in [('inheritance', {'generalization', 'realization'}), ('composition', {'composition'})]:
        children = defaultdict(set)
        parents = defaultdict(set)
        evidence = []
        for relation in relations:
            r = relation['fact']
            if r['kind'] not in kinds: continue
            parent, child = (r['target'], r['source']) if family == 'inheritance' else (r['source'], r['target'])
            if parent == child: continue
            children[parent].add(child)
            parents[child].add(parent)
            evidence.append((parent, child, relation['id']))
        roots = sorted(set(children)-set(parents))
        # Cyclic structures still produce explicit proposals, never disappear.
        reached = set()
        for root in roots + sorted(set(children)):
            if root not in roots and root in reached: continue
            members = {root}
            queue = [root]
            for node in queue:
                for child in sorted(children[node]-members):
                    members.add(child)
                    queue.append(child)
            reached.update(members)
            if len(members) < 2: continue
            reason = {'kind': family, 'root': root, 'relations': sorted(eid for a,b,eid in evidence if a in members and b in members)}
            candidates.append({'id': identifier('candidate_', [family, root, sorted(members)]), 'members': sorted(members), 'reason': reason})
    candidates.sort(key=lambda c: (c['reason']['kind'] != 'inheritance', -len(c['members']), c['id']))
    assigned = set()
    regions = []
    decisions = []
    # One declared baseline policy. Overlapping proposals remain available to
    # future composition search; they are not semantic containment constraints.
    for candidate in candidates:
        available = sorted(set(candidate['members'])-assigned)
        removed = sorted(set(candidate['members']) & assigned)
        selected = len(available) >= 2
        decisions.append({'candidate': candidate['id'], 'selected': selected, 'excluded_already_assigned': removed, 'remaining_members': available})
        if selected:
            regions.append({'id': identifier('region_', available), 'members': available, 'proposal': candidate['id'], 'reason': candidate['reason']['kind']})
            assigned.update(available)
    for n in facts['nodes']:
        if n['id'] not in assigned:
            regions.append({'id': identifier('region_', [n['id']]), 'members': [n['id']], 'proposal': None, 'reason': 'unassigned_singleton'})
    regions.sort(key=lambda r: r['id'])
    owners = {n:r['id'] for r in regions for n in r['members']}
    connections = []
    for relation in relations:
        r = relation['fact']
        connections.append({'relation': relation['id'], 'source_node': r['source'], 'target_node': r['target'], 'source_region': owners[r['source']], 'target_region': owners[r['target']], 'internal': owners[r['source']] == owners[r['target']]})
    for region in regions:
        region['internal_relations'] = [c['relation'] for c in connections if c['internal'] and c['source_region'] == region['id']]
        # Semantic terminals, deliberately without a geometric face or coordinate.
        region['boundary_terminals'] = [
            {'relation': c['relation'], 'side': side, 'node': c[side+'_node'], 'peer_region': c[('target' if side == 'source' else 'source')+'_region']}
            for c in connections if not c['internal']
            for side in ('source','target') if c[side+'_region'] == region['id']
        ]
    constraints = [{'type': 'above', 'upper': r['fact']['target'], 'lower': r['fact']['source'], 'relation': r['id'], 'basis': 'declared_reading_policy'} for r in relations if r['fact']['kind'] in ('generalization','realization')]
    result = {'version': 1, 'facts': facts, 'relations': relations, 'region_candidates': candidates, 'regions': regions, 'membership_decisions': decisions, 'connections': connections, 'constraints': constraints, 'policy': 'inheritance-first, maximal remaining composition, singleton remainder', 'diagnostics': {'node_count': len(facts['nodes']), 'region_count': len(regions), 'largest_region': max(len(r['members']) for r in regions), 'cross_region_relations': sum(not c['internal'] for c in connections), 'overlapping_candidates': sum(bool(d['excluded_already_assigned']) for d in decisions)}, 'claim': 'Structural proposal only; no geometry or readability certification'}
    if 'imports' in original: result['input_bindings'] = binding_trace
    if 'package' in original or any('package' in n or 'visibility' in n for n in original['nodes']):
        from notation import namespace,node_title
        result['input_namespaces'] = dict(model_package=original.get('package'),classifiers=[dict(id=n['id'],declared_package=n.get('package'),effective_namespace=namespace(model,n),visibility=n.get('visibility'),display=node_title(model,n)) for n in model['nodes']],policy='Explicit classifier package overrides model default; no native language default or code-generation transformation inferred')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('-o', required=True, type=Path)
    args = parser.parse_args()
    ir = build(json.loads(args.model.read_text(encoding='utf-8-sig')))
    args.o.parent.mkdir(parents=True, exist_ok=True)
    args.o.write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(ir['diagnostics']))
