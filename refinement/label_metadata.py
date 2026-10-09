"""Non-visual semantic IDs for native relation-text fragments."""
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'


def annotated(svg, graph):
    root = ET.fromstring(svg)
    for edge in graph['edges']:
        group = root.find(f'.//*[@id="{edge["id"]}"]')
        fragments = [(label, text) for label in edge.get('labels', []) for text in label['lines']]
        elements = group.findall(NS+'text')
        if len(elements) != len(fragments):
            raise ValueError('Incomplete native relation labels')
        for element, (label, value) in zip(elements, fragments):
            if element.text != value:
                raise ValueError('Native fragment differs from canonical label')
            element.set('data-label-id', label['id'])
            element.set('data-end', label['id'].rsplit('_', 1)[-1])
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
