"""Obstacle-corner visibility proposals with at most one natural diagonal bend."""
import math
from auxiliary_groups import route_options,center,xy,pt
from fan_layout import box
from tree_layout import hits_box

def options(a,b,nodes):
    original=route_options(a,b,nodes)
    ax,ay=center(a);bx,by=center(b)
    def ray(n,target):
        cx,cy=center(n);dx,dy=target[0]-cx,target[1]-cy
        if abs(dx)+abs(dy)<1e-7:return None
        scale=min(n['width']/2/abs(dx) if dx else math.inf,n['height']/2/abs(dy) if dy else math.inf)
        return pt(cx+scale*dx,cy+scale*dy)
    corners={(ax,by),(bx,ay)}
    for n in nodes:
        x0,y0,x1,y1=box(n,16)
        corners.update(((x0,y0),(x0,y1),(x1,y0),(x1,y1)))
    for c in sorted(corners):
        start,end=ray(a,c),ray(b,c)
        if start is None or end is None:continue
        ps=[start,pt(*c),end]
        if any(p['x']<12 or p['y']<12 for p in ps):continue
        if any(math.dist(xy(u),xy(v))<1 for u,v in zip(ps,ps[1:])):continue
        if any(hits_box(xy(u),xy(v),box(n)) for u,v in zip(ps,ps[1:]) for n in nodes):continue
        original.append(ps)
    seen=set();result=[]
    for ps in original:
        key=tuple((round(p['x'],7),round(p['y'],7)) for p in ps)
        if key not in seen:seen.add(key);result.append(ps)
    return result
