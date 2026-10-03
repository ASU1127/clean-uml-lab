"""Bounded attachment alternatives for intrinsic-width crowded class boxes.

Keep node dimensions, all facts and existing obstacle-corner routes unchanged.
Add direct and single-elbow paths from three well-separated face attachments.
"""
import math
from region_routes import options as corner_options
from auxiliary_groups import center,xy,pt
from fan_layout import box
from tree_layout import hits_box


def options(a,b,nodes):
    routes=corner_options(a,b,nodes)
    def ports(node,opposite):
        cx,cy=center(node);ox,oy=center(opposite)
        dx,dy=ox-cx,oy-cy
        if abs(dx)/node['width']>=abs(dy)/node['height']:
            x=node['x']+(node['width'] if dx>0 else 0)
            return [pt(x,node['y']+node['height']*f) for f in (.25,.5,.75)]
        y=node['y']+(node['height'] if dy>0 else 0)
        return [pt(node['x']+node['width']*f,y) for f in (.25,.5,.75)]
    for start in ports(a,b):
        for end in ports(b,a):
            routes.append([start,end])
            routes.append([start,pt(start['x'],end['y']),end])
            routes.append([start,pt(end['x'],start['y']),end])
    seen=set();valid=[]
    for ps in routes:
        ps=[p for i,p in enumerate(ps) if i==0 or math.dist(xy(p),xy(ps[i-1]))>1e-6]
        if len(ps)<2 or any(p['x']<12 or p['y']<12 for p in ps):continue
        if any(hits_box(xy(u),xy(v),box(n)) for u,v in zip(ps,ps[1:]) for n in nodes):continue
        key=tuple((round(p['x'],7),round(p['y'],7)) for p in ps)
        if key not in seen:seen.add(key);valid.append(ps)
    return valid
