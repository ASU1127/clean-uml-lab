"""Conservative class layout: labels occupy port bands, edges distinct tracks.

The deliberate tradeoff is a taller canvas. No text/relationship is omitted.
"""
import json,math,xml.etree.ElementTree as ET
from compile_model import compile_model
from layout import structural_order
from notation import node_title,end_lines,qualifier_name
NS='http://www.w3.org/2000/svg';ET.register_namespace('',NS)
def element(parent,tag,**attrs):return ET.SubElement(parent,'{'+NS+'}'+tag,{k.replace('_','-'):str(v) for k,v in attrs.items()})
def key(text,italic=False):return ('italic:' if italic else 'normal:')+text
def measurements(model):
    compile_model(model,validate_only=True);items={}
    for n in model['nodes']:
        title=node_title(model,n)
        items[key(title,n['kind']=='abstract')]={'key':key(title,n['kind']=='abstract'),'text':title,'italic':n['kind']=='abstract'}
        for s in n['members']+(['«interface»'] if n['kind']=='interface' else ['«enumeration»'] if n['kind']=='enum' else []):items[key(s)]={'key':key(s),'text':s,'italic':False}
    for r in model['relations']:
        for k in ('source_role','target_role','source_multiplicity','target_multiplicity','label'):
            if k in r:items[key(r[k])]={'key':key(r[k]),'text':r[k],'italic':False}
        for side in ('source','target'):
            strings=end_lines(r,side)
            if side+'_qualifier' in r: strings.append(qualifier_name(r,side))
            for s in strings:items[key(s)]={'key':key(s),'text':s,'italic':False}
    return list(items.values())

def allocate_tracks(intervals, gap=18):
    """Reuse a route only after its previous vertical interval has ended."""
    ends=[];assigned={}
    for i,low,high in sorted(intervals,key=lambda x:(x[1],x[2],x[0])):
        free=next((j for j,end in enumerate(ends) if end+gap<low),None)
        if free is None:free=len(ends);ends.append(high)
        else:ends[free]=high
        assigned[i]=free
    return assigned

def render(model,metrics,reserve=True,tracks=True,compact=False,reuse=False,nodes_only=False):
    compile_model(model,validate_only=True);ordered=structural_order(model)['nodes'];widths=metrics['items']
    if not nodes_only and any(side+'_qualifier' in r for r in model['relations'] for side in ('source','target')):
        raise ValueError('lane-only rendering does not support qualifiers; use the tree pipeline')
    def width(s,italic=False):return widths[key(s,italic)]['width']+4
    incident={n['id']:[] for n in ordered}
    for i,r in enumerate(model['relations']):
        incident[r['source']].append((i,'source'));incident[r['target']].append((i,'target'))
    natural={}
    for n in ordered:
        natural[n['id']]=max([width(node_title(model,n),n['kind']=='abstract')]+[width(x) for x in n['members']]+([width('«interface»')] if n['kind']=='interface' else [width('«enumeration»')] if n['kind']=='enum' else []))+24
    right=max(natural.values())+24;nodes={};ports={};y=24
    for n in ordered:
        fields=[m for m in n['members'] if '(' not in m];methods=[m for m in n['members'] if '(' in m]
        header=48 if n['kind'] in ('interface','enum') else 28
        content=header+len(n['members'])*22+12+(6 if fields and methods else 0)
        # One band can hold role + multiplicity plus a baseline gap.
        h=max(content,len(incident[n['id']])*48+20) if reserve else content
        if compact and reserve:
            cursor=8
            for i,side in incident[n['id']]:
                r=model['relations'][i]
                lines=len(end_lines(r,side))
                cursor+=max(24,lines*18+12)
                ports[(i,side)]=(right,y+cursor)
            h=max(content,cursor+12)
        else:
            for j,(i,side) in enumerate(incident[n['id']]):ports[(i,side)]=(right,y+(j+1)*h/(len(incident[n['id']])+1))
        nodes[n['id']]={'x':right-natural[n['id']],'y':y,'width':natural[n['id']],'height':h,'header':header}
        y+=h+36
    maxlabel=max([width(r[k]) for r in model['relations'] for k in ('source_role','target_role','source_multiplicity','target_multiplicity') if k in r]+[0])
    track_start=right+maxlabel+44
    # Central relationship names sit on a reserved top-of-track segment.
    central=max([width(r['label']) for r in model['relations'] if 'label' in r]+[0])
    track_gap=max(20,central+24) if tracks else 0
    intervals=[(i,min(ports[(i,'source')][1],ports[(i,'target')][1]),max(ports[(i,'source')][1],ports[(i,'target')][1])) for i in range(len(model['relations']))]
    allocation=allocate_tracks(intervals) if reuse and tracks else {i:i for i in range(len(model['relations']))}
    canvas_width=track_start+max(allocation.values(),default=0)*track_gap+max(36,central+18)
    root=ET.Element('{'+NS+'}svg',{'viewBox':f'0 0 {canvas_width} {y}','width':str(canvas_width),'height':str(y),'style':'background:white','data-renderer':'clean-uml-lanes-1.3'})
    element(root,'rect',x=0,y=0,width=canvas_width,height=y,fill='white')
    def text(parent,s,x,ypos,italic=False):
        t=element(parent,'text',x=x,y=ypos,font_family='Arial',font_size=16,fill='black',textLength=width(s,italic),lengthAdjust='spacingAndGlyphs')
        if italic:t.set('font-style','italic')
        t.text=s
    edge_metadata=[]
    # Structured rendering reuses only the class groups, with its own routes.
    # Avoid scanning old track label slots for edges that will be discarded.
    for i,r in enumerate([] if nodes_only else model['relations']):
        sx,sy=ports[(i,'source')];tx,ty=ports[(i,'target')];route=track_start+allocation[i]*track_gap
        kind=r['kind'];group=element(root,'g',id=f'edge_{i}',**{'class':'link','data-entity-1':'node_'+r['source'],'data-entity-2':'node_'+r['target']})
        start=sx+(16 if kind in ('composition','aggregation') else 0);end=tx+(12 if kind in ('generalization','realization') else 0)
        d=f'M{start},{sy} L{route},{sy} L{route},{ty} L{end},{ty}'
        path=element(group,'path',d=d,fill='none',stroke='black',stroke_width=1.1)
        if kind in ('dependency','realization'):path.set('stroke-dasharray','6,4')
        if kind in ('generalization','realization'):element(group,'polygon',points=f'{tx},{ty} {tx+12},{ty-6} {tx+12},{ty+6}',fill='white',stroke='black')
        elif kind=='dependency':element(group,'path',d=f'M{tx+10},{ty-5} L{tx},{ty} L{tx+10},{ty+5}',fill='none',stroke='black')
        if kind in ('composition','aggregation'):element(group,'polygon',points=f'{sx},{sy} {sx+8},{sy-5} {sx+16},{sy} {sx+8},{sy+5}',fill='black' if kind=='composition' else 'white',stroke='black')
        for side in ('source','target'):
            xx,yy=ports[(i,side)];strings=end_lines(r,side)
            for j,s in enumerate(strings):text(group,s,xx+20,yy-5-18*(len(strings)-1-j))
        if 'label' in r:
            # Vertical track text stays alongside its own private track; never
            # rotates or introduces a decorative legend. More width is reserved.
            middle=(sy+ty)/2
            slots=[v for v in range(math.ceil(min(sy,ty)+18),math.floor(max(sy,ty)-5)) if all(not v-15<=p[1]<=v+2 for p in ports.values())]
            baseline=min(slots,key=lambda v:abs(v-middle)) if slots else middle
            text(group,r['label'],route+6,baseline)
        edge_metadata.append({'index':i,'source':r['source'],'target':r['target'],'source_port':[sx,sy],'target_port':[tx,ty],'track':route})
    for n in ordered:
        b=nodes[n['id']];x=b['x'];yy=b['y'];w=b['width'];h=b['height'];header=b['header']
        g=element(root,'g',id='node_'+n['id'],**{'class':'entity','data-qualified-name':n['id']})
        element(g,'rect',x=x,y=yy,width=w,height=h,fill='white',stroke='black',stroke_width=1)
        if n['kind']=='interface':text(g,'«interface»',x+(w-width('«interface»'))/2,yy+19)
        if n['kind']=='enum':text(g,'«enumeration»',x+(w-width('«enumeration»'))/2,yy+19)
        title=node_title(model,n)
        text(g,title,x+(w-width(title,n['kind']=='abstract'))/2,yy+header-8,n['kind']=='abstract')
        fields=[m for m in n['members'] if '(' not in m];methods=[m for m in n['members'] if '(' in m]
        cursor=yy+header
        if n['members']:element(g,'line',x1=x,y1=cursor,x2=x+w,y2=cursor,stroke='black')
        for index,part in enumerate((fields,methods)):
            if index and fields and methods:
                cursor+=6;element(g,'line',x1=x,y1=cursor,x2=x+w,y2=cursor,stroke='black')
            for s in part:cursor+=22;text(g,s,x+10,cursor-5)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True),{'nodes':nodes,'edges':edge_metadata,'width':canvas_width,'height':y,'reserve_label_bands':reserve,'separate_edge_tracks':tracks,'compact_bands':compact,'reuse_tracks':reuse}
