"""Check the rendered qualifier notation independently of its constructor."""
from geometry import segments,intersects,overlaps

NS={'s':'http://www.w3.org/2000/svg'}


def findings(root,model):
    expected={(f'edge_{i}',side):r[side+'_qualifier'] for i,r in enumerate(model['relations']) for side in ('source','target') if side+'_qualifier' in r}
    widgets={};result=[]
    def error(code,**details):result.append(dict(level='error',code=code,**details))
    nodes={}
    for g in root.findall('.//s:g',NS):
        if g.get('class')=='entity':
            rect=g.find('s:rect',NS)
            x,y,w,h=(float(rect.get(k)) for k in ('x','y','width','height'))
            nodes[g.get('id','').removeprefix('node_')]=(x,y,x+w,y+h)
    width,height=(float(root.get(k)) for k in ('width','height'))
    for edge in root.findall('s:g',NS):
        if edge.get('class')!='link':continue
        for g in edge.findall('s:g',NS):
            if g.get('class')!='qualifier':continue
            key=(edge.get('id'),g.get('data-end'))
            if key not in expected or key in widgets:
                error('unexpected_qualifier',widget=g.get('id'));continue
            rect=g.find('s:rect',NS);texts=g.findall('s:text',NS)
            if rect is None or len(texts)!=1 or texts[0].text!=expected[key]['name']:
                error('qualifier_rectangle_or_text_missing',widget=g.get('id'));continue
            x,y,w,h=(float(rect.get(k)) for k in ('x','y','width','height'));b=(x,y,x+w,y+h)
            widgets[key]=b
            if x<0 or y<0 or x+w>width or y+h>height:error('qualifier_outside_canvas',widget=g.get('id'))
            relation=model['relations'][int(key[0].split('_')[1])];owner=relation[key[1]]
            if g.get('data-classifier')!=owner:error('qualifier_wrong_semantic_end',widget=g.get('id'))
            a=nodes[owner]
            horizontal=(abs(b[3]-a[1])<1e-5 or abs(b[1]-a[3])<1e-5) and min(b[2],a[2])>max(b[0],a[0])
            vertical=(abs(b[2]-a[0])<1e-5 or abs(b[0]-a[2])<1e-5) and min(b[3],a[3])>max(b[1],a[1])
            if not(horizontal or vertical):error('qualifier_detached_from_classifier',widget=g.get('id'))
            t=texts[0];tx,ty,tw=(float(t.get(k)) for k in ('x','y','textLength'))
            if tx<x or tx+tw>x+w or ty-12<y or ty>y+h:error('qualifier_text_outside_rectangle',widget=g.get('id'))
            for name,node in nodes.items():
                if overlaps(b,node):error('qualifier_overlaps_classifier',widget=g.get('id'),node=name)
    for key in expected.keys()-widgets.keys():error('missing_qualifier',edge=key[0],side=key[1])
    for i,(key,b) in enumerate(widgets.items()):
        for other,otherbox in list(widgets.items())[i+1:]:
            if overlaps(b,otherbox):error('qualifier_rectangle_overlap',qualifiers=[list(key),list(other)])
        for edge in root.findall('s:g',NS):
            if edge.get('class')!='link':continue
            for p in edge.findall('s:path',NS):
                segs=segments(p.get('d',''))
                if segs is not None and any(intersects(s,b,inset=1) for s in segs):
                    error('edge_through_qualifier',qualifier=list(key),edge=edge.get('id'));break
            for t in edge.findall('s:text',NS):
                tx,ty,tw=(float(t.get(k)) for k in ('x','y','textLength'))
                if overlaps((tx,ty-12,tx+tw,ty),b):error('label_overlaps_qualifier',qualifier=list(key),text=t.text)
    return result
