"""Bounded source-to-SVG audit. Checks observable geometry, not human taste."""
import re
from functools import lru_cache
import xml.etree.ElementTree as ET
from geometry import global_findings
from notation import node_title,end_lines
from qualifier_audit import findings as qualifier_findings

NS={'s':'http://www.w3.org/2000/svg'}
def norm(s): return ''.join(s.split())

def uncached_path_points(data):
    """Sample the absolute M/L/C subset emitted by the pinned PlantUML renderer.

    Unsupported SVG commands return None rather than a false clean result.
    Sampling is a warning heuristic, not a pixel/glyph intersection proof.
    """
    tokens=re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',data)
    points=[];i=0;cmd=None;current=(0.,0.)
    while i<len(tokens):
        if tokens[i].isalpha():cmd=tokens[i];i+=1
        count={'M':2,'L':2,'C':6}.get(cmd)
        if count is None or i+count>len(tokens):return None
        try:values=list(map(float,tokens[i:i+count]))
        except ValueError:return None
        i+=count;end=tuple(values[-2:])
        if cmd=='M':points.append(end);cmd='L'
        else:
            for k in range(1,101):
                t=k/100;u=1-t
                if cmd=='C':
                    points.append(tuple(u**3*current[a]+3*u*u*t*values[a]+3*u*t*t*values[a+2]+t**3*end[a] for a in (0,1)))
                else:points.append(tuple(current[a]*(1-t)+end[a]*t for a in (0,1)))
        current=end
    return points

PATH_CACHE_ENABLED=True

@lru_cache(maxsize=256)
def cached_path_points(data):
    result=uncached_path_points(data)
    return None if result is None else tuple(result)

def configure_path_cache(enabled=True):
    global PATH_CACHE_ENABLED
    PATH_CACHE_ENABLED=enabled
    cached_path_points.cache_clear()

def path_points(data):
    if not PATH_CACHE_ENABLED:return uncached_path_points(data)
    result=cached_path_points(data)
    # Callers receive a fresh list; mutation cannot corrupt a later audit.
    return None if result is None else list(result)

def label_findings(root):
    findings=[]
    for group in root.findall('.//s:g',NS):
        if 'link' not in group.get('class','').split():continue
        points=[]
        for path in group.findall('.//s:path',NS):
            sampled=path_points(path.get('d',''))
            if sampled is None or path.get('transform') or group.get('transform'):
                findings.append({'level':'warning','code':'unsupported_link_geometry'})
            else:points.extend(sampled)
        for text in group.findall('.//s:text',NS):
            if any(k not in text.attrib for k in ('x','y','textLength','font-size')):continue
            x,y,w,size=(float(text.get(k)) for k in ('x','y','textLength','font-size'))
            if any(x+.7<px<x+w-.7 and y-size*.75<py<y-.7 for px,py in points):
                findings.append({'level':'warning','code':'edge_label_collision','text':''.join(text.itertext()),'link':group.get('id')})
    return findings

def audit_svg(data, model, global_checks=True):
    root=ET.fromstring(data)
    findings=label_findings(root); boxes={}; groups={}
    if global_checks:findings.extend(global_findings(root))
    for group in root.findall('.//s:g',NS):
        if 'entity' not in group.get('class','').split(): continue
        rect=group.find('s:rect',NS)
        if rect is None: continue
        if group.get('transform') or rect.get('transform'):
            findings.append({'level':'warning','code':'unsupported_transform'});continue
        box=tuple(float(rect.get(k,'0')) for k in ('x','y','width','height'))
        ident=group.get('data-qualified-name',group.get('id',''))
        boxes[ident]=box;groups[ident]=group
        x,y,w,h=box
        for text in group.findall('.//s:text',NS):
            # PlantUML textLength is a renderer measurement, not a font-glyph proof.
            if any(k not in text.attrib for k in ('x','y','textLength')):continue
            tx,ty,tw=(float(text.get(k)) for k in ('x','y','textLength'))
            if tx < x-1 or tx+tw > x+w+1 or ty > y+h+1 or ty < y:
                findings.append({'level':'error','code':'text_outside_node','node':ident,'text':''.join(text.itertext())})
    keys=list(boxes)
    for i,a in enumerate(keys):
        x,y,w,h=boxes[a]
        for b in keys[i+1:]:
            xx,yy,ww,hh=boxes[b]
            if min(x+w,xx+ww)-max(x,xx)>.5 and min(y+h,yy+hh)-max(y,yy)>.5:
                findings.append({'level':'error','code':'node_overlap','nodes':[a,b]})
    if len(boxes)!=len(model['nodes']):
        findings.append({'level':'warning','code':'entity_metadata_count_mismatch','found':len(boxes),'expected':len(model['nodes'])})
    alltext=norm(''.join(root.itertext()))
    for node in model['nodes']:
        group=groups.get(node['id'])
        text=norm(''.join(group.itertext())) if group is not None else alltext
        for expected in [node_title(model,node)]+node['members']:
            if norm(expected) not in text:
                findings.append({'level':'error','code':'missing_rendered_text','node':node['id'],'text':expected})
    for i,relation in enumerate(model['relations']):
        group=root.find(f'.//*[@id="edge_{i}"]')
        if group is None:continue
        expected=end_lines(relation,'source')+end_lines(relation,'target')+([relation['label']] if 'label' in relation else [])
        if [t.text for t in group.findall('s:text',NS)]!=expected:
            findings.append({'level':'error','code':'relation_label_text_or_order_mismatch','edge':f'edge_{i}'})
    if any(side+'_qualifier' in r for r in model['relations'] for side in ('source','target')):
        findings.extend(qualifier_findings(root,model))
    return {'status':'failed' if any(f['level']=='error' for f in findings) else 'passed_with_warnings' if findings else 'passed',
            'checks':['entity_rectangle_overlap','renderer_text_bounds','expected_node_and_member_text','sampled_own_edge_label_collision']+(['cross_edge_labels','unrelated_node_routing','label_node_overlap','label_label_overlap'] if global_checks else []),
            'not_checked':['full_UML_semantics','business_requirements','font_glyph_coverage','edge_crossings','arrowhead_collisions','human_readability']+([] if global_checks else ['edge_node_intersection']),
            'findings':findings}

def audit_contract(model, contract):
    """Explicit requirements supplied separately; not inferred truth."""
    allowed={'required_nodes','required_relations','forbidden_nodes','forbidden_relations'}
    if not isinstance(contract,dict) or set(contract)-allowed: raise ValueError('unsupported contract fields')
    findings=[]
    for key,items in contract.items():
        if not isinstance(items,list) or any(not isinstance(x,dict) or not x for x in items):
            raise ValueError('contract entries must be nonempty object lists')
        hay=model['nodes'] if key.endswith('nodes') else model['relations']
        for expected in items:
            found=any(all(actual.get(k)==v for k,v in expected.items()) for actual in hay)
            if (key.startswith('required') and not found) or (key.startswith('forbidden') and found):
                findings.append({'level':'error','code':key,'fact':expected})
    return {'status':'failed' if findings else 'passed','origin':'caller supplied assertions, not independent ground truth','findings':findings}
