"""Conservative SVG geometry warnings, not UML or human-vision certification."""
import math
import re

NS={'s':'http://www.w3.org/2000/svg'}

def segments(data):
    tokens=re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',data)
    result=[];i=0;command=None;point=(0.,0.)
    while i<len(tokens):
        if tokens[i].isalpha():command=tokens[i];i+=1
        count={'M':2,'L':2,'C':6}.get(command)
        if count is None or i+count>len(tokens):return None
        try:v=list(map(float,tokens[i:i+count]))
        except ValueError:return None
        if not all(math.isfinite(n) for n in v):return None
        i+=count;end=tuple(v[-2:])
        if command=='M':point=end;command='L';continue
        if command=='L':result.append((point,end))
        else:
            controls=[point,tuple(v[:2]),tuple(v[2:4]),end]
            length=sum(math.dist(a,b) for a,b in zip(controls,controls[1:]))
            steps=max(8,math.ceil(length/2))
            if steps>4096:return None
            previous=point
            for k in range(1,steps+1):
                t=k/steps;u=1-t
                current=tuple(u**3*point[a]+3*u*u*t*v[a]+3*u*t*t*v[a+2]+t**3*end[a] for a in (0,1))
                result.append((previous,current));previous=current
        point=end
    return result

def overlaps(a,b,margin=.7):
    return min(a[2],b[2])-max(a[0],b[0])>margin and min(a[3],b[3])-max(a[1],b[1])>margin

def intersects(segment,box,inset=.7):
    x0,y0,x1,y1=box;x0+=inset;y0+=inset;x1-=inset;y1-=inset
    if x0>=x1 or y0>=y1:return False
    (x,y),(xx,yy)=segment;dx=xx-x;dy=yy-y;t0,t1=0.,1.
    for p,q in ((-dx,x-x0),(dx,x1-x),(-dy,y-y0),(dy,y1-y)):
        if abs(p)<1e-12:
            if q<0:return False
        elif p<0:t0=max(t0,q/p)
        else:t1=min(t1,q/p)
        if t0>t1:return False
    return True

def global_findings(root):
    findings=[];nodes=[];labels=[];edges=[]
    entity_names={g.get('id'):g.get('data-qualified-name',g.get('id')) for g in root.findall('.//s:g',NS) if 'entity' in g.get('class','').split()}
    parents={c:p for p in root.iter() for c in p}
    def transformed(element):
        while element is not None:
            if element.get('transform'):return True
            element=parents.get(element)
        return False
    def warn(code,**details):findings.append(dict(level='warning',code=code,**details))
    for group in root.findall('.//s:g',NS):
        classes=group.get('class','').split()
        if not ('entity' in classes or 'link' in classes):continue
        ident=group.get('data-qualified-name',group.get('id','unknown'))
        if transformed(group):warn('unsupported_global_geometry',element=ident);continue
        if 'entity' in classes:
            rect=group.find('s:rect',NS)
            if rect is None or transformed(rect):warn('unsupported_global_geometry',element=ident);continue
            x,y,w,h=(float(rect.get(k,'0')) for k in ('x','y','width','height'))
            nodes.append((ident,(x,y,x+w,y+h)))
        else:
            lines=[]
            for path in group.findall('.//s:path',NS):
                segs=segments(path.get('d',''))
                if segs is None or transformed(path):warn('unsupported_global_geometry',element=ident)
                else:lines.extend(segs)
            endpoints={entity_names.get(group.get(k)) for k in ('data-entity-1','data-entity-2')}
            # Older renderer metadata can omit endpoint names. Avoid claiming
            # clean routing when unrelated-node exclusions cannot be established.
            if None in endpoints:warn('missing_edge_endpoint_metadata',element=ident)
            edges.append((ident,lines,endpoints))
            for text in group.findall('.//s:text',NS):
                if transformed(text) or any(k not in text.attrib for k in ('x','y','textLength','font-size')):
                    warn('unsupported_label_geometry',element=ident);continue
                x,y,w,size=(float(text.get(k)) for k in ('x','y','textLength','font-size'))
                labels.append((ident,''.join(text.itertext()),(x,y-size*.75,x+w,y)))
    for edge,lines,endpoints in edges:
        for owner,label,box in labels:
            if edge!=owner and any(intersects(s,box) for s in lines):
                warn('cross_edge_label_collision',edge=edge,label_owner=owner,text=label)
        for node,box in nodes:
            if node not in endpoints and any(intersects(s,box,inset=2) for s in lines):
                warn('edge_through_unrelated_node',edge=edge,node=node)
    for i,(owner,label,box) in enumerate(labels):
        for node,nodebox in nodes:
            if overlaps(box,nodebox):warn('label_node_overlap',link=owner,text=label,node=node)
        for other,otherlabel,otherbox in labels[i+1:]:
            if overlaps(box,otherbox):warn('label_label_overlap',links=[owner,other],texts=[label,otherlabel])
    return findings
