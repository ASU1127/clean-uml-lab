"""Opt-in relocation of auxiliary weak-relation components with bounded routing.
Preserves all facts. Membership is topological, not a business service classifier.
"""
import copy,math,itertools
from fan_layout import points,box,overlap,safe
from tree_layout import draw,hits_box
from joint_labels import solve
from route_metrics import measure

def groups(m):
 eligible={n['id'] for n in m['nodes'] if all(r['kind'] in ('dependency','realization','generalization') for r in m['relations'] if n['id'] in (r['source'],r['target']))};adj={n:set() for n in eligible}
 for r in m['relations']:
  if r['source'] in eligible and r['target'] in eligible:adj[r['source']].add(r['target']);adj[r['target']].add(r['source'])
 result=[];seen=set()
 for n in sorted(eligible):
  if n in seen:continue
  comp=[n];seen.add(n)
  for x in comp:
   for y in sorted(adj[x]):
    if y not in seen:seen.add(y);comp.append(y)
  # A dependency-only singleton is also an auxiliary component. It was
  # previously skipped, leaving isolated service classes on long rank routes.
  incident=[r for r in m['relations'] if n in (r['source'],r['target'])]
  if len(comp)>1 or (incident and all(r['kind']=='dependency' for r in incident)):
   result.append(comp)
 return result

def xy(p):return (p['x'],p['y'])
def pt(x,y):return {'x':x,'y':y}
def center(n):return n['x']+n['width']/2,n['y']+n['height']/2

def route_options(a,b,nodes):
 ax,ay=center(a);bx,by=center(b);dx,dy=bx-ax,by-ay
 def ray(n,x,y):
  cx,cy=center(n);s=min(n['width']/2/abs(x) if x else math.inf,n['height']/2/abs(y) if y else math.inf);return pt(cx+x*s,cy+y*s)
 routes=[[ray(a,dx,dy),ray(b,-dx,-dy)]]
 for x in sorted({(ax+bx)/2,*[n['x']-24 for n in nodes],*[n['x']+n['width']+24 for n in nodes]}):
  pa=pt(a['x']+(a['width'] if x>ax else 0),ay);pb=pt(b['x']+(b['width'] if x>bx else 0),by)
  routes.append([pa,pt(x,ay),pt(x,by),pb])
 for y in sorted({(ay+by)/2,*[n['y']-24 for n in nodes],*[n['y']+n['height']+24 for n in nodes]}):
  pa=pt(ax,a['y']+(a['height'] if y>ay else 0));pb=pt(bx,b['y']+(b['height'] if y>by else 0))
  routes.append([pa,pt(ax,y),pt(bx,y),pb])
 valid=[]
 for ps in routes:
  if any(p['x']<12 or p['y']<12 for p in ps):continue
  if any(hits_box(xy(u),xy(v),box(n)) for u,v in zip(ps,ps[1:]) for n in nodes):continue
  # Discard repeated adjacent vertices before drawing endpoint markers.
  ps=[p for i,p in enumerate(ps) if i==0 or math.dist(xy(p),xy(ps[i-1]))>1e-6]
  if len(ps)>1:valid.append(ps)
 return valid

def improve(m,metrics,g,reroute=True):
 # Cache only within this bounded search: no stale geometry across calls.
 from cached_route_metrics import CachedMeasure
 measure=CachedMeasure()
 initial=measure(draw(m,metrics,g)[1]);best=copy.deepcopy(g);bestm=initial;stats={'placements':0,'routable':0,'shorter':0,'label_success':0};accepted=[]
 for comp in groups(m):
  nodes={n['id']:n for n in g['children']};links={n:set() for n in comp};degree=dict.fromkeys(comp,0)
  for r in m['relations']:
   a,b=r['source'],r['target']
   if a not in links or b not in links:continue
   if r['kind'] in ('realization','generalization'):a,b=b,a
   if b not in links[a]:links[a].add(b);degree[b]+=1
  order=[];ready=sorted(n for n in comp if degree[n]==0)
  while ready:
   n=ready.pop(0);order.append(n)
   for b in sorted(links[n]):
    degree[b]-=1
    if degree[b]==0:ready.append(b)
  if len(order)!=len(comp):continue
  width=max(nodes[n]['width'] for n in comp);height=sum(nodes[n]['height'] for n in comp)+72*(len(comp)-1)
  external={r[s] for r in m['relations'] if any(r[k] in comp for k in ['source','target']) for s in ['source','target']}-set(comp);remaining=[n for n in g['children'] if n['id'] not in comp]
  xs={24,*[n['x'] for n in remaining],*[n['x']+n['width']+48 for n in remaining],*[n['x']-width-48 for n in remaining]};ys={24,*[n['y']+n['height']+60 for n in remaining],*[n['y']-height-60 for n in remaining]}
  candidates=sorted(itertools.product(xs,ys),key=lambda p:sum(math.dist((p[0]+width/2,p[1]+height/2),center(nodes[n])) for n in external))
  for x,y in candidates:
   if x<24 or y<24 or x+width>g['width']-24 or y+height>g['height']-24:continue
   if any(overlap((x-16,y-16,x+width+16,y+height+16),box(n,16)) for n in remaining):continue
   if stats['placements']>=100:break
   stats['placements']+=1
   t=copy.deepcopy(g);tn={n['id']:n for n in t['children']};cy=y
   for n in order:tn[n]['x']=x+(width-tn[n]['width'])/2;tn[n]['y']=cy;cy+=tn[n]['height']+72
   if any(tn[r['target']]['y']+tn[r['target']]['height']>=tn[r['source']]['y'] for r in m['relations'] if r['kind'] in ('generalization','realization')):continue
   changed=[e for e in t['edges'] if any(m['relations'][int(e['id'].split('_')[1])][s] in comp for s in ['source','target'])];fixed=[e for e in t['edges'] if e not in changed]
   if any(hits_box(xy(u),xy(v),box(tn[n])) for e in fixed for u,v in zip(points(e),points(e)[1:]) for n in comp):continue
   chosen=list(fixed);ok=True
   for e in sorted(changed,key=lambda e:(not all(k in comp for k in [e['sources'][0],e['targets'][0]]),e['id'])):
    a,b=e['sources'][0],e['targets'][0]
    options=route_options(tn[a],tn[b],t['children'])
    if not reroute:options=[ps for ps in options if len(ps)==2]
    candidates2=[]
    for ps in options:
     scene={'width':t['width'],'height':t['height'],'edges':[{'index':int(f['id'].split('_')[1]),'points':[xy(p) for p in points(f)]} for f in chosen]+[{'index':int(e['id'].split('_')[1]),'points':[xy(p) for p in ps]}]};rm=measure(scene)
     if any(rm[k]>initial[k] for k in ['proper_crossings','other_contacts','shared_track_length']):continue
     candidates2.append((len(ps),sum(math.dist(xy(u),xy(v)) for u,v in zip(ps,ps[1:])),ps))
    if not candidates2:ok=False;break
    ps=min(candidates2,key=lambda z:z[:2])[2];e['sections'][0].update(startPoint=ps[0],endPoint=ps[-1],bendPoints=ps[1:-1]);chosen.append(e)
   if not ok:continue
   stats['routable']+=1;rm=measure(draw(m,metrics,t)[1])
   if rm['route_length']>=bestm['route_length']-40 or rm['route_length']>initial['route_length']*.95 or rm['bends']>initial['bends']:continue
   stats['shorter']+=1
   if not solve(t,limit=5000,model=m) or not safe(m,metrics,g,t):continue
   stats['label_success']+=1;best=t;bestm=rm;accepted.append({'group':comp,'x':x,'y':y,'metrics':rm})
 return best,{'before':initial,'after':bestm,'stats':stats,'accepted':accepted}
