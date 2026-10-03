"""Bounded joint label solver with semantic marker clearance."""
import math
from tree_layout import hits_box
from fan_layout import points,box,overlap
from qualifier_layout import edge_geometry

def marker_boxes(g,model,qualifier_clearance=True):
 result=[]
 for e in g['edges']:
  relation=model['relations'][int(e['id'].split('_')[1])];kind=relation['kind'];ps=points(e)
  if e.get('semanticReverse',False):ps=list(reversed(ps))
  if e.get('qualifier_sizes'):
   visible,qualifiers=edge_geometry(g,e,model)
   ps=[dict(x=x,y=y) for x,y in visible]
   if qualifier_clearance:result.extend((q['x']-3,q['y']-3,q['x']+q['width']+3,q['y']+q['height']+3) for q in qualifiers.values())
  specs=[]
  if kind in ('composition','aggregation'):specs.append((ps[0],ps[1],16,5,8))
  elif kind in ('generalization','realization'):specs.append((ps[-1],ps[-2],12,6,12))
  elif kind=='dependency':specs.append((ps[-1],ps[-2],10,5,10))
  navigation=relation.get('navigability','--')
  if navigation in ('<-','<->'):specs.append((ps[0],ps[1],10,5,10))
  if navigation in ('->','<->'):specs.append((ps[-1],ps[-2],10,5,10))
  for p,q,depth,width,d in specs:
   dx,dy=q['x']-p['x'],q['y']-p['y'];length=math.hypot(dx,dy)
   if length<1:continue
   ux,uy=dx/length,dy/length;nx,ny=-uy,ux
   pts=[(p['x'],p['y']),(p['x']+ux*depth,p['y']+uy*depth)]
   pts += [(p['x']+ux*d+sign*nx*width,p['y']+uy*d+sign*ny*width) for sign in (-1,1)]
   result.append((min(x for x,y in pts)-4,min(y for x,y in pts)-4,max(x for x,y in pts)+4,max(y for x,y in pts)+4))
 return result

def solve(g,limit=10000,model=None,preserve_edges=(),qualifier_clearance=True):
 labels=[(e,l) for e in g['edges'] for l in e.get('labels',[])]
 nodes=[box(n,3) for n in g['children']]
 if model is not None:
  try:nodes+=marker_boxes(g,model,qualifier_clearance=qualifier_clearance)
  except ValueError:return False
 routes=[((a['x'],a['y']),(b['x'],b['y'])) for e in g['edges'] for a,b in zip(points(e),points(e)[1:])]
 options=[]
 for e,l in labels:
  side=l['id'].rsplit('_',1)[-1];tail=(side=='source')!=e.get('semanticReverse',False)
  ps=points(e);segs=[((a['x'],a['y']),(b['x'],b['y'])) for a,b in zip(ps,ps[1:])]
  if side!='center' and not tail:segs=[(b,a) for a,b in reversed(segs)]
  candidates=[]
  # Unchanged routes may have valid placements outside the sampled offsets,
  # especially self-loops. Retain them only when the caller confirms the route
  # is unchanged, and recheck them against all new geometry and markers.
  if e['id'] in preserve_edges:
   x,y=l['x'],l['y'];bounds=(x-2,y-2,x+l['width']+2,y+l['height']+2)
   if x>=0 and y>=0 and bounds[2]<=g['width'] and bounds[3]<=g['height'] and not any(overlap(bounds,n) for n in nodes) and not any(hits_box(a,b,bounds) for a,b in routes):
    candidates.append((x,y,bounds))
  for a,b in (segs if side=='center' else segs[:1]):
   dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
   if length<1:continue
   ux,uy=dx/length,dy/length;nx,ny=-uy,ux
   distances=[length*f for f in (.5,.35,.65,.2,.8)] if side=='center' else [min(d,length*.45) for d in (30,46,64,84,110,140,16)]
   for d in distances:
    for sign in (1,-1):
     offset=abs(nx)*l['width']/2+abs(ny)*l['height']/2+8
     x=a[0]+ux*d+sign*nx*offset-l['width']/2;y=a[1]+uy*d+sign*ny*offset-l['height']/2
     bounds=(x-2,y-2,x+l['width']+2,y+l['height']+2)
     if x<0 or y<0 or bounds[2]>g['width'] or bounds[3]>g['height']:continue
     if any(overlap(bounds,n) for n in nodes) or any(hits_box(a,b,bounds) for a,b in routes):continue
     candidate=(x,y,bounds)
     if candidate not in candidates:candidates.append(candidate)
  if not candidates:return False
  options.append(candidates)
 chosen={};budget=[limit]
 def search(todo):
  if not todo:return True
  budget[0]-=1
  if budget[0]<0:return False
  available={i:[c for c in options[i] if all(not overlap(c[2],p[2]) for p in chosen.values())] for i in todo}
  i=min(todo,key=lambda i:(len(available[i]),labels[i][1]['id']))
  for c in available[i]:
   chosen[i]=c
   if search(todo-{i}):return True
   del chosen[i]
  return False
 if not search(set(range(len(labels)))):return False
 for i,(_,l) in enumerate(labels):l['x'],l['y']=chosen[i][:2]
 return True

