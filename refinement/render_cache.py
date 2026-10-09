"""Translate previously measured text bounds only for identical SVG typography.

Class shapes, routes, text values, typography, lengths and transformations must
stay identical. This cache cannot project arbitrary layout/font/text changes.
"""
import copy
import xml.etree.ElementTree as ET

from affinity_review import bind, assess


def fragments(root):
    parents = {c: p for p in root.iter() for c in p}
    result = []
    for el in root.iter():
        if el.tag.rsplit('}', 1)[-1] != 'text' or not ''.join(el.itertext()).strip():
            continue
        p = el
        in_defs = False
        while p is not None:
            if p.tag.rsplit('}', 1)[-1] == 'defs':
                in_defs = True
            p = parents.get(p)
        if not in_defs:
            result.append(el)
    return result


def frozen_structure(svg):
    root = ET.fromstring(svg)
    for el in fragments(root):
        for name in ('x', 'y', 'data-label-align'):
            el.attrib.pop(name, None)
    return ET.tostring(root)


class RenderCache:
    def __init__(self, svg, model, measured_scene):
        if measured_scene['engine'] != 'clean':
            raise ValueError('Translation cache currently supports native Clean SVG text only')
        root = ET.fromstring(svg)
        if any(el.tag.rsplit('}', 1)[-1] == 'foreignObject' for el in root.iter()):
            raise ValueError('HTML typography is outside the translation cache scope')
        self.structure = frozen_structure(svg)
        self.old_texts = fragments(root)
        self.scene = bind(svg, model, measured_scene)
        if len(self.old_texts) != len(self.scene['texts']):
            raise ValueError('Measured fragment count mismatch')
        self.model = model

    def project(self, svg):
        if frozen_structure(svg) != self.structure:
            raise ValueError('Cache invalid: typography, text, transforms or graph geometry changed')
        new_texts = fragments(ET.fromstring(svg))
        projected = copy.deepcopy(self.scene)
        for measured, old, new in zip(projected['texts'], self.old_texts, new_texts):
            measured['x'] += float(new.get('x'))-float(old.get('x'))
            measured['y'] += float(new.get('y'))-float(old.get('y'))
            measured['label_id'] = new.get('data-label-id')
        return projected

    def review(self, svg):
        projected = self.project(svg)
        result = assess(projected)
        for warning in result['proximity_warnings']:
            warning['label_id'] = projected['texts'][warning['text_index']]['label_id']
        return result
