"""Relation-text proximity warnings from real rendered SVG text bounds.

Bind fragments using native SVG groups or uniquely matching canonical text.
Unbound fragments are counted, never silently treated as clear. This measures
visual proximity, not semantic Property ownership or human understanding.
"""
import math
import re
import xml.etree.ElementTree as ET

from path_labels import segment_box_distance

POLICY = {'margin_text_height': .22, 'inset_text_height': .04}


def normalized(value):
    return re.sub(r'\s+', ' ', value).strip()


def bind(svg, model, scene):
    root = ET.fromstring(svg)
    parents = {child: parent for parent in root.iter() for child in parent}
    engine = scene['engine']
    canonical = {}
    for index, relation in enumerate(model['relations']):
        for side in ('source', 'target'):
            values = [relation.get(side+'_role'), relation.get(side+'_multiplicity')]
            text = normalized(' '.join(v for v in values if v))
            if text:
                canonical.setdefault(text, []).append((index, side))
        if relation.get('label'):
            canonical.setdefault(normalized(relation['label']), []).append((index, 'center'))
    plant_links = sorted((el for el in root.iter() if 'link' in el.get('class', '').split()),
                         key=lambda el: int(el.get('data-source-line', '-1')))
    plant_index = {el: index for index, el in enumerate(plant_links)}
    metadata = []
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1] not in ('text', 'foreignObject'):
            continue
        value = ''.join(element.itertext()).strip()
        if not value:
            continue
        ancestry = []
        current = element
        while current is not None:
            ancestry.append(current)
            current = parents.get(current)
        if any(el.tag.rsplit('}', 1)[-1] == 'defs' for el in ancestry):
            continue
        meta = dict(text=value, relation=None, end=element.get('data-end'), binding=None,
                    qualifier=any('qualifier' in el.get('class', '').split() for el in ancestry))
        if engine == 'clean':
            links = [el for el in ancestry if re.fullmatch(r'edge_\d+', el.get('id', ''))]
            if links:
                meta.update(relation=int(links[0].get('id')[5:]), binding='explicit SVG relation group')
        elif engine == 'plantuml':
            links = [el for el in ancestry if el in plant_index]
            if links:
                meta.update(relation=plant_index[links[0]], binding='verified source-line relation group')
        elif engine != 'mermaid':
            raise ValueError('Unsupported engine '+engine)
        choices = canonical.get(normalized(value), [])
        if meta['relation'] is None and len(choices) == 1:
            meta.update(relation=choices[0][0], end=choices[0][1], binding='unique canonical relation text')
        if meta['relation'] is not None and not 0 <= meta['relation'] < len(model['relations']):
            raise ValueError('Unexpected relation text owner')
        metadata.append(meta)
    if len(metadata) != len(scene['texts']):
        raise ValueError(f'SVG text order does not match measured scene: {len(metadata)} != {len(scene["texts"])}')
    result = dict(scene)
    texts = []
    for measured, meta in zip(scene['texts'], metadata):
        if normalized(measured['text']) != normalized(meta['text']):
            raise ValueError('SVG fragment differs from measured fragment')
        texts.append({**measured, **{k: v for k, v in meta.items() if k != 'text'}})
    result['texts'] = texts
    return result


def assess(scene):
    paths = {edge['index']: list(zip(edge['points'], edge['points'][1:])) for edge in scene['edges']}
    warnings, unknown = [], []
    covered = 0
    for index, text in enumerate(scene['texts']):
        if text.get('node') or text.get('qualifier') or text['width'] <= 0 or text['height'] <= 0:
            continue
        owner = text.get('relation')
        if owner not in paths:
            unknown.append({'text_index': index, 'text': text['text']})
            continue
        covered += 1
        inset = POLICY['inset_text_height']*text['height']
        rectangle = (text['x']+inset, text['y']+inset,
                     text['x']+text['width']-inset, text['y']+text['height']-inset)
        own = min(segment_box_distance(a, b, rectangle) for a, b in paths[owner])
        foreign = [(min(segment_box_distance(a, b, rectangle) for a, b in segments), other)
                   for other, segments in paths.items() if other != owner and segments]
        other_distance, other = min(foreign, default=(math.inf, None))
        required = POLICY['margin_text_height']*text['height']
        if other_distance-own < required-1e-6:
            warnings.append(dict(text_index=index, text=text['text'], relation=owner,
                                 end=text.get('end'), nearest_other_relation=other,
                                 own_distance=round(own, 3), other_distance=round(other_distance, 3),
                                 margin=round(other_distance-own, 3), required_margin=round(required, 3)))
    return dict(scope='Same scale-normalized text-box-to-connector distance across frozen renderers. A warning means another relation is closer or lacks a .22 text-height separation advantage. This is an engineering review heuristic; no human rating, pixel-ink or UML semantic-ownership certification.',
                policy=POLICY, mapped_relation_fragments=covered, unmapped_fragments=unknown,
                proximity_warnings=warnings, status='needs_review' if warnings or unknown else 'no_proximity_warning_detected')
