"""Attach a qualifier rectangle without adding a routing elbow.

All coordinates are presentation data. The named semantic end is unchanged.
Unsupported short/compound routes fail rather than hide a qualifier.
"""
import math


def geometry(model, nodes, relation, points, sizes):
    visible = list(points)
    qualifiers = {}
    for side, index, neighbor in [('source', 0, 1), ('target', -1, -2)]:
        if side + '_qualifier' not in relation:
            continue
        if side not in sizes:
            raise ValueError('missing measured qualifier size')
        n = nodes[relation[side]]
        x, y, w, h = n['x'], n['y'], n['width'], n['height']
        p, q = points[index], points[neighbor]
        dx, dy = q[0] - p[0], q[1] - p[1]
        qw, qh = sizes[side]['width'], sizes[side]['height']
        faces = [(abs(p[1]-y), -dy, 'north'),
                 (abs(p[1]-y-h), dy, 'south'),
                 (abs(p[0]-x), -dx, 'west'),
                 (abs(p[0]-x-w), dx, 'east')]
        attached = [f for f in faces if f[0] < 1e-4 and f[1] > 1e-7]
        if not attached:
            raise ValueError('qualified association must leave a classifier face')
        _, _, face = max(attached, key=lambda f: (f[1], f[2]))
        if face in ('north','south'):
            if qw > w + 1e-7:
                raise ValueError('classifier face is too narrow for its qualifier')
            cx = max(x+qw/2, min(x+w-qw/2, p[0]))
            qx, qy = cx-qw/2, y-qh if face=='north' else y+h
            anchor = (cx, y if face=='north' else y+h)
        else:
            if qh > h + 1e-7:
                raise ValueError('classifier face is too short for its qualifier')
            cy = max(y+qh/2, min(y+h-qh/2, p[1]))
            qx, qy = x-qw if face=='west' else x+w, cy-qh/2
            anchor = (x if face=='west' else x+w, cy)
        vx, vy = q[0]-anchor[0], q[1]-anchor[1]
        exits = []
        if vx > 1e-9: exits.append((qx+qw-anchor[0])/vx)
        elif vx < -1e-9: exits.append((qx-anchor[0])/vx)
        if vy > 1e-9: exits.append((qy+qh-anchor[1])/vy)
        elif vy < -1e-9: exits.append((qy-anchor[1])/vy)
        positive = [f for f in exits if f > 1e-9]
        if not positive:
            raise ValueError('qualifier has no outward path segment')
        fraction = min(positive)
        if fraction >= 1 or math.hypot(vx,vy)*(1-fraction) < 16:
            raise ValueError('qualified association path is too short for its rectangle and marker')
        endpoint = (anchor[0]+vx*fraction, anchor[1]+vy*fraction)
        visible[index] = endpoint
        qualifiers[side] = dict(x=qx,y=qy,width=qw,height=qh,face=face,
                                classifier=relation[side],class_port=list(anchor),
                                point=list(endpoint),name=relation[side+'_qualifier']['name'])
    if len(visible)==2 and qualifiers:
        # Rectangles at both ends must leave a visible connector between them.
        original=(points[-1][0]-points[0][0],points[-1][1]-points[0][1])
        actual=(visible[-1][0]-visible[0][0],visible[-1][1]-visible[0][1])
        if sum(a*b for a,b in zip(original,actual)) <= 0 or math.hypot(*actual)<16:
            raise ValueError('qualifier rectangles leave no connector clearance')
    return visible, qualifiers


def edge_geometry(g, edge, model):
    if len(edge.get('sections',[])) != 1 or any('children' in n for n in g['children']):
        raise ValueError('qualifier label solving requires one flat route section')
    section=edge['sections'][0]
    ps=[(p['x'],p['y']) for p in [section['startPoint']]+section.get('bendPoints',[])+[section['endPoint']]]
    if edge.get('semanticReverse',False): ps.reverse()
    relation=model['relations'][int(edge['id'].split('_')[1])]
    return geometry(model,{n['id']:n for n in g['children']},relation,ps,edge.get('qualifier_sizes',{}))
