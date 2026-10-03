"""Joint straight-route and label placement; bounded root centering."""
import copy,math
from tree_layout import draw,hits_box
from audit import audit_svg
from marker_labels import findings
from route_metrics import measure

def points(e):
 s=e['sections'][0];return [s['startPoint']]+s.get('bendPoints',[])+[s['endPoint']]
def box(l,pad=0):return (l['x']-pad,l['y']-pad,l['x']+l['width']+pad,l['y']+l['height']+pad)
def overlap(a,b):return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])

def relabel(g,e):
 """Place full label groups next to their own segment, preserving semantic side."""
 ps=points(e);segs=[((a['x'],a['y']),(b['x'],b['y'])) for a,b in zip(ps,ps[1:])]
 nodes=[box(n,3) for n in g['children']]
 other=[box(l,3) for edge in g['edges'] if edge['id']!=e['id'] for l in edge.get('labels',[])]
 routes=[((a['x'],a['y']),(b['x'],b['y'])) for edge in g['edges'] for a,b in zip(points(edge),points(edge)[1:])]
 for l in e.get('labels',[]):
  side=l['id'].rsplit('_',1)[-1]
  tail=(side=='source')!=e.get('semanticReverse',False)
  segments=segs if side=='center' or tail else [(b,a) for a,b in reversed(segs)]
  candidates=[]
  for a,b in (segments if side=='center' else segments[:1]):
   dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
   if length<1:continue
   ux,uy=dx/length,dy/length;nx,ny=-uy,ux
   distances=[length*.5,length*.35,length*.65] if side=='center' else [min(d,length*.45) for d in (30,46,64,84)]
   for d in distances:
    for sign in (1,-1):
     offset=abs(nx)*l['width']/2+abs(ny)*l['height']/2+8
     cx=a[0]+ux*d+sign*nx*offset;cy=a[1]+uy*d+sign*ny*offset
     candidates.append((cx-l['width']/2,cy-l['height']/2))
  placed=False
  for x,y in candidates:
   bounds=(x-2,y-2,x+l['width']+2,y+l['height']+2)
   if x<0 or y<0 or x+l['width']>g['width'] or y+l['height']>g['height']:continue
   if any(overlap(bounds,b) for b in nodes+other):continue
   if any(hits_box(a,b,bounds) for a,b in routes):continue
   l['x']=x;l['y']=y;other.append(bounds);placed=True;break
  if not placed:return False
 return True

def safe(model,metrics,old,new):
 try:before,bs=draw(model,metrics,old);after,ns=draw(model,metrics,new)
 except ValueError:return False
 a,b=measure(bs),measure(ns)
 return (not audit_svg(after,model)['findings'] and len(findings(after))<=len(findings(before)) and all(b[k]<=a[k] for k in ('proper_crossings','other_contacts','shared_track_length')))

def improve(model,metrics,g,center=True,straight=True):
 events=[]
 # Place top sources above the span of their directly connected descendants.
 if center:
  incoming={x for e in g['edges'] for x in e['targets']}
  for n in list(g['children']):
   if n['id'] in incoming or n.get('ports'):continue
   incident=[e for e in g['edges'] if n['id'] in e['sources']]
   targets={x for e in incident for x in e['targets']}
   children=[c for c in g['children'] if c['id'] in targets and c['id']!=n['id']]
   if len(children)<2:continue
   desired=(min(c['x']+c['width']/2 for c in children)+max(c['x']+c['width']/2 for c in children))/2
   delta=desired-(n['x']+n['width']/2)
   if abs(delta)<8:continue
   trial=copy.deepcopy(g);node=next(c for c in trial['children'] if c['id']==n['id']);node['x']+=delta
   if node['x']<0 or node['x']+node['width']>g['width']:continue
   changed=[]
   for e in trial['edges']:
    if n['id'] in e['sources']:
     e['sections'][0]['startPoint']['x']+=delta
     # Move the endpoint-side labels with the node before joint route placement.
     for l in e.get('labels',[]):
      side=l['id'].rsplit('_',1)[-1]
      if (side=='source')!=e.get('semanticReverse',False) and side!='center':l['x']+=delta
     a,b=e['sections'][0]['startPoint'],e['sections'][0]['endPoint']
     obstacles=[c for c in trial['children'] if hits_box((a['x'],a['y']),(b['x'],b['y']),box(c,0))]
     if not obstacles:e['sections'][0]['bendPoints']=[]
     else:
      alternatives=[]
      for obstacle in obstacles:
       for x in (obstacle['x']-14,obstacle['x']+obstacle['width']+14):
        bends=[{'x':x,'y':obstacle['y']-14},{'x':x,'y':obstacle['y']+obstacle['height']+14}]
        route=[a]+bends+[b]
        if all(not hits_box((u['x'],u['y']),(v['x'],v['y']),box(c,0)) for u,v in zip(route,route[1:]) for c in trial['children']):
         alternatives.append((sum(math.hypot(u['x']-v['x'],u['y']-v['y']) for u,v in zip(route,route[1:])),bends))
      if alternatives:e['sections'][0]['bendPoints']=min(alternatives,key=lambda x:x[0])[1]
     changed.append(e)
   placements=[relabel(trial,e) for e in changed]
   joint_used=False
   valid=all(placements) and safe(model,metrics,g,trial)
   if not valid:
    from joint_labels import solve
    if solve(trial,model=model) and safe(model,metrics,g,trial):valid=True;joint_used=True
   if valid:
    g=trial;events.append({'kind':'root_center','node':n['id'],'dx':delta,'joint_marker_labels':joint_used})
   else:events.append({'kind':'root_center_rejected','node':n['id'],'placements':placements,'findings':audit_svg(draw(model,metrics,trial)[0],model)['findings'],'metrics':measure(draw(model,metrics,trial)[1])})
 if straight:
  for original in list(g['edges']):
   if original['sources']==original['targets'] or any(x.startswith('port_') for x in original['sources']):continue
   trial=copy.deepcopy(g);e=next(e for e in trial['edges'] if e['id']==original['id']);e['sections'][0]['bendPoints']=[]
   if relabel(trial,e) and safe(model,metrics,g,trial):
    # Straightening has no reason to increase the route length or bend count.
    old=measure(draw(model,metrics,g)[1]);new=measure(draw(model,metrics,trial)[1])
    if new['bends']<=old['bends'] and new['route_length']<=old['route_length']+.01:
     g=trial;events.append({'kind':'straight_or_relabel','edge':e['id']})
 return g,events
