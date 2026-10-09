"""Exact memoization of unchanged fragment proximity on fixed scene geometry."""
import copy
import xml.etree.ElementTree as ET

from render_cache import RenderCache as TranslationCache
from affinity_review import assess


class RenderCache(TranslationCache):
    def __init__(self, svg, model, measured_scene, cache_distances=True):
        if any(el.get('transform') for el in ET.fromstring(svg).iter()):
            raise ValueError('Transformed text requires remeasurement; translation cache scope exceeded')
        super().__init__(svg, model, measured_scene)
        self.cache_distances = cache_distances
        self.memo = {}
        self.stats = dict(fragment_computations=0, fragment_reuses=0)

    def review(self, svg):
        if not self.cache_distances:
            return super().review(svg)
        projected = self.project(svg)
        empty = assess({'edges': projected['edges'], 'texts': []})
        warnings, unknown, covered = [], [], 0
        for index, text in enumerate(projected['texts']):
            key = (index, text.get('node'), text.get('qualifier'), text.get('relation'),
                   text.get('end'), text['x'], text['y'], text['width'], text['height'])
            if key in self.memo:
                one = self.memo[key]
                self.stats['fragment_reuses'] += 1
            else:
                one = assess({'edges': projected['edges'], 'texts': [text]})
                self.stats['fragment_computations'] += 1
                if len(self.memo) >= 4096:
                    self.memo.pop(next(iter(self.memo)))
                self.memo[key] = one
            covered += one['mapped_relation_fragments']
            for warning in one['proximity_warnings']:
                warnings.append({**warning, 'text_index': index, 'label_id': text.get('label_id')})
            for missing in one['unmapped_fragments']:
                unknown.append({**missing, 'text_index': index})
        return {**empty, 'mapped_relation_fragments': covered, 'unmapped_fragments': unknown,
                'proximity_warnings': warnings,
                'status': 'needs_review' if warnings or unknown else 'no_proximity_warning_detected'}
