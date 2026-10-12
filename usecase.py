"""Bounded use-case layout and editable draw.io/SVG/PNG export, without an LLM."""
import argparse
import hashlib
import html
import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def validate(raw):
    allowed={'type','name','actors','use_cases','relations'}
    if not isinstance(raw,dict) or set(raw)-allowed or raw.get('type')!='use_case':
        raise ValueError('Expected type=use_case and only name, actors, use_cases, relations')
    if not isinstance(raw.get('name'),str) or not raw['name'].strip() or len(raw['name'])>120:
        raise ValueError('A nonempty system name is required')
    nodes={}
    for key,limit,fields in [('actors',12,{'id','name','kind','side'}),
                             ('use_cases',30,{'id','name','extension_points'})]:
        seq=raw.get(key)
        if not isinstance(seq,list) or not 1<=len(seq)<=limit:
            raise ValueError(f'{key} must contain 1..{limit} entries')
        for n in seq:
            if not isinstance(n,dict) or set(n)-fields:
                raise ValueError(f'Unsupported {key} fields: {n}')
            if not isinstance(n.get('id'),str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',n['id']) or n['id'] in nodes:
                raise ValueError('Node IDs must be unique, bounded ASCII identifiers')
            if not isinstance(n.get('name'),str) or not n['name'].strip() or len(n['name'])>180:
                raise ValueError(f'Invalid name for {n["id"]}')
            if key=='actors':
                if n.get('kind','human') not in ('human','external') or n.get('side','left') not in ('left','right'):
                    raise ValueError('Actor kind must be human/external; side is an optional left/right layout hint')
            else:
                points=n.get('extension_points',[])
                if not isinstance(points,list) or len(points)>4 or any(not isinstance(x,str) or not x.strip() or len(x)>70 for x in points) or len(set(points))!=len(points):
                    raise ValueError('Extension points must be unique names, at most four per use case')
            nodes[n['id']]=key
    seq=raw.get('relations')
    if not isinstance(seq,list) or len(seq)>80:
        raise ValueError('Expected at most 80 relations')
    ids=set()
    graphs={'generalization':{},'include':{}}
    signatures=set()
    for r in seq:
        if not isinstance(r,dict) or set(r)-{'id','kind','source','target','extension_points'}:
            raise ValueError(f'Unsupported relation fields: {r}')
        if not isinstance(r.get('id'),str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',r['id']) or r['id'] in ids:
            raise ValueError('Relation IDs must be unique ASCII identifiers')
        ids.add(r['id'])
        s,t=r.get('source'),r.get('target')
        if s not in nodes or t not in nodes or s==t:
            raise ValueError('Relation endpoints must be distinct existing nodes')
        kind=r.get('kind')
        if kind=='association':
            if {nodes[s],nodes[t]}!={'actors','use_cases'}:
                raise ValueError('This subject supports actor/use-case associations only')
            sig=(kind,*sorted((s,t)))
        elif kind in ('include','extend'):
            if nodes[s]!='use_cases' or nodes[t]!='use_cases':
                raise ValueError('Include/extend endpoints must both be use cases')
            sig=(kind,s,t)
            if kind=='extend':
                points=r.get('extension_points')
                target=next(n for n in raw['use_cases'] if n['id']==t)
                if not isinstance(points,list) or not points or any(not isinstance(x,str) for x in points) or len(set(points))!=len(points) or any(x not in target.get('extension_points',[]) for x in points):
                    raise ValueError('Extend needs explicit extension_points defined on its target; do not invent them')
        elif kind=='generalization':
            if nodes[s]!=nodes[t]:
                raise ValueError('Generalization must connect two actors or two use cases')
            sig=(kind,s,t)
        else:
            raise ValueError(f'Unsupported relation kind: {kind}')
        if kind!='extend' and 'extension_points' in r:
            raise ValueError('extension_points is only valid on extend relations')
        if sig in signatures:
            raise ValueError('Duplicate logical relation')
        signatures.add(sig)
        if kind in graphs:
            graphs[kind].setdefault(s,[]).append(t)
    for kind,g in graphs.items():
        visited,active=set(),set()
        def walk(n):
            if n in active:
                raise ValueError(f'{kind} cycle')
            if n in visited:
                return
            active.add(n)
            for nxt in g.get(n,[]):
                walk(nxt)
            active.remove(n)
            visited.add(n)
        for n in g:
            walk(n)
    return raw


def wrap(text, units=24):
    lines=[]
    for para in text.split('\n'):
        han_only=bool(para) and all(unicodedata.east_asian_width(ch) in ('W','F') for ch in para)
        local_units=2*math.ceil(len(para)/math.ceil(2*len(para)/units)) if han_only and 2*len(para)>units else units
        line,used='',0
        tokens=re.findall(r'[\x00-\x7f]+|[^\x00-\x7f]',para)
        tokens=[part for token in tokens for part in (re.findall(r'\S+\s*',token) if token.isascii() else [token])]
        for token in tokens:
            length=sum(2 if unicodedata.east_asian_width(ch) in ('W','F') else 1 for ch in token)
            if line and used+length>local_units:
                lines.append(line.rstrip());line,used='',0
            line+=token;used+=length
        lines.append(line.strip() or ' ')
    return lines


def dimensions(model, measurements):
    result={}
    for kind in ('actors','use_cases'):
        for n in model[kind]:
            lines=wrap(n['name']);extra=n.get('extension_points',[])
            names=[(s,16) for s in lines]
            entries=names+([('extension points',12)]+[(line,13) for p in extra for line in wrap(p)] if extra else [])
            widths=[measurements[f'{size}:{s}']['width'] for s,size in entries]
            if kind=='use_cases':
                height=max(64,28+len(names)*22+(len(entries)-len(names))*18+(8 if extra else 0))
                width=max(152,math.ceil((max(widths)+30)*1.28))
            else:
                height=max(62,40+22*len(lines)) if n.get('kind')=='external' else 110+22*(len(lines)-1)
                width=max(96,max(widths)+20)
            result[n['id']]={'id':n['id'],'kind':kind,'name':n['name'],'w':width,'h':height,
                             'lines':lines,'extra':extra,'actor_kind':n.get('kind','human')}
    return result


def side(n):
    return n.get('side','right' if n.get('kind')=='external' else 'left')


def placement(model, dims, role_order=True, relation_columns=True, title_width=0):
    actors={n['id']:n for n in model['actors']}
    uses=[n['id'] for n in model['use_cases']]
    assoc={n:[] for n in uses}
    neighbours={n:[] for n in uses}
    support=set()
    for r in model['relations']:
        s,t=r['source'],r['target']
        if r['kind']=='association':
            a,u=(s,t) if s in actors else (t,s)
            assoc[u].append(a)
        elif s in neighbours and t in neighbours:
            neighbours[s].append(t);neighbours[t].append(s)
            if r['kind']=='include':
                support.add(t)
            elif r['kind']=='extend':
                support.add(s)
            elif r['kind']=='generalization':
                support.add(s)
    indexes={n['id']:i for i,n in enumerate(model['actors'])}
    affinity={u:sum(indexes[a] for a in assoc[u])/len(assoc[u]) if assoc[u] else None for u in uses}
    for _ in range(4):
        previous=affinity.copy()
        for u in uses:
            if not assoc[u]:
                values=[previous[v] for v in neighbours[u] if previous[v] is not None]
                if values:
                    affinity[u]=sum(values)/len(values)
    groups={}
    for u in uses:
        if not relation_columns:
            col=0
        elif u in support:
            col=1
        elif assoc[u] and all(side(actors[a])=='right' for a in assoc[u]):
            col=2
        else:
            col=0
        groups.setdefault(col,[]).append(u)
    if relation_columns and len(groups)==1:
        groups={0:uses[:]}
    # Order constraints change positions only; they never create logical UML edges.
    components={};component_affinity={}
    for u in uses:
        if u in components:
            continue
        todo=[u];component=[]
        while todo:
            v=todo.pop()
            if v in component:
                continue
            component.append(v);todo.extend(neighbours[v])
        first=min(uses.index(v) for v in component)
        values=[indexes[a] for v in component if v not in support for a in assoc[v] if actors[a].get('kind','human')=='human']
        mean=sum(values)/len(values) if values else len(actors)
        for v in component:
            components[v]=first;component_affinity[v]=mean
    for col,seq in groups.items():
        if role_order:
            seq.sort(key=lambda u:(affinity[u] if affinity[u] is not None else len(actors),component_affinity[u],components[u],uses.index(u)))
    columns=sorted(groups)
    sizes={c:max(dims[u]['w'] for u in groups[c]) for c in columns}
    left_width=max((dims[n['id']]['w'] for n in model['actors'] if side(n)=='left'),default=96)
    left_shift=max(0,left_width/2+24-100)
    cx={};x=260+left_shift
    for col in columns:
        cx[col]=x+sizes[col]/2;x+=sizes[col]+170
    scene={}
    step=max(116,max(dims[u]['h'] for u in uses)+38)
    first_y=94+max(dims[u]['h'] for u in uses)/2
    for col,seq in groups.items():
        if relation_columns and col==1 and len(columns)>1:
            continue
        for i,u in enumerate(seq):
            scene[u]={**dims[u],'x':cx[col],'y':first_y+i*step,'column':col}
    if 1 in groups and relation_columns and len(columns)>1:
        desired={u:sum(scene[v]['y'] for v in neighbours[u] if v in scene)/max(1,sum(v in scene for v in neighbours[u])) for u in groups[1]}
        extended={r['source'] for r in model['relations'] if r['kind']=='extend'}
        seq=sorted(groups[1],key=lambda u:(desired[u] or first_y,u not in extended,uses.index(u))) if role_order else groups[1]
        # Least-squares projection onto non-overlapping rows, retaining both directions of slack.
        blocks=[]
        for i,u in enumerate(seq):
            blocks.append([desired[u]-i*step,1,[i]])
            while len(blocks)>1 and blocks[-2][0]/blocks[-2][1]>blocks[-1][0]/blocks[-1][1]:
                b=blocks.pop();a=blocks.pop();blocks.append([a[0]+b[0],a[1]+b[1],a[2]+b[2]])
        rows={i:max(first_y,b[0]/b[1])+i*step for b in blocks for i in b[2]}
        for i,u in enumerate(seq):
            scene[u]={**dims[u],'x':cx[1],'y':rows[i],'column':1}
    top=42
    bottom=max(n['y']+n['h']/2 for n in scene.values())+48
    boundary={'x':220+left_shift,'y':top,'w':max(x-170-220-left_shift+40,title_width+28),'h':bottom-top}
    for which in ('left','right'):
        seq=[n for n in model['actors'] if side(n)==which]
        desired={n['id']:sum(scene[u]['y'] for u in uses if n['id'] in assoc[u])/max(1,sum(n['id'] in assoc[u] for u in uses)) for n in seq}
        if role_order:
            seq.sort(key=lambda n:(desired[n['id']],indexes[n['id']]))
        last=0
        for i,a in enumerate(seq):
            d=dims[a['id']]
            y=max(first_y,desired[a['id']],last+(scene[seq[i-1]['id']]['h']+d['h'])/2+30 if i else 0)
            scene[a['id']]={**d,'x':100+left_shift if which=='left' else boundary['x']+boundary['w']+max(120,d['w']/2+30),
                            'y':y,'side':which}
            last=y
    boundary['h']=max(boundary['h'],max(n['y']+n['h']/2 for n in scene.values())+25-top)
    width=math.ceil(max(n['x']+n['w']/2 for n in scene.values())+50)
    return scene,boundary,width,math.ceil(boundary['y']+boundary['h']+36)


def anchor(n, toward):
    x,y=n['x'],n['y'];dx,dy=toward[0]-x,toward[1]-y
    if n['kind']=='use_cases':
        denom=math.hypot(dx/(n['w']/2),dy/(n['h']/2)) or 1
        return (x+dx/denom,y+dy/denom)
    if n['actor_kind']=='human':
        return (x+(24 if dx>=0 else -24),y-6)
    if abs(dx)+abs(dy)<1e-9:
        dx=-1 if n.get('side')=='right' else 1
    scale=min((n['w']/2)/abs(dx) if dx else float('inf'),(n['h']/2)/abs(dy) if dy else float('inf'))
    return (x+dx*scale,y+dy*scale)


def path_for(a,b,via):
    via=[p for p in via if math.dist(p,(a['x'],a['y']))>1 and math.dist(p,(b['x'],b['y']))>1]
    pts=[anchor(a,via[0] if via else (b['x'],b['y'])),*via,anchor(b,via[-1] if via else (a['x'],a['y']))]
    clean=[pts[0]]
    for p in pts[1:]:
        if math.dist(p,clean[-1])>.01:
            clean.append(p)
    return clean


def segments(path):
    return list(zip(path,path[1:]))


def intersection(a,b,c,d):
    cross=lambda u,v:u[0]*v[1]-u[1]*v[0]
    r=(b[0]-a[0],b[1]-a[1]);s=(d[0]-c[0],d[1]-c[1]);den=cross(r,s)
    if abs(den)<1e-7:
        return False
    q=(c[0]-a[0],c[1]-a[1]);t,u=cross(q,s)/den,cross(q,r)/den
    return 1e-5<t<1-1e-5 and 1e-5<u<1-1e-5


def rect_hit(a,b,rect,margin=0):
    x,y,w,h=rect
    x-=margin;y-=margin;w+=margin*2;h+=margin*2
    low,high=0.,1.
    for start,delta,mn,mx in [(a[0],b[0]-a[0],x,x+w),(a[1],b[1]-a[1],y,y+h)]:
        if abs(delta)<1e-9:
            if not mn<start<mx:
                return False
        else:
            p,q=sorted(((mn-start)/delta,(mx-start)/delta));low=max(low,p);high=min(high,q)
            if high-low<=1e-6:
                return False
    return high>max(low,0) and low<1


def bounds(n):
    if n['kind']=='actors' and n['actor_kind']=='human':
        return (n['x']-n['w']/2,n['y']-42,n['w'],108+22*(len(n['lines'])-1))
    return (n['x']-n['w']/2,n['y']-n['h']/2,n['w'],n['h'])


def shape_hit(a,b,n):
    if n['kind']!='use_cases':
        return rect_hit(a,b,bounds(n),4)
    rx,ry=n['w']/2+5,n['h']/2+5
    ax,ay=(a[0]-n['x'])/rx,(a[1]-n['y'])/ry
    dx,dy=(b[0]-a[0])/rx,(b[1]-a[1])/ry
    t=max(0,min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy or 1)))
    return (ax+t*dx)**2+(ay+t*dy)**2<1


def rect_overlap(a,b,margin=0):
    return min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0])>-margin and min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1])>-margin


def label_candidates(path,w,h):
    lengths=[math.dist(a,b) for a,b in segments(path)];total=sum(lengths)
    for f in (.5,.4,.6,.3,.7):
        distance=total*f
        for (a,b),length in zip(segments(path),lengths):
            if distance<=length:
                t=distance/max(length,.001);x=a[0]+(b[0]-a[0])*t;y=a[1]+(b[1]-a[1])*t
                nx,ny=-(b[1]-a[1])/max(length,.001),(b[0]-a[0])/max(length,.001)
                normal_distance=(w*abs(nx)+h*abs(ny))/2+8
                signs=(-1,1) if ny>=0 else (1,-1)
                for more in (0,14,28):
                    for sign in signs:
                        offset=sign*(normal_distance+more)
                        yield (x+nx*offset-w/2,y+ny*offset-h/2,w,h)
                # Keep text horizontal; line-adjacent positions remain visible at normal scale.
                for offset in (15,-15,28,-28,42,-42):
                    yield (x-w/2,y+offset-h/2,w,h)
                break
            distance-=length


def label_cost(rect,path,scene,placed,label_boxes,own):
    nodes=sum(rect_overlap(rect,bounds(n),4) for n in scene.values())
    texts=sum(rect_overlap(rect,b,5) for b in label_boxes)
    lines=sum(rect_hit(a,b,rect,3) for route in placed for a,b in segments(route['points']))
    self_lines=sum(rect_hit(a,b,rect,3) for a,b in segments(path))
    return nodes+texts+lines+self_lines


def routing(model,scene,metrics):
    placed=[];label_boxes=[];trials=0
    relations=sorted(model['relations'],key=lambda r:(r['kind']=='association',model['relations'].index(r)))
    for r in relations:
        a,b=scene[r['source']],scene[r['target']]
        mid=((a['x']+b['x'])/2,(a['y']+b['y'])/2)
        options=[[]]
        for offset in (-38,38,-76,76,-114,114):
            options.append([(mid[0],mid[1]+offset)])
        options.extend([[(a['x'],b['y'])],[(b['x'],a['y'])]])
        for x in sorted({n['x']-n['w']/2-24 for n in scene.values()}|{n['x']+n['w']/2+24 for n in scene.values()}):
            if min(a['x'],b['x'])-130<=x<=max(a['x'],b['x'])+130:
                options.append([(x,a['y']),(x,b['y'])])
        text='«'+r['kind']+'»' if r['kind'] in ('include','extend') else ''
        if text:
            m=metrics['14:'+text];lw,lh=m['width']+4,20
        choices=[]
        for via in options[:32]:
            trials+=1
            pts=path_for(a,b,via)
            if len(pts)<2 or any(not math.isfinite(v) for point in pts for v in point):
                continue
            hits=sum(shape_hit(p,q,n) for p,q in segments(pts) for uid,n in scene.items() if uid not in (r['source'],r['target']))
            hits+=sum(shape_hit(p,q,a) for p,q in segments(pts)[1:])
            hits+=sum(shape_hit(p,q,b) for p,q in segments(pts)[:-1])
            crosses=sum(intersection(p,q,c,d) for p,q in segments(pts) for other in placed for c,d in segments(other['points']))
            lengths=sum(math.dist(p,q) for p,q in segments(pts))
            label=None;collisions=0
            if text:
                candidates=list(label_candidates(pts,lw,lh))
                label=min(candidates,key=lambda box:label_cost(box,pts,scene,placed,label_boxes,r))
                collisions=label_cost(label,pts,scene,placed,label_boxes,r)
            obscures=sum(rect_hit(p,q,box,3) for p,q in segments(pts) for box in label_boxes)
            score=(hits+collisions+obscures,crosses,len(pts)-2,lengths)
            choices.append((score,pts,label))
        score,pts,label=min(choices,key=lambda v:v[0])
        placed.append({'id':r['id'],'kind':r['kind'],'source':r['source'],'target':r['target'],
                       'points':pts,'label':label,'text':text})
        if label:
            label_boxes.append(label)
    return placed,trials


def audit(scene,routes):
    findings={'invalid_path':[],'node_overlap':[],'line_node':[],'label_node':[],'label_label':[],
              'label_line':[],'crossings':[]}
    ns=list(scene.values())
    for i,n in enumerate(ns):
        for m in ns[i+1:]:
            if rect_overlap(bounds(n),bounds(m),-2):
                findings['node_overlap'].append([n['id'],m['id']])
    labels=[]
    for route in routes:
        pts=route['points']
        if len(pts)<2 or any(not math.isfinite(v) for point in pts for v in point) or sum(math.dist(a,b) for a,b in segments(pts))<1:
            findings['invalid_path'].append(route['id'])
        for n in ns:
            if n['id'] not in (route['source'],route['target']) and any(shape_hit(a,b,n) for a,b in segments(pts)):
                findings['line_node'].append([route['id'],n['id']])
            if route['label'] and rect_overlap(route['label'],bounds(n),2):
                findings['label_node'].append([route['id'],n['id']])
        if route['label']:
            labels.append(route)
            for other in routes:
                if any(rect_hit(a,b,route['label'],2) for a,b in segments(other['points'])):
                    findings['label_line'].append([route['id'],other['id']])
    for i,r in enumerate(routes):
        for s in routes[i+1:]:
            if any(intersection(a,b,c,d) for a,b in segments(r['points']) for c,d in segments(s['points'])):
                findings['crossings'].append([r['id'],s['id']])
    for i,r in enumerate(labels):
        for s in labels[i+1:]:
            if rect_overlap(r['label'],s['label'],2):
                findings['label_label'].append([r['id'],s['id']])
    return {'status':'needs_review' if any(findings.values()) else 'geometry_pass',
            'counts':{k:len(v) for k,v in findings.items()},'findings':findings,
            'bends':sum(len(r['points'])-2 for r in routes),
            'route_length':round(sum(math.dist(a,b) for r in routes for a,b in segments(r['points'])),2),
            'scope':'Geometric heuristic only; not business-fact correctness, final font bounds or human preference.'}


def text_svg(x,y,value,size=16,anchor='middle'):
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}">{html.escape(value)}</text>'


def svg(model,scene,boundary,routes,w,h):
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
         '<rect width="100%" height="100%" fill="white"/>',
         '<g font-family="Arial, Microsoft YaHei, sans-serif" fill="#111" stroke-width="1.2">',
         f'<rect x="{boundary["x"]}" y="{boundary["y"]}" width="{boundary["w"]}" height="{boundary["h"]}" fill="none" stroke="#333"/>',
         text_svg(boundary['x']+14,boundary['y']+24,model['name'],16,'start')]
    for r in routes:
        p=r['points'];coords=' '.join(f'{x:.2f},{y:.2f}' for x,y in p)
        dashed=' stroke-dasharray="6 4"' if r['kind'] in ('include','extend') else ''
        out.append(f'<polyline data-relation="{r["id"]}" points="{coords}" fill="none" stroke="#333"{dashed}/>')
        if r['kind']!='association':
            a,b=p[-2:];dx,dy=b[0]-a[0],b[1]-a[1];norm=math.hypot(dx,dy) or 1;dx/=norm;dy/=norm
            size=13 if r['kind']=='generalization' else 10
            wings=[(b[0]-size*dx-sign*size*.45*dy,b[1]-size*dy+sign*size*.45*dx) for sign in (-1,1)]
            poly=[wings[0],b,wings[1]]
            if r['kind']=='generalization':
                out.append('<polygon points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in poly)+'" fill="white" stroke="#333"/>')
            else:
                out.append('<polyline points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in poly)+'" fill="none" stroke="#333"/>')
    for n in scene.values():
        x,y=n['x'],n['y'];nid=n['id']
        out.append(f'<g data-node="{nid}">')
        if n['kind']=='use_cases':
            out.append(f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="{n["w"]/2:.2f}" ry="{n["h"]/2:.2f}" fill="white" stroke="#333"/>')
            if n['extra']:
                yy=y-n['h']/2+30
                for line in n['lines']:
                    out.append(text_svg(x,yy,line));yy+=22
                separator=yy-12
                chord=n['w']/2*math.sqrt(max(0,1-((separator-y)/(n['h']/2))**2))
                out.append(f'<path d="M {x-chord:.2f},{separator:.2f} H {x+chord:.2f}" stroke="#333" fill="none"/>')
                yy+=7;out.append(text_svg(x,yy,'extension points',12));yy+=18
                for point in n['extra']:
                    for line in wrap(point):
                        out.append(text_svg(x,yy,line,13));yy+=18
            else:
                for i,line in enumerate(n['lines']):
                    out.append(text_svg(x,y+6+(i-(len(n['lines'])-1)/2)*22,line))
        elif n['actor_kind']=='external':
            out.append(f'<rect x="{x-n["w"]/2:.2f}" y="{y-n["h"]/2:.2f}" width="{n["w"]}" height="{n["h"]}" fill="white" stroke="#333"/>')
            out.append(text_svg(x,y-10,'«actor»',13))
            for i,line in enumerate(n['lines']):
                out.append(text_svg(x,y+12+i*22,line))
        else:
            out.append(f'<circle cx="{x}" cy="{y-28}" r="9" stroke="#333" fill="white"/>')
            out.append(f'<path d="M{x},{y-19} V{y+14} M{x-24},{y-6} H{x+24} M{x-18},{y+37} L{x},{y+14} L{x+18},{y+37}" fill="none" stroke="#333"/>')
            for i,line in enumerate(n['lines']):
                out.append(text_svg(x,y+60+i*22,line))
        out.append('</g>')
    for r in routes:
        if r['label']:
            x,y,w0,h0=r['label'];out.append(f'<g data-edge-label="{r["id"]}">'+text_svg(x+w0/2,y+h0/2+5,r['text'],14)+'</g>')
    out.extend(['</g>','</svg>'])
    return '\n'.join(out)


def drawio(model,scene,boundary,routes,w,h):
    root=ET.Element('mxfile',host='Clean UML',version='1.0');diagram=ET.SubElement(root,'diagram',id='usecase',name=model['name'])
    graph=ET.SubElement(diagram,'mxGraphModel',page='0',pageWidth=str(w),pageHeight=str(h))
    cells=ET.SubElement(graph,'root');ET.SubElement(cells,'mxCell',id='0');ET.SubElement(cells,'mxCell',id='1',parent='0')
    def vertex(id,value,style,x,y,width,height,parent='1'):
        cell=ET.SubElement(cells,'mxCell',id=id,value=value,style=style,vertex='1',parent=parent)
        ET.SubElement(cell,'mxGeometry',x=str(x),y=str(y),width=str(width),height=str(height),attrib={'as':'geometry'})
        return cell
    base='html=0;whiteSpace=nowrap;align=center;verticalAlign=middle;fontFamily=Arial;fontSize=16;strokeWidth=1.2;strokeColor=#333333;fillColor=#ffffff;'
    text_style='text;'+base+'strokeColor=none;fillColor=none;'
    subject=vertex('subject','',base+'container=0;',boundary['x'],boundary['y'],boundary['w'],boundary['h'])
    # mxCodec preserves cell metadata but drops arbitrary mxGraphModel attributes on save.
    subject.set('cleanUmlModel',json.dumps(model,ensure_ascii=False));subject.set('cleanUmlType','use_case')
    vertex('subject_name',model['name'],text_style+'align=left;',14,8,boundary['w']-28,22,'subject')
    for n in scene.values():
        x,y=n['x'],n['y']
        if n['kind']=='use_cases':
            cell=vertex('node_'+n['id'],'',base+'ellipse;',x-n['w']/2,y-n['h']/2,n['w'],n['h'])
            cell.set('cleanUmlName',n['name']);cell.set('cleanUmlExtensionPoints',json.dumps(n['extra'],ensure_ascii=False))
            yy=14 if n['extra'] else n['h']/2-len(n['lines'])*11
            for i,line in enumerate(n['lines']):
                vertex('name_'+n['id']+'_'+str(i),line,text_style,5,yy,n['w']-10,22,'node_'+n['id']);yy+=22
            if n['extra']:
                yy+=3
                vertex('points_heading_'+n['id'],'extension points',text_style+'fontSize=12;',8,yy,n['w']-16,18,'node_'+n['id']);yy+=18
                for j,p in enumerate(n['extra']):
                    lines=wrap(p)
                    for k,line in enumerate(lines):
                        vertex('point_'+n['id']+'_'+str(j)+'_'+str(k),line,text_style+'fontSize=13;',8,yy,n['w']-16,18,'node_'+n['id']);yy+=18
                # The compartment separator is a real, editable native line inside its use-case frame.
                sep=ET.SubElement(cells,'mxCell',id='separator_'+n['id'],style='endArrow=none;startArrow=none;strokeColor=#333333;',edge='1',parent='node_'+n['id'])
                g=ET.SubElement(sep,'mxGeometry',relative='1',attrib={'as':'geometry'})
                sy=14+len(n['lines'])*22-4;chord=n['w']/2*math.sqrt(max(0,1-((sy-n['h']/2)/(n['h']/2))**2))
                ET.SubElement(g,'mxPoint',x=str(n['w']/2-chord),y=str(sy),attrib={'as':'sourcePoint'})
                ET.SubElement(g,'mxPoint',x=str(n['w']/2+chord),y=str(sy),attrib={'as':'targetPoint'})
        elif n['actor_kind']=='human':
            cell=vertex('node_'+n['id'],'\n'.join(n['lines']),base+'shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;labelWidth='+str(n['w'])+';',x-24,y-37,48,74)
        else:
            cell=vertex('node_'+n['id'],'',base+'rounded=0;',x-n['w']/2,y-n['h']/2,n['w'],n['h'])
            vertex('actor_heading_'+n['id'],'«actor»',text_style+'fontSize=13;',5,n['h']/2-24,n['w']-10,18,'node_'+n['id'])
            for i,line in enumerate(n['lines']):
                vertex('actor_name_'+n['id']+'_'+str(i),line,text_style,5,n['h']/2-4+i*22,n['w']-10,22,'node_'+n['id'])
        cell.set('cleanUmlId',n['id']);cell.set('cleanUmlNodeKind',n['kind']);cell.set('cleanUmlName',n['name'])
    for r in routes:
        a,b=scene[r['source']],scene[r['target']];p,q=r['points'][0],r['points'][-1]
        def relative(n,point):
            if n['kind']=='actors' and n['actor_kind']=='human':
                return ((point[0]-(n['x']-24))/48,(point[1]-(n['y']-37))/74)
            return ((point[0]-(n['x']-n['w']/2))/n['w'],(point[1]-(n['y']-n['h']/2))/n['h'])
        ex,ey=relative(a,p);ix,iy=relative(b,q)
        style=f'edgeStyle=none;rounded=0;startArrow=none;endArrow=none;strokeColor=#333333;strokeWidth=1.2;exitX={ex};exitY={ey};exitPerimeter=0;entryX={ix};entryY={iy};entryPerimeter=0;'
        if r['kind'] in ('include','extend'):
            style+='dashed=1;dashPattern=6 4;endArrow=open;endFill=0;'
        elif r['kind']=='generalization':
            style+='endArrow=block;endFill=0;'
        cell=ET.SubElement(cells,'mxCell',id='relation_'+r['id'],style=style,edge='1',parent='1',source='node_'+r['source'],target='node_'+r['target'],cleanUmlKind=r['kind'])
        relation=next(item for item in model['relations'] if item['id']==r['id'])
        if relation['kind']=='extend':
            cell.set('cleanUmlExtensionLocations',json.dumps(relation['extension_points'],ensure_ascii=False))
        g=ET.SubElement(cell,'mxGeometry',relative='1',attrib={'as':'geometry'})
        arr=ET.SubElement(g,'Array',attrib={'as':'points'})
        for px,py in r['points'][1:-1]:
            ET.SubElement(arr,'mxPoint',x=str(px),y=str(py))
        if r['label']:
            x,y,width,height=r['label']
            label=vertex('label_'+r['id'],r['text'],text_style+'fontSize=14;',0,0,width,height,'relation_'+r['id'])
            geometry=label.find('mxGeometry');geometry.set('relative','1');geometry.set('x','0');geometry.set('y','0')
            # mxGraph's relative edge label origin is the route's midpoint, independent of terminal direction.
            mid_distance=sum(math.dist(u,v) for u,v in segments(r['points']))/2
            mx,my=r['points'][0]
            for (u,v) in segments(r['points']):
                length=math.dist(u,v)
                if mid_distance<=length:
                    frac=mid_distance/max(length,.001);mx=u[0]+(v[0]-u[0])*frac;my=u[1]+(v[1]-u[1])*frac;break
                mid_distance-=length
            ET.SubElement(geometry,'mxPoint',x=str(x-mx),y=str(y-my),attrib={'as':'offset'})
    return ET.tostring(root,encoding='unicode')


def verify_native(path,model):
    tree=ET.parse(path);graph=next(tree.iter('mxGraphModel'));cells={n.get('id'):n for n in tree.iter('mxCell')}
    embedded=cells['subject'].get('cleanUmlModel') or graph.get('cleanUmlModel')
    if not embedded or json.loads(embedded)!=model:
        raise ValueError('Native embedded model differs')
    expected={n['id'] for key in ('actors','use_cases') for n in model[key]}
    actual={c.get('cleanUmlId') for c in cells.values() if c.get('cleanUmlId')}
    if actual!=expected:
        raise ValueError('Native node identity differs')
    if cells['subject_name'].get('value')!=model['name']:
        raise ValueError('Native system name differs')
    for n in model['actors']:
        c=cells['node_'+n['id']]
        if c.get('cleanUmlName')!=n['name']:
            raise ValueError('Native actor name differs')
        if n.get('kind','human')=='human':
            if c.get('value')!='\n'.join(wrap(n['name'])) or 'shape=umlActor;' not in c.get('style'):
                raise ValueError('Visible native actor differs')
        else:
            visible=[v.get('value') for v in cells.values() if v.get('parent')=='node_'+n['id'] and v.get('vertex')=='1']
            if visible!=['«actor»']+wrap(n['name']):
                raise ValueError('Visible external actor text differs')
    for n in model['use_cases']:
        c=cells['node_'+n['id']]
        if c.get('cleanUmlName')!=n['name'] or json.loads(c.get('cleanUmlExtensionPoints'))!=n.get('extension_points',[]):
            raise ValueError('Native use-case text differs')
        text=[c.get('value') for c in cells.values() if c.get('parent')=='node_'+n['id'] and c.get('vertex')=='1']
        if text!=wrap(n['name'])+(['extension points']+[s for p in n.get('extension_points',[]) for s in wrap(p)] if n.get('extension_points') else []):
            raise ValueError('Visible native text differs')
    for r in model['relations']:
        c=cells['relation_'+r['id']];s=c.get('style')
        if c.get('source')!='node_'+r['source'] or c.get('target')!='node_'+r['target'] or c.get('cleanUmlKind')!=r['kind']:
            raise ValueError('Native relationship/direction differs')
        if r['kind'] in ('include','extend') and not ('dashed=1;' in s and 'endArrow=open;' in s and cells['label_'+r['id']].get('value')=='«'+r['kind']+'»'):
            raise ValueError('Native include/extend notation differs')
        if r['kind']=='generalization' and not ('endArrow=block;' in s and 'endFill=0;' in s and 'dashed=1;' not in s):
            raise ValueError('Native generalization marker differs')
        if r['kind']=='extend' and json.loads(c.get('cleanUmlExtensionLocations','null'))!=r['extension_points']:
            raise ValueError('Native extension locations differ')
    return {'status':'passed','actors':len(model['actors']),'use_cases':len(model['use_cases']),
            'relations':len(model['relations']),'scope':'Native XML identities, visible use-case text, declared extension points, terminals, directions and relation markers; not desktop GUI acceptance.'}


def generate(args,out):
    out.mkdir(parents=True);start=time.perf_counter()
    source=Path(args.model).resolve();original=source.read_bytes();(out/'input-model.json').write_bytes(original)
    try:
        raw=json.loads(original.decode('utf-8-sig'))
        model=validate(raw)
    except (ValueError,UnicodeError) as e:
        save(out/'run.json',{'status':'unsupported_or_invalid','error':str(e),'model_preserved':True,'layout_calls':0,'pngs':0,'repairs':0});print(str(e),file=sys.stderr);return 2
    here=Path(__file__).resolve().parent
    core=here if (here/'runtime').is_dir() else here.parent/'clean-uml-public44-core'
    sharp=str(Path(args.sharp_module).resolve()) if args.sharp_module else str(core/'runtime/node_modules/sharp')
    env=os.environ.copy()
    if args.fontconfig:
        env['FONTCONFIG_FILE']=str(Path(args.fontconfig).resolve())
    texts={}
    for key in ('actors','use_cases'):
        for n in model[key]:
            texts.update({f'16:{s}':{'key':f'16:{s}','text':s,'size':16} for s in wrap(n['name'])})
            for pt in n.get('extension_points',[]):
                texts.update({f'13:{s}':{'key':f'13:{s}','text':s,'size':13} for s in wrap(pt)})
    for size,text in [(12,'extension points'),(14,'«include»'),(14,'«extend»')]:
        texts[f'{size}:{text}']={'key':f'{size}:{text}','text':text,'size':size}
    texts['16:'+model['name']]={'key':'16:'+model['name'],'text':model['name'],'size':16}
    save(out/'text-input.json',list(texts.values()))
    measure=here/'measure_text.cjs'
    if not measure.is_file():
        measure=core/'runtime/scripts/measure_usecase.cjs'
    proc=subprocess.run([args.node,str(measure),sharp,str(out/'text-input.json'),str(out/'text-metrics.json')],env=env,capture_output=True,text=True,encoding='utf-8',timeout=45)
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    measured=json.loads((out/'text-metrics.json').read_text(encoding='utf-8'))['items']
    scene,boundary,w,h=placement(model,dimensions(model,measured),not args.no_role_order,not args.no_relation_columns,measured['16:'+model['name']]['width'])
    routes,trials=routing(model,scene,measured);report=audit(scene,routes)
    save(out/'model.json',model);save(out/'scene.json',{'nodes':scene,'boundary':boundary,'routes':routes,'width':w,'height':h});save(out/'review.json',report)
    (out/'diagram.svg').write_text(svg(model,scene,boundary,routes,w,h),encoding='utf-8')
    (out/'diagram.drawio').write_text(drawio(model,scene,boundary,routes,w,h),encoding='utf-8')
    native=verify_native(out/'diagram.drawio',model);save(out/'native-check.json',native)
    pngs=0
    if not args.vector_only:
        proc=subprocess.run([args.node,str(core/'runtime/scripts/rasterize.cjs'),sharp,str(out/'diagram.svg'),str(out/'diagram.png')],env=env,capture_output=True,text=True,encoding='utf-8',timeout=45)
        if proc.returncode:
            raise RuntimeError(proc.stderr)
        pngs=1
    run={'status':report['status'],'human_readability':'not_certified','role_order':not args.no_role_order,
         'relation_columns':not args.no_relation_columns,'layout_calls':1,'route_trials':trials,
         'text_measurement_calls':1,'browser_measurements':0,'pngs':pngs,'repairs':0,
         'seconds':round(time.perf_counter()-start,6),'model_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
         'geometry':report['counts'],'width':w,'height':h,'native':native['status']}
    save(out/'run.json',run)
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>'+html.escape(model['name'])+'</title><style>body{font:16px Arial;margin:24px}img{max-width:100%;height:auto}</style><p><a href="diagram.drawio">Editable draw.io</a> · <a href="diagram.svg">SVG</a> · <a href="review.json">Review</a></p><img src="diagram.svg" alt="'+html.escape(model['name'],quote=True)+'">',encoding='utf-8')
    print(json.dumps(run,ensure_ascii=False));return 0 if report['status']=='geometry_pass' else 2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('model');p.add_argument('-o','--output',required=True)
    p.add_argument('--no-role-order',action='store_true');p.add_argument('--no-relation-columns',action='store_true')
    p.add_argument('--node',default='node');p.add_argument('--sharp-module');p.add_argument('--fontconfig')
    p.add_argument('--vector-only',action='store_true')
    args=p.parse_args();out=Path(args.output).resolve()
    if out.exists():
        p.error('Output exists; use a new directory')
    try:
        return generate(args,out)
    except (OSError,RuntimeError,subprocess.SubprocessError) as e:
        if out.is_dir():
            save(out/'run.json',{'status':'execution_failure','error':str(e),'repairs':0,'human_readability':'not_certified'})
        print(str(e),file=sys.stderr);return 3


if __name__=='__main__':
    sys.exit(main())
