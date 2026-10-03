"""Explicit UML notation shared by measurement, rendering and export.

Package paths on a classifier are absolute; the model package is a default
for classifiers without a package. Absence never supplies language defaults.
"""
import re

NAME = r'[A-Za-z_\u0080-\uffff]\w*'
VISIBILITY = {'public': '+', 'private': '-'}


def package_parts(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 12:
        raise ValueError('package must be a nonempty list of namespace paths')
    result = []
    for part in value:
        if not isinstance(part, str) or not re.fullmatch(NAME + r'(?:\.' + NAME + r')*', part):
            raise ValueError('invalid package path')
        result.extend(part.split('.'))
    if len(result) > 12 or len('::'.join(result)) > 240:
        raise ValueError('package path is too long')
    return result


def namespace(model, node):
    value = node.get('package', model.get('package'))
    return package_parts(value) if value is not None else []


def qualified_name(model, node):
    return '::'.join(namespace(model, node) + [node['name']])


def node_title(model, node):
    prefix = VISIBILITY[node['visibility']] + ' ' if 'visibility' in node else ''
    return prefix + qualified_name(model, node)


def end_lines(relation, side):
    result = [relation[k] for k in (side + '_role', side + '_multiplicity') if k in relation]
    if side + '_ordered' in relation:
        result.append('{ordered}' if relation[side + '_ordered'] else '{unordered}')
    return result


def qualifier_name(relation, side):
    return relation[side + '_qualifier']['name']
