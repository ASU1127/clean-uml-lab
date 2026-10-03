"""Separate local-region layout from quotient-graph placement and routing."""
import copy,json,math
from auxiliary_groups import route_options,xy
from fan_layout import points
from cached_route_metrics import CachedMeasure


def propose(model,template,ir,folder,node,elk,reorder=False,label_aware=False,spine=False,route_all=False,root=None,corner_routes=False,tight_regions=False,compact_spacing=False,spread_ports=False,component_pack=False,center_sources=False):
    owners={n:r['id'] for r in ir['regions'] for n in r['members']}
    ns={n['id']:n for n in template['children']}
    local={};calls=0
    def layout(g,name):
        nonlocal calls
        a=folder/(name+'-input.json');b=folder/(name+'-layout.json')
        a.write_text(json.dumps(g,ensure_ascii=False),encoding='utf-8')
        node('layout.cjs',elk,a,b);calls+=1
        return json.loads(b.read_text(encoding='utf-8-sig'))
    def endpoints(e):
        r=model['relations'][int(e['id'].split('_')[1])]
        return r['source'],r['target']
    for region in ir['regions']:
        rid=region['id'];members=set(region['members'])
        edges=[copy.deepcopy(e) for e in template['edges'] if set(endpoints(e))<=members]
        g=dict(id=rid,children=[copy.deepcopy(ns[n]) for n in region['members']],edges=edges,layoutOptions=copy.deepcopy(template['layoutOptions']))
        # Independent local geometry cannot be stretched by an external edge.
        if len(members)==1 and not edges:
            n=g['children'][0];n.update(x=24,y=24);g.update(width=n['width']+48,height=n['height']+48)
        else:g=layout(g,rid)
        if tight_regions:
            # Reserve actual node/self-loop content. Outer ELK region padding
            # otherwise gets counted once locally and again in the quotient.
            content=[(n['x'],n['y'],n['x']+n['width'],n['y']+n['height']) for n in g['children']]
            for e in g.get('edges',[]):
                if not route_all or endpoints(e)[0]==endpoints(e)[1]:
                    content.extend((p['x']-8,p['y']-8,p['x']+8,p['y']+8) for p in points(e))
                    content.extend((l['x']-4,l['y']-4,l['x']+l['width']+4,l['y']+l['height']+4) for l in e.get('labels',[]))
            left=min(b[0] for b in content)-12;top=min(b[1] for b in content)-12
            width=max(b[2] for b in content)-left+12;height=max(b[3] for b in content)-top+12
            for n in g['children']:n['x']-=left;n['y']-=top
            for e in g.get('edges',[]):
                for p in points(e):p['x']-=left;p['y']-=top
                for l in e.get('labels',[]):l['x']-=left;l['y']-=top
            g.update(width=width,height=height)
        local[rid]=g
    pairs={}
    for edge in template['edges']:
        a,b=endpoints(edge);a,b=owners[a],owners[b]
        if a==b:continue
        if edge.get('semanticReverse'):a,b=b,a
        pairs.setdefault((a,b),[]).append(edge['id'])
    placement_pairs=sorted(pairs)
    if spine:
        from region_spine import links
        placement_pairs,stats=links(model,owners,root)
        (folder/'spine.json').write_text(json.dumps(stats),encoding='utf-8')
    quotient=dict(id='root',layoutOptions={**template['layoutOptions'],'elk.spacing.nodeNode':'48' if compact_spacing else '72','elk.layered.spacing.nodeNodeBetweenLayers':'60' if compact_spacing else '100'},children=[dict(id=rid,width=g['width'],height=g['height']) for rid,g in local.items()],edges=[dict(id='regionlink_'+str(i),sources=[a],targets=[b]) for i,(a,b) in enumerate(placement_pairs)])
    placed=layout(quotient,'quotient')
    if component_pack:
        if not route_all:raise ValueError('Component packing requires rebuilding non-loop routes')
        from component_pack import pack
        placed,packing=pack(model,ir,placed,root)
        (folder/'component-pack.json').write_text(json.dumps(packing,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'packed-quotient.json').write_text(json.dumps(placed,ensure_ascii=False),encoding='utf-8')
    if center_sources:
        if not route_all:raise ValueError('Source centering requires rebuilding non-loop routes')
        from source_center import center
        placed,centering=center(placed)
        (folder/'source-center.json').write_text(json.dumps(centering,ensure_ascii=False,indent=2),encoding='utf-8')
    if reorder:
        from region_order import improve
        placed,stats=improve(placed,pairs)
        (folder/'order-search.json').write_text(json.dumps(stats),encoding='utf-8')
    positions={n['id']:n for n in placed['children']}
    nodes=[];edges=[]
    for rid,g in local.items():
        ox,oy=positions[rid]['x'],positions[rid]['y']
        for n in g['children']:
            n=copy.deepcopy(n);n['x']+=ox;n['y']+=oy;nodes.append(n)
        for edge in g.get('edges',[]):
            e=copy.deepcopy(edge)
            if len(e.get('sections',[]))!=1:raise ValueError('Local edge has multiple sections')
            for p in points(e):p['x']+=ox;p['y']+=oy
            for label in e.get('labels',[]):label['x']+=ox;label['y']+=oy
            edges.append(e)
    byid={n['id']:n for n in nodes};measure=CachedMeasure()
    boundary=[copy.deepcopy(e) for e in template['edges'] if owners[endpoints(e)[0]]!=owners[endpoints(e)[1]]]
    if route_all:
        # Keep self-loops, whose attachment and labels cannot be represented by
        # a two-node route proposal. All other edges share the same router.
        edges=[e for e in edges if endpoints(e)[0]==endpoints(e)[1]]
        boundary=[copy.deepcopy(e) for e in template['edges'] if endpoints(e)[0]!=endpoints(e)[1]]
    priorities={'generalization':0,'realization':0,'composition':1,'aggregation':2,'association':3,'dependency':4}
    router=route_options
    if corner_routes:
        from region_routes import options
        router=options
    if spread_ports:
        from port_routes import options
        router=options
    for e in sorted(boundary,key=lambda e:(priorities[model['relations'][int(e['id'].split('_')[1])]['kind']],e['id'])):
        a,b=e['sources'][0],e['targets'][0]
        candidates=[]
        for ps in router(byid[a],byid[b],nodes):
            rm=measure(dict(width=placed['width'],height=placed['height'],edges=[dict(index=f['id'],points=[xy(p) for p in points(f)]) for f in edges]+[dict(index=e['id'],points=[xy(p) for p in ps])]))
            candidates.append(((rm['other_contacts'],rm['shared_track_length'],rm['proper_crossings'],len(ps),sum(math.dist(xy(a),xy(b)) for a,b in zip(ps,ps[1:]))),ps))
        if not candidates:raise ValueError('No unobstructed cross-region route for '+e['id'])
        candidates.sort(key=lambda v:v[0])
        if label_aware:
            from joint_labels import solve
            chosen=None
            for _,ps in candidates:
                trial=copy.deepcopy(e)
                trial['sections']=[dict(startPoint=ps[0],endPoint=ps[-1],bendPoints=ps[1:-1])]
                for label in trial.get('labels',[]):label.update(x=0,y=0)
                partial=dict(width=placed['width'],height=placed['height'],children=nodes,edges=copy.deepcopy(edges)+[trial])
                if solve(partial,limit=1000,model=model,preserve_edges={f['id'] for f in edges}):
                    chosen=partial['edges'];break
            if chosen is None:raise ValueError('No label-feasible cross-region route for '+e['id'])
            edges=chosen
            continue
        _,ps=candidates[0];e['sections']=[dict(startPoint=ps[0],endPoint=ps[-1],bendPoints=ps[1:-1])]
        # Provisional values are replaced by the joint label solver.
        for label in e.get('labels',[]):label.update(x=0,y=0)
        e['needs_label_placement']=True
        edges.append(e)
    return dict(id='root',width=placed['width'],height=placed['height'],children=nodes,edges=edges),calls
