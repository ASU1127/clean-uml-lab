"""Compile a deliberately small class-diagram IR; no LLM or network calls."""
import argparse
import json
import re
from pathlib import Path
from type_bindings import normalize_model
from notation import NAME, VISIBILITY, package_parts, qualified_name, node_title, end_lines

ARROWS = {'generalization': '--|>', 'realization': '..|>', 'association': '--',
          'dependency': '..>', 'composition': '*--', 'aggregation': 'o--'}

def clean(value, field):
    # Bounded plain-text vocabulary prevents PlantUML/Creole directive injection.
    if not isinstance(value, str) or not value or len(value) > 320:
        raise ValueError(f'{field}: expected nonempty text <=320 characters')
    if not re.fullmatch(r'[\w .,:()+#*/\-<>\[\]=?~]+', value, re.UNICODE):
        raise ValueError(f'{field}: unsupported text syntax')
    if any(x in value for x in ('[[', ']]', '**', '//', '__', '~~')) or re.search(r'</?(?:b|i|u|s|font|color|size|img|sup|sub)(?:\s|>)',value,re.I):
        raise ValueError(f'{field}: markup is not supported')
    return value

def multiplicity(value):
    if not isinstance(value, str) or not re.fullmatch(r'(\d+|\*)(\.\.(\d+|\*))?', value):
        raise ValueError('unsupported multiplicity')
    if '..' in value:
        low, high = value.split('..')
        if low == '*' or high != '*' and int(low) > int(high):
            raise ValueError('invalid multiplicity interval')
    return f' "{value}"'

def compile_model(model, layout='default', validate_only=False):
    model, _ = normalize_model(model)
    if layout in ('structural','structural-default'):
        from layout import structural_order
        compile_model(model,'default',validate_only=True)  # Validate before graph traversal.
        return compile_model(structural_order(model),'hierarchy-up' if layout=='structural' else 'default',validate_only=validate_only)
    if layout not in ('default', 'hierarchy-up'):
        raise ValueError('unsupported layout')
    if not isinstance(model, dict) or not {'nodes', 'relations'} <= set(model) or set(model) - {'nodes', 'relations', 'package'}:
        raise ValueError('expected nodes and relations with optional package')
    if 'package' in model: package_parts(model['package'])
    if not isinstance(model['nodes'], list) or not 1 <= len(model['nodes']) <= 40:
        raise ValueError('nodes must be a nonempty list')
    if not isinstance(model['relations'], list) or len(model['relations']) > 100:
        raise ValueError('relations must be a list')
    ids, names, lines = {}, set(), []
    for node in model['nodes']:
        if not isinstance(node, dict) or not {'id', 'name', 'kind', 'members'} <= set(node) or set(node) - {'id', 'name', 'kind', 'members', 'package', 'visibility'}:
            raise ValueError('unsupported node fields')
        ident = node['id']
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', ident) or ident in ids:
            raise ValueError('invalid or duplicate node id')
        clean(node['name'], 'node name')
        if 'package' in node: package_parts(node['package'])
        if 'visibility' in node and node['visibility'] not in VISIBILITY:
            raise ValueError('package-owned classifier visibility supports public/private only')
        name = clean(node_title(model,node), 'qualified node name')
        identity = qualified_name(model,node)
        if identity in names:
            raise ValueError('duplicate qualified classifier name')
        names.add(identity)
        kind = node['kind']
        if kind not in ('class', 'interface', 'abstract', 'enum') or not isinstance(node['members'], list):
            raise ValueError('unsupported kind or members')
        ids[ident] = kind
        declaration = f'{"abstract class" if kind == "abstract" else kind} "{name}" as {ident}' + (' <<interface>>' if kind == 'interface' else '')
        members = [clean(x, 'member') for x in node['members']]
        if kind == 'enum' and any(not re.fullmatch(r'[A-Za-z_\u0080-\uffff][\w]*',m) for m in members):
            raise ValueError('enum prototype supports plain literal names only')
        lines.append(declaration + (' {\n' + '\n'.join('  '+x for x in members) + '\n}' if members else ''))
    seen, inheritance = set(), {x: [] for x in ids}
    for rel in model['relations']:
        required = {'kind', 'source', 'target'}
        optional = {'source_multiplicity', 'target_multiplicity', 'source_role', 'target_role', 'label', 'navigability', 'source_ordered', 'target_ordered', 'source_qualifier', 'target_qualifier'}
        if not isinstance(rel, dict) or not required <= set(rel) or set(rel) - required - optional:
            raise ValueError('unsupported relation fields')
        kind, source, target = rel['kind'], rel['source'], rel['target']
        if not all(isinstance(x, str) for x in (kind, source, target)) or kind not in ARROWS or source not in ids or target not in ids:
            raise ValueError('unknown kind or dangling endpoint')
        if kind in ('generalization', 'realization') and source == target:
            raise ValueError('self relationship unsupported for this relation kind')
        # Preserve distinct parallel facts; identical duplicate declarations are
        # ambiguous without stable user-provided association identities.
        key = (kind,source,target) if kind in ('generalization','realization') else json.dumps(rel,sort_keys=True,ensure_ascii=False)
        if key in seen:
            raise ValueError('identical duplicate relation needs an explicit distinct identity')
        seen.add(key)
        navigation=rel.get('navigability','--')
        if navigation not in ('--','->','<-','<->'):
            raise ValueError('unsupported navigability')
        if 'navigability' in rel and kind not in ('association','aggregation','composition'):
            raise ValueError('navigability only supported on associations')
        if kind in ('composition','aggregation') and navigation in ('<-','<->'):
            raise ValueError('whole-end arrow plus diamond is not implemented; retain the fact and report it')
        if kind in ('generalization','realization') and 'enum' in (ids[source],ids[target]):
            raise ValueError('enum inheritance/realization is not implemented')
        if kind == 'realization' and (ids[source] not in ('class','abstract') or ids[target] != 'interface'):
            raise ValueError('realization prototype requires class -> interface')
        if kind == 'generalization':
            if (ids[source] == 'interface') != (ids[target] == 'interface'):
                raise ValueError('generalization requires matching supported classifier kinds')
            inheritance[source].append(target)
        if kind in ('generalization', 'realization', 'dependency') and any(x in rel for x in ('source_multiplicity','target_multiplicity','source_role','target_role','source_ordered','target_ordered','source_qualifier','target_qualifier')):
            raise ValueError('multiplicity only supported on associations')
        for side in ('source','target'):
            if side+'_ordered' in rel and type(rel[side+'_ordered']) is not bool:
                raise ValueError('ordered end must be an explicit boolean')
            if side+'_qualifier' in rel:
                qualifier=rel[side+'_qualifier']
                if not isinstance(qualifier,dict) or set(qualifier)!={'kind','name'} or qualifier['kind']!='attribute' or not isinstance(qualifier['name'],str) or not re.fullmatch(NAME,qualifier['name']) or len(qualifier['name'])>80:
                    raise ValueError('qualifier supports one explicit attribute name; retain other qualifier forms and report them')
        def endpoint(side):
            parts=[]
            if side+'_role' in rel:
                parts.append(clean(rel[side+'_role'],'role'))
            if side+'_multiplicity' in rel:
                multiplicity(rel[side+'_multiplicity'])
                parts.append(rel[side+'_multiplicity'])
            if side+'_ordered' in rel: parts.append('{ordered}' if rel[side+'_ordered'] else '{unordered}')
            # Reserve one line above the return-end label on a self-loop.
            # This is renderer spacing, never additional model information.
            prefix = '\\n' if source == target and side == 'target' and parts else ''
            return ' "'+prefix+'\\n'.join(parts)+'"' if parts else ''
        sm, tm = endpoint('source'), endpoint('target')
        if kind == 'composition' and 'source_multiplicity' in rel:
            high = rel['source_multiplicity'].split('..')[-1]
            if high == '*' or int(high) > 1:
                raise ValueError('composite whole end cannot have upper multiplicity >1')
        label = ' : ' + clean(rel['label'], 'label') if 'label' in rel else ''
        arrow = ARROWS[kind]
        if kind=='association':arrow={'--':'--','->':'-->','<-':'<--','<->':'<-->'}[navigation]
        elif kind in ('composition','aggregation') and navigation=='->':arrow+='>'
        if layout == 'hierarchy-up':
            arrow = {'generalization': '-up-|>', 'realization': '.up.|>'}.get(kind, arrow)
            # Ordinary association is undirected. Canonicalize statement order
            # with both endpoint labels moving together; do not reverse ownership.
            ordinary_only = all(r['kind']=='association' and r['source']!=r['target'] for r in model['relations'])
            plain_label = not any(c in rel.get('label','') for c in '<>')
            if ordinary_only and plain_label and kind == 'association' and 'navigability' not in rel and list(ids).index(source)>list(ids).index(target):
                source,target,sm,tm=target,source,tm,sm
        lines.append(f'{source}{sm} {arrow}{tm} {target}{label}')
    visiting, done = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError('generalization cycle')
        if node in done:
            return
        visiting.add(node)
        for parent in inheritance[node]:
            visit(parent)
        visiting.remove(node)
        done.add(node)
    for node in ids:
        visit(node)
    if validate_only: return None
    if any(side+'_qualifier' in r for r in model['relations'] for side in ('source','target')):
        raise ValueError('PlantUML text serialization for qualifiers is not implemented; use prototype.py for native SVG/draw.io generation')
    style = (Path(__file__).resolve().parents[1]/'assets/style.puml').read_text(encoding='utf-8')
    return '@startuml\n'+style+'\n'.join(lines)+'\n@enduml\n'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compile_model(json.loads(args.model.read_text(encoding='utf-8')))
    except (ValueError, TypeError, KeyError) as error:
        parser.exit(2, f'Compile rejected: {error}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding='utf-8')
    print(args.output)

if __name__ == '__main__':
    main()
