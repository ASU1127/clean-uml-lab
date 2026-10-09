"""Renderer-neutral text readability checks on actual browser-measured scenes.

Reports bounding-box conflicts, not pixel-ink intersections or human ratings.
The scene must retain classifier ownership and measured text rectangles.
"""
import argparse,json,statistics
from pathlib import Path


def assess(scene):
    nodes={n['id']:n for n in scene['nodes']}
    texts=[dict(t,index=i) for i,t in enumerate(scene['texts']) if t['width']>0 and t['height']>0]
    labels=[t for t in texts if not t.get('node')]
    def bounds(t,inset=True):
        pad=.06*t['font_size'] if inset else 0
        return (t['x']+pad,t['y']+pad,t['x']+t['width']-pad,t['y']+t['height']-pad)
    def intersection(a,b,font):
        w=min(a[2],b[2])-max(a[0],b[0]);h=min(a[3],b[3])-max(a[1],b[1])
        return dict(width=w,height=h,area=w*h) if w>=font/16 and h>=font/16 and w*h>=.04*font*font else None
    overlaps=[];intrusions=[]
    for i,a in enumerate(labels):
        for b in labels[i+1:]:
            hit=intersection(bounds(a),bounds(b),max(a['font_size'],b['font_size']))
            if hit:overlaps.append(dict(texts=[a['index'],b['index']],values=[a['text'],b['text']],intersection=hit))
        for nid,n in nodes.items():
            hit=intersection(bounds(a),bounds(n,inset=False),a['font_size'])
            if hit:intrusions.append(dict(text=a['index'],value=a['text'],classifier=nid,intersection=hit))
    return dict(scope='Identical bounding-box checks across renderers on frozen browser-measured scenes. Inset .06 em and minimum .04 em squared overlap; no weight tuning. These are review findings, not pixel-ink collisions, UML validity or human-preference scores.',classifier_count=len(nodes),text_fragments=len(texts),relation_text_fragments=len(labels),median_relation_font_size=statistics.median(t['font_size'] for t in labels) if labels else None,label_label_conflicts=overlaps,label_classifier_conflicts=intrusions,status='needs_review' if overlaps or intrusions else 'no_text_bounds_conflicts_detected',excluded=['Relation-text ownership and nearest endpoint disambiguation','Text versus connector or marker clearance across external renderers','Pixel ink masks, screen readability and aesthetic preference'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('scene');p.add_argument('-o','--output',required=True);a=p.parse_args()
    result=assess(json.loads(Path(a.scene).read_text(encoding='utf-8')))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in result.items() if k in ('status','relation_text_fragments','label_label_conflicts','label_classifier_conflicts')},ensure_ascii=False))
