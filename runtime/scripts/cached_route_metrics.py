"""Per-search bounded pair cache; reproduces route_metrics accumulation order."""
import math
from itertools import combinations


def pair_terms(e, f):
    crossings, contacts, overlaps = [], [], []
    seen = set()
    def cross(u, v): return u[0]*v[1]-u[1]*v[0]
    for a, b in zip(e, e[1:]):
        for c, d in zip(f, f[1:]):
            u=(b[0]-a[0],b[1]-a[1]);v=(d[0]-c[0],d[1]-c[1]);q=(c[0]-a[0],c[1]-a[1]);den=cross(u,v);norm=math.hypot(*u)
            if norm<1e-9:continue
            if abs(den)<1e-9:
                if abs(cross(q,u))<1e-6:
                    tc=(q[0]*u[0]+q[1]*u[1])/(norm*norm);td=((d[0]-a[0])*u[0]+(d[1]-a[1])*u[1])/(norm*norm)
                    overlaps.append(max(0,min(1,max(tc,td))-max(0,min(tc,td)))*norm)
                continue
            t=cross(q,v)/den;s=cross(q,u)/den;x,y=a[0]+t*u[0],a[1]+t*u[1]
            if -1e-9<=t<=1+1e-9 and -1e-9<=s<=1+1e-9:
                point=(round(x,6),round(y,6))
                if point in seen:continue
                seen.add(point)
                if any(math.dist(point,p)<1e-6 for p in (e[0],e[-1])) and any(math.dist(point,p)<1e-6 for p in (f[0],f[-1])):continue
                proper=1e-9<t<1-1e-9 and 1e-9<s<1-1e-9
                (crossings if proper else contacts).append(point)
    return crossings, contacts, overlaps


class CachedMeasure:
    def __init__(self, capacity=16384):
        self.cache={}
        self.capacity=capacity
        self.hits=0
        self.misses=0

    def __call__(self, scene):
        edges=[];crossings=[];contacts=[];overlap=0;length=0;bends=0
        for e in scene['edges']:
            if 'points' in e:ps=e['points']
            else:
                a,b=e['source_port'],e['target_port'];ps=[a,[e['track'],a[1]],[e['track'],b[1]],b]
            ps=tuple(tuple(p) for p in ps)
            edges.append((e['index'],ps))
            length+=sum(math.dist(a,b) for a,b in zip(ps,ps[1:]));bends+=max(0,len(ps)-2)
        for (i,e),(j,f) in combinations(edges,2):
            key=(e,f)
            terms=self.cache.get(key)
            if terms is None:
                self.misses+=1;terms=pair_terms(e,f)
                if self.capacity>0:
                    if len(self.cache)>=self.capacity:self.cache.pop(next(iter(self.cache)))
                    self.cache[key]=terms
            else:self.hits+=1
            cs,ts,os=terms
            crossings.extend({'edges':[i,j],'point':p} for p in cs)
            contacts.extend({'edges':[i,j],'point':p} for p in ts)
            # Replay individual contributions, preserving floating-point order.
            for term in os:overlap+=term
        width,height=scene['width'],scene['height']
        return {'width':width,'height':height,'area':round(width*height),'aspect_ratio':round(max(width,height)/min(width,height),3),'proper_crossings':len(crossings),'other_contacts':len(contacts),'shared_track_length':round(overlap,2),'route_length':round(length,2),'bends':bends,'crossing_locations':crossings,'contact_locations':contacts}
