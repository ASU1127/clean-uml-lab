"""Resolve explicit imports only in typed member positions, with a trace."""
import copy
import re

NAME = r'[A-Za-z_\u0080-\uffff]\w*'
QUALIFIED = re.compile(NAME + r'(?:\.' + NAME + r')+')
TOKEN = re.compile(NAME + r'|[.<>,\[\]]')


def bind_type(text, bindings):
    tokens = list(TOKEN.finditer(text))
    end = 0
    for token in tokens:
        if text[end:token.start()].strip():
            raise ValueError('unsupported imported member type expression')
        end = token.end()
    if text[end:].strip() or not tokens:
        raise ValueError('unsupported imported member type expression')
    index = 0
    replacements = []

    def peek():
        return tokens[index].group() if index < len(tokens) else None

    def consume(value):
        nonlocal index
        if peek() != value:
            raise ValueError('malformed imported member type expression')
        index += 1

    def expression():
        nonlocal index
        start = index
        if not peek() or not re.fullmatch(NAME, peek()):
            raise ValueError('type name expected in imported member')
        index += 1
        while peek() == '.':
            index += 1
            if not peek() or not re.fullmatch(NAME, peek()):
                raise ValueError('qualified type name expected')
            index += 1
        # A qualified name is already bound. Never replace its final component.
        if index == start + 1 and tokens[start].group() in bindings:
            token = tokens[start]
            replacements.append((token.start(), token.end(), bindings[token.group()]))
        if peek() == '<':
            consume('<'); expression()
            while peek() == ',':
                consume(','); expression()
            consume('>')
        while peek() == '[':
            consume('['); consume(']')

    expression()
    if index != len(tokens):
        raise ValueError('unsupported imported member type expression tail')
    result = text
    for start, end, replacement in reversed(replacements):
        result = result[:start] + replacement + result[end:]
    return result


def bind_member(text, bindings):
    def typed(value):
        if value.count(':') != 1:
            raise ValueError('imports require a typed member or typed parameter')
        head, tail = value.split(':')
        if not head.strip():
            raise ValueError('member or parameter name missing')
        return head + ':' + bind_type(tail, bindings)

    if '(' not in text:
        return typed(text)
    match = re.fullmatch(r'([^()]+)\(([^()]*)\)(\s*:\s*.+)', text)
    if not match:
        raise ValueError('imports require a typed method signature')
    parameters = match.group(2)
    depth = 0
    start = 0
    chunks = []
    for index, char in enumerate(parameters):
        if char == '<': depth += 1
        elif char == '>': depth -= 1
        elif char == ',' and depth == 0:
            chunks.append(typed(parameters[start:index])); start = index + 1
        if depth < 0:
            raise ValueError('malformed generic parameter type')
    if parameters.strip(): chunks.append(typed(parameters[start:]))
    result_type = match.group(3)
    before, after = result_type.split(':', 1)
    return match.group(1) + '(' + ','.join(chunks) + ')' + before + ':' + bind_type(after, bindings)


def normalize_model(model):
    if not isinstance(model, dict) or not {'nodes', 'relations'} <= set(model) or set(model) - {'nodes', 'relations', 'imports', 'package'}:
        raise ValueError('expected nodes and relations, with optional explicit imports and package')
    normalized = copy.deepcopy({k: model[k] for k in ('nodes', 'relations', 'package') if k in model})
    imports = model.get('imports', [])
    if not isinstance(imports, list) or any(not isinstance(x, str) or len(x) > 320 or not QUALIFIED.fullmatch(x) for x in imports):
        raise ValueError('imports must be explicit qualified type names; wildcard/static imports unsupported')
    if len(imports) != len(set(imports)):
        raise ValueError('duplicate import')
    bindings = {}
    for name in imports:
        simple = name.rsplit('.', 1)[1]
        if simple in bindings:
            raise ValueError('ambiguous imported simple type name: ' + simple)
        bindings[simple] = name
    trace = dict(imports=imports, bindings=bindings, changed_members=[], scope='Explicit imports resolved in member types only; no classpath or implicit-language-default validation')
    if not imports:
        return normalized, trace
    if not isinstance(normalized['nodes'], list):
        raise ValueError('nodes must be a list')
    for node in normalized['nodes']:
        if not isinstance(node, dict) or not isinstance(node.get('members'), list):
            raise ValueError('unsupported node for import binding')
        if node.get('name') in bindings:
            raise ValueError('import and local classifier name conflict: ' + node['name'])
        if node.get('kind') == 'enum':
            continue
        for index, member in enumerate(node['members']):
            if not isinstance(member, str):
                raise ValueError('member must be text')
            bound = bind_member(member, bindings)
            if bound != member:
                trace['changed_members'].append(dict(node=node.get('id'), member_index=index, before=member, after=bound))
                node['members'][index] = bound
    return normalized, trace
