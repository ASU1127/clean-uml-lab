import copy,json,sys,subprocess,os
from pathlib import Path
from tree_layout import draw
from audit import audit_svg
from route_metrics import measure

def normalize(g):
 coords=[]
 for n in g['children']:coords += [(n['x'],n['y']),(n['x']+n['width'],n['y']+n['height'])]
 for e in g['edges']:
  for s in e['sections']:coords += [(p['x'],p['y']) for p in [s['startPoint'],s['endPoint']]+s.get('bendPoints',[])]
  for l in e.get('labels',[]):coords += [(l['x'],l['y']),(l['x']+l['width'],l['y']+l['height'])]
 dx=max(0,24-min(x for x,y in coords))
 for n in g['children']:n['x']+=dx
 for e in g['edges']:
  for s in e['sections']:
   for p in [s['startPoint'],s['endPoint']]+s.get('bendPoints',[]):p['x']+=dx
  for l in e.get('labels',[]):l['x']+=dx
 g['width']=max(x for x,y in coords)+dx+24

def improve(model,metrics,g):
 families={};degree={n['id']:0 for n in model['nodes']};events=[]
 for i,r in enumerate(model['relations']):
  degree[r['source']]+=1;degree[r['target']]+=1
  if r['kind'] in ('generalization','realization'):families.setdefault((r['target'],r['kind']),[]).append((r['source'],i))
 for (parent,kind),children in families.items():
  if len(children)<2 or any(degree[c]!=1 for c,i in children):
   events.append({'parent':parent,'status':'not_applicable','reason':'requires two or more leaf subtypes'});continue
  candidate=copy.deepcopy(g);nodes={n['id']:n for n in candidate['children']};pb=nodes[parent];bs=[nodes[c] for c,i in children]
  delta=pb['x']+pb['width']/2-(min(n['x'] for n in bs)+max(n['x']+n['width'] for n in bs))/2
  if abs(delta)<1e-6:continue
  for c,i in children:
   nodes[c]['x']+=delta;e=next(e for e in candidate['edges'] if e['id']==f'edge_{i}')
   for s in e['sections']:
    point=s['endPoint'] if e['semanticReverse'] else s['startPoint'];point['x']+=delta;s['bendPoints']=[]
  normalize(candidate)
  before_svg,before_scene=draw(model,metrics,g);svg,scene=draw(model,metrics,candidate);a=measure(before_scene);b=measure(scene)
  warnings=audit_svg(svg,model)['findings'];old=audit_svg(before_svg,model)['findings']
  accepted=not warnings and not old and all(b[k]<=a[k] for k in ['proper_crossings','other_contacts','shared_track_length'])
  events.append({'parent':parent,'status':'accepted' if accepted else 'rejected','shift_px':delta,'warnings':warnings,'before':a,'after':b})
  if accepted:g=candidate
 return g,events

