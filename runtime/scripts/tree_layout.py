"""Top-down layout with measured endpoint spacing; preserve complete UML graph."""
import argparse,json,sys,subprocess,os,xml.etree.ElementTree as ET
from pathlib import Path
from structured_layout import graph,draw as base_draw,key,NS
from audit import audit_svg
from route_metrics import measure

def hits_box(a,b,box):
 lo,hi=0.,1.
 for axis in (0,1):
  delta=b[axis]-a[axis]
  if abs(delta)<1e-9:
   if not box[axis]<a[axis]<box[axis+2]:return False
  else:
   first=(box[axis]-a[axis])/delta;last=(box[axis+2]-a[axis])/delta
   lo=max(lo,min(first,last));hi=min(hi,max(first,last))
 return hi-lo>1e-7 and hi>1e-7 and lo<1-1e-7

def simplify(g):
 """Shortcut elbows only when boxes, labels and route intersections stay clear."""
 nodes=[(n['x'],n['y'],n['x']+n['width'],n['y']+n['height']) for n in g['children']]
 labels=[(l['x']-3,l['y']-3,l['x']+l['width']+3,l['y']+l['height']+3) for e in g['edges'] for l in e.get('labels',[])]
 edges=[]
 for e in g['edges']:
  s=e['sections'][0];edges.append({'index':int(e['id'].split('_')[1]),'points':[(p['x'],p['y']) for p in [s['startPoint']]+s.get('bendPoints',[])+[s['endPoint']]]})
 scene={'width':g['width'],'height':g['height'],'edges':edges};base=measure(scene)
 owner={n['id']:n['id'] for n in g['children']}
 for n in g['children']:
  for port in n.get('ports',[]):owner[port['id']]=n['id']
 for original,edge in zip(g['edges'],edges):
  if owner[original['sources'][0]]==owner[original['targets'][0]]:continue
  changed=True
  while changed:
   changed=False;p=edge['points']
   for gap in range(len(p)-1,1,-1):
    for i in range(len(p)-gap):
     j=i+gap
     boxes=list(labels)
     for b in nodes:
      attached=any(b[0]-1e-6<=q[0]<=b[2]+1e-6 and b[1]-1e-6<=q[1]<=b[3]+1e-6 for q in [p[i],p[j]])
      margin=0 if attached else 8;boxes.append((b[0]-margin,b[1]-margin,b[2]+margin,b[3]+margin))
     if any(hits_box(p[i],p[j],b) for b in boxes):continue
     trial=p[:i+1]+p[j:];edge['points']=trial;m=measure(scene)
     if all(m[k]<=base[k] for k in ('proper_crossings','other_contacts','shared_track_length')):
      base=m;changed=True;break
     edge['points']=p
    if changed:break
 for e,route in zip(g['edges'],edges):e['sections'][0]['bendPoints']=[{'x':x,'y':y} for x,y in route['points'][1:-1]]
 return g

def draw(model,metrics,g):
 svg,scene=base_draw(model,metrics,g);root=ET.fromstring(svg)
 for m in model['nodes']:
  nid=m['id'];n=scene['nodes'][nid];group=root.find(f'.//*[@id="node_{nid}"]');rect=group.find('{'+NS+'}rect');delta=n['width']-float(rect.get('width'));rect.set('width',str(n['width']))
  for line in group.findall('{'+NS+'}line'):line.set('x2',str(n['x']+n['width']))
  header=48 if m['kind'] in ('interface','enum') else 28
  for t in group.findall('{'+NS+'}text'):
   if float(t.get('y'))<n['y']+header:t.set('x',str(float(t.get('x'))+delta/2))
 return ET.tostring(root,encoding='utf-8',xml_declaration=True),scene

def tree_graph(model,metrics,routing='POLYLINE',sized=True,backbone=True,root=None,rank_policy='uniform'):
 g=graph(model,metrics,direction='DOWN',loop_ports=True,orient='bfs' if backbone else False,root=root,rank_policy=rank_policy)
 g['layoutOptions'].update({'elk.edgeRouting':routing,'elk.spacing.nodeSelfLoop':'100','elk.layered.spacing.nodeNodeBetweenLayers':'60','elk.spacing.nodeNode':'48'})
 for n,m in zip(g['children'],model['nodes']):
  fields=[s for s in m['members'] if '(' not in s];methods=[s for s in m['members'] if '(' in s]
  n['height']=(48 if m['kind'] in ('interface','enum') else 28)+len(m['members'])*22+12+(6 if fields and methods else 0)
  sizes={'sources':[],'targets':[]}
  for e in g['edges']:
   for end in sizes:
    if n['id'] in e[end]:
     side=('source' if end=='sources' else 'target')
     if e['semanticReverse']:side='target' if side=='source' else 'source'
     sizes[end].append(max([label['width']+32 for label in e['labels'] if label['id'].endswith('_'+side)]+[36]))
  if sized:n['width']=max(n['width'],max((len(v)*max(v) if v else 0) for v in sizes.values())+32)
  n['layoutOptions']['elk.spacing.portPort']='32'
 return g

