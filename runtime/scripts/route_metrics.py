"""Geometry diagnostics, not a human-readability score. Coordinates in SVG pixels."""
import json,math,argparse
from itertools import combinations
from pathlib import Path

def measure(scene):
 edges=[]
 for original in scene['edges']:
  e=dict(original)
  if 'points' not in e:
   a,b=e['source_port'],e['target_port'];e['points']=[a,[e['track'],a[1]],[e['track'],b[1]],b]
  edges.append(e)
 crossings=[];contacts=[];overlap=0;length=0;bends=0
 for e in edges:
  points=e['points'];length+=sum(math.dist(a,b) for a,b in zip(points,points[1:]));bends+=max(0,len(points)-2)
 for e,f in combinations(edges,2):
  seen=set()
  for a,b in zip(e['points'],e['points'][1:]):
   for c,d in zip(f['points'],f['points'][1:]):
    def cross(u,v):return u[0]*v[1]-u[1]*v[0]
    u=(b[0]-a[0],b[1]-a[1]);v=(d[0]-c[0],d[1]-c[1]);q=(c[0]-a[0],c[1]-a[1]);den=cross(u,v);norm=math.hypot(*u)
    if norm<1e-9:continue
    if abs(den)<1e-9:
     if abs(cross(q,u))<1e-6:
      tc=(q[0]*u[0]+q[1]*u[1])/(norm*norm);td=((d[0]-a[0])*u[0]+(d[1]-a[1])*u[1])/(norm*norm)
      overlap+=max(0,min(1,max(tc,td))-max(0,min(tc,td)))*norm
     continue
    t=cross(q,v)/den;s=cross(q,u)/den;x,y=a[0]+t*u[0],a[1]+t*u[1]
    if -1e-9<=t<=1+1e-9 and -1e-9<=s<=1+1e-9:
     point=(round(x,6),round(y,6))
     if point in seen:continue
     seen.add(point)
     # Shared node attachment is not a crossing. Contacts elsewhere are retained.
     if any(math.dist(point,p)<1e-6 for p in (e['points'][0],e['points'][-1])) and any(math.dist(point,p)<1e-6 for p in (f['points'][0],f['points'][-1])):continue
     proper=1e-9<t<1-1e-9 and 1e-9<s<1-1e-9
     (crossings if proper else contacts).append({'edges':[e['index'],f['index']],'point':point})
 width,height=scene['width'],scene['height']
 return {'width':width,'height':height,'area':round(width*height),'aspect_ratio':round(max(width,height)/min(width,height),3),'proper_crossings':len(crossings),'other_contacts':len(contacts),'shared_track_length':round(overlap,2),'route_length':round(length,2),'bends':bends,'crossing_locations':crossings,'contact_locations':contacts}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('scene',type=Path);p.add_argument('--out',type=Path);a=p.parse_args();s=json.dumps(measure(json.loads(a.scene.read_text(encoding='utf-8-sig'))),ensure_ascii=False,indent=2)
 if a.out:a.out.write_text(s,encoding='utf-8')
 else:print(s)
