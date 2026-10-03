"""Place disconnected components beside the main graph without extra marks."""
import copy
import math


def pack(model,ir,placed,root=None):
    result=copy.deepcopy(placed)
    owners={n:r['id']for r in ir['regions']for n in r['members']}
    members={r['id']:r['members']for r in ir['regions']}
    adjacency={r:set()for r in members}
    for relation in model['relations']:
        a,b=owners[relation['source']],owners[relation['target']]
        if a!=b:adjacency[a].add(b);adjacency[b].add(a)
    seen=set();components=[]
    positions={n['id']:n for n in result['children']}
    for region in sorted(adjacency):
        if region in seen:continue
        regions=[region];seen.add(region)
        for item in regions:
            for other in sorted(adjacency[item]-seen):seen.add(other);regions.append(other)
        nodes=sorted(n for rid in regions for n in members[rid])
        left=min(positions[r]['x']for r in regions);top=min(positions[r]['y']for r in regions)
        right=max(positions[r]['x']+positions[r]['width']for r in regions);bottom=max(positions[r]['y']+positions[r]['height']for r in regions)
        components.append(dict(regions=regions,nodes=nodes,x=left,y=top,width=right-left,height=bottom-top))
    components.sort(key=lambda c:(not(root in c['nodes'])if root else False,-len(c['nodes']),-c['width']*c['height'],c['nodes']))
    if len(components)<=1:
        return result,dict(changed=False,component_count=len(components),policy='Main component left, independent components in a plain grid to the right')
    main=components[0];others=sorted(components[1:],key=lambda c:(-c['height'],c['nodes']))
    columns=max(1,math.ceil(math.sqrt(len(others))/2))
    widths=[max((c['width']for i,c in enumerate(others)if i%columns==col),default=0)for col in range(columns)]
    targets=[(main,24,24)]
    y=24
    for start in range(0,len(others),columns):
        x=24+main['width']+56
        row=others[start:start+columns]
        for col,component in enumerate(row):
            targets.append((component,x,y));x+=widths[col]+40
        y+=max(c['height']for c in row)+40
    moves=[]
    for component,x,y in targets:
        dx,dy=x-component['x'],y-component['y']
        for rid in component['regions']:
            positions[rid]['x']+=dx;positions[rid]['y']+=dy
        moves.append(dict(nodes=component['nodes'],dx=dx,dy=dy))
    result['width']=max(n['x']+n['width']for n in positions.values())+24
    result['height']=max(n['y']+n['height']for n in positions.values())+24
    return result,dict(changed=True,component_count=len(components),auxiliary_columns=columns,moves=moves,policy='Rigid component translation only; main left, independent components right. No semantic edges or decorative container added.')
