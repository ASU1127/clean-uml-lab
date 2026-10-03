"""Two-column port routing and direct simple stars; preserve model/text facts."""
import math,xml.etree.ElementTree as ET
from lane_layout import render as lanes,element,key,NS,allocate_tracks

def move_node(g,dx,dy):
    for item in g.iter():
        for a in ('x','x1','x2'):
            if a in item.attrib:item.set(a,str(float(item.get(a))+dx))
        for a in ('y','y1','y2'):
            if a in item.attrib:item.set(a,str(float(item.get(a))+dy))

def star_center(model):
    if not 2<=len(model['nodes'])<=5 or len(model['relations'])!=len(model['nodes'])-1:return None
    allowed={'generalization','realization','dependency','association'}
    if any(r['kind'] not in allowed or set(r)-{'kind','source','target'} for r in model['relations']):return None
    for n in model['nodes']:
        leaves=[]
        for r in model['relations']:
            if r['source']==r['target'] or n['id'] not in (r['source'],r['target']):break
            leaves.append(r['target'] if r['source']==n['id'] else r['source'])
        else:
            if len(set(leaves))==len(model['nodes'])-1:return n['id']
    return None

def render(model,metrics,mode='adaptive',stars=True,compact_tracks=True):
    data,scene=lanes(model,metrics,compact=True,reuse=True)
    original=ET.fromstring(data);nodes=scene['nodes'];order=list(nodes)
    center=star_center(model) if stars and mode!='lanes' else None
    use_spread=mode=='spread' or (mode=='adaptive' and len(nodes)>=6 and scene['height']/scene['width']>1.6)
    if mode=='lanes' or (not center and not use_spread):
        scene['strategy']='lanes';return data,scene
    root=ET.Element('{'+NS+'}svg',{'style':'background:white','data-renderer':'clean-uml-adaptive-1.5'})
    def width(s):return metrics['items'][key(s)]['width']+4
    def text(parent,s,x,y):
        t=element(parent,'text',x=x,y=y,font_family='Arial',font_size=16,fill='black',textLength=width(s),lengthAdjust='spacingAndGlyphs');t.text=s
    def node_to(nid,x,y):
        old=nodes[nid].copy();g=original.find(f'.//*[@id="node_{nid}"]')
        move_node(g,x-old['x'],y-old['y']);nodes[nid].update(x=x,y=y)
        return g
    groups=[];ports={};directions={};newedges=[]
    if center:
        leaves=[n for n in order if n!=center];total=sum(nodes[n]['width'] for n in leaves)+36*(len(leaves)-1)
        canvas_width=max(total,nodes[center]['width'])+48
        groups.append(node_to(center,(canvas_width-nodes[center]['width'])/2,24))
        leaf_y=24+nodes[center]['height']+100;x=(canvas_width-total)/2
        for n in leaves:groups.append(node_to(n,x,leaf_y));x+=nodes[n]['width']+36
        for i,r in enumerate(model['relations']):
            other=r['target'] if r['source']==center else r['source'];b=nodes[other];c=nodes[center]
            # Distinct center ports rather than an ambiguous shared junction.
            j=leaves.index(other);cp=(c['x']+(j+1)*c['width']/(len(leaves)+1),c['y']+c['height']);lp=(b['x']+b['width']/2,b['y'])
            ports[(i,'source')]=cp if r['source']==center else lp
            ports[(i,'target')]=cp if r['target']==center else lp
        canvas_height=max(n['y']+n['height'] for n in nodes.values())+24
        strategy='star'
    else:
        # Contiguous height-balanced partition, deterministic and no image search.
        heights=[nodes[n]['height']+36 for n in order]
        cut=min(range(1,len(order)),key=lambda k:abs(sum(heights[:k])-sum(heights[k:])))
        left,right=order[:cut],order[cut:];left_edge=max(nodes[n]['width'] for n in left)+24
        maxlabel=max([width(r[k]) for r in model['relations'] for k in ('source_role','target_role','source_multiplicity','target_multiplicity') if k in r]+[0])
        central=max([width(r['label']) for r in model['relations'] if 'label' in r]+[0]);gap=max(20,central+24)
        # Vertical offsets on the right avoid coincident opposing horizontal legs.
        right_old_y=nodes[right[0]]['y'];left_ids=set(left)
        oldports={(e['index'],side):tuple(e[side+'_port']) for e in scene['edges'] for side in ('source','target')}
        ly=[p[1] for (i,s),p in oldports.items() if model['relations'][i][s] in left_ids]
        ry=[p[1]-right_old_y+24 for (i,s),p in oldports.items() if model['relations'][i][s] not in left_ids]
        offset=max(range(0,24),key=lambda off:min([abs(a-(b+off)) for a in ly for b in ry]+[24]))
        for (i,s),p in oldports.items():
            isleft=model['relations'][i][s] in left_ids
            ports[(i,s)]=(0,p[1] if isleft else p[1]-right_old_y+24+offset);directions[(i,s)]=1 if isleft else -1
        spans=[(i,min(ports[(i,'source')][1],ports[(i,'target')][1]),max(ports[(i,'source')][1],ports[(i,'target')][1])) for i in range(len(model['relations']))]
        allocation=allocate_tracks(spans);start=left_edge+maxlabel+44
        track_count=max(allocation.values(),default=0)+1
        label_widths={t:max([width(r['label']) for i,r in enumerate(model['relations']) if allocation[i]==t and 'label' in r]+[0]) for t in range(track_count)}
        track_x={};cursor=start
        for t in range(track_count):
            track_x[t]=cursor
            cursor+=max(20,label_widths[t]+24) if compact_tracks else gap
        right_edge=track_x[track_count-1]+max((label_widths[track_count-1] if compact_tracks else central)+24,24)+maxlabel+44
        for n in left:groups.append(node_to(n,left_edge-nodes[n]['width'],nodes[n]['y']))
        for n in right:groups.append(node_to(n,right_edge,nodes[n]['y']-right_old_y+24+offset))
        for k,(x,y) in list(ports.items()):ports[k]=(left_edge if directions[k]==1 else right_edge,y)
        canvas_width=right_edge+max(nodes[n]['width'] for n in right)+24
        canvas_height=max(n['y']+n['height'] for n in nodes.values())+24;strategy='spread'
    root.set('viewBox',f'0 0 {canvas_width} {canvas_height}');root.set('width',str(canvas_width));root.set('height',str(canvas_height))
    element(root,'rect',x=0,y=0,width=canvas_width,height=canvas_height,fill='white')
    for i,r in enumerate(model['relations']):
        sp=ports[(i,'source')];tp=ports[(i,'target')];kind=r['kind'];g=element(root,'g',id=f'edge_{i}',**{'class':'link','data-entity-1':'node_'+r['source'],'data-entity-2':'node_'+r['target']})
        if center:
            dx,dy=sp[0]-tp[0],sp[1]-tp[1];length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
            pathpoints=[sp,tp];target_unit=(ux,uy)
        else:
            route=track_x[allocation[i]];pathpoints=[sp,(route,sp[1]),(route,tp[1]),tp];target_unit=(directions[(i,'target')],0)
        end_offset=12 if kind in ('generalization','realization') else 0
        start_offset=16 if kind in ('aggregation','composition') else 0
        points=list(pathpoints)
        if start_offset:points[0]=(sp[0]+directions[(i,'source')]*start_offset,sp[1])
        points[-1]=(tp[0]+target_unit[0]*end_offset,tp[1]+target_unit[1]*end_offset)
        path=element(g,'path',d='M'+' L'.join(f'{x},{y}' for x,y in points),fill='none',stroke='black',stroke_width=1.1)
        if kind in ('dependency','realization'):path.set('stroke-dasharray','6,4')
        ux,uy=target_unit;px,py=-uy,ux
        if kind in ('generalization','realization'):
            tri=[tp,(tp[0]+ux*12+px*6,tp[1]+uy*12+py*6),(tp[0]+ux*12-px*6,tp[1]+uy*12-py*6)]
            element(g,'polygon',points=' '.join(f'{x},{y}' for x,y in tri),fill='white',stroke='black')
        elif kind=='dependency':element(g,'path',d=f'M{tp[0]+ux*10+px*5},{tp[1]+uy*10+py*5} L{tp[0]},{tp[1]} L{tp[0]+ux*10-px*5},{tp[1]+uy*10-py*5}',fill='none',stroke='black')
        if start_offset:
            ds=directions[(i,'source')];x,y=sp
            element(g,'polygon',points=f'{x},{y} {x+ds*8},{y-5} {x+ds*16},{y} {x+ds*8},{y+5}',fill='black' if kind=='composition' else 'white',stroke='black')
        for side in ('source','target'):
            xx,yy=ports[(i,side)];strings=[r[k] for k in (side+'_role',side+'_multiplicity') if k in r]
            for j,s in enumerate(strings):text(g,s,xx+20 if directions.get((i,side),1)==1 else xx-20-width(s),yy-5-18*(len(strings)-1-j))
        if 'label' in r:
            sy,ty=sp[1],tp[1];middle=(sy+ty)/2
            slots=[v for v in range(math.ceil(min(sy,ty)+18),math.floor(max(sy,ty)-5)) if all(not v-15<=p[1]<=v+2 for p in ports.values())]
            text(g,r['label'],route+6,min(slots,key=lambda v:abs(v-middle)) if slots else middle)
        newedges.append({'index':i,'source':r['source'],'target':r['target'],'source_port':sp,'target_port':tp,'points':pathpoints})
    for g in groups:root.append(g)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True),{'strategy':strategy,'compact_tracks':compact_tracks,'width':canvas_width,'height':canvas_height,'nodes':nodes,'edges':newedges}
