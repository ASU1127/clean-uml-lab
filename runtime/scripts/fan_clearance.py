"""One bounded geometry repair for infeasible composition-fan end labels."""
import copy
from fan_layout import points
from tree_layout import hits_box


def stage(graph,model):
    g=copy.deepcopy(graph);nodes={n['id']:n for n in g['children']};groups={};changed=[]
    for e in g['edges']:
        r=model['relations'][int(e['id'].split('_')[1])]
        if r['kind'] not in ('composition','aggregation') or e.get('qualifier_sizes') or r['source']==r['target']:
            continue
        ps=points(e)
        if len(ps)!=3 or abs(ps[0]['x']-ps[1]['x'])>1e-6:
            continue
        groups.setdefault(e['sources'][0],[]).append(e)
    for edges in groups.values():
        if len(edges)<2:continue
        maximum=max(abs(points(e)[-1]['x']-points(e)[0]['x']) for e in edges) or 1
        for e in edges:
            ps=points(e);a,b,c=[(p['x'],p['y']) for p in ps]
            dx,dy=c[0]-a[0],c[1]-a[1]
            if dy<=100:continue
            depth=max(30,72-42*abs(dx)/maximum)
            proposed=[a,(a[0],a[1]+depth),c]
            if any(hits_box(u,v,(n['x']+2,n['y']+2,n['x']+n['width']-2,n['y']+n['height']-2)) for u,v in zip(proposed,proposed[1:]) for n in nodes.values()):
                continue
            if [(p['x'],p['y']) for p in ps]!=proposed:
                e['sections'][0]['bendPoints']=[dict(x=a[0],y=a[1]+depth)];changed.append(e['id'])
    return g,changed
