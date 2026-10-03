"""Center a free top source over its children before any route is built."""
import copy


def center(placed):
    result=copy.deepcopy(placed)
    nodes={n['id']:n for n in result['children']}
    incoming={x for e in result['edges']for x in e['targets']}
    moves=[];rejected=[]
    for ident in sorted(nodes):
        if ident in incoming:continue
        children=sorted({x for e in result['edges']if ident in e['sources']for x in e['targets']if x!=ident})
        if len(children)<2:continue
        node=nodes[ident]
        centers=[nodes[x]['x']+nodes[x]['width']/2 for x in children]
        desired=(min(centers)+max(centers))/2-node['width']/2
        delta=desired-node['x']
        if abs(delta)<8:continue
        if desired<24 or desired+node['width']>result['width']-24:
            rejected.append(dict(region=ident,reason='outside fixed canvas'));continue
        collision=any(other['id']!=ident and min(desired+node['width']+12,other['x']+other['width']+12)>max(desired-12,other['x']-12)and min(node['y']+node['height']+12,other['y']+other['height']+12)>max(node['y']-12,other['y']-12)for other in nodes.values())
        if collision:
            rejected.append(dict(region=ident,reason='would collide with another region'));continue
        node['x']=desired;moves.append(dict(region=ident,dx=delta,children=children))
    return result,dict(moves=moves,rejected=rejected,policy='Only zero-incoming quotient sources with at least two children move in x; dimensions, y, canvas and UML facts stay fixed. Full routing and labels are solved afterwards.')
