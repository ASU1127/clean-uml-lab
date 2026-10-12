"""Local UML class-diagram generation with audited global-layout proposals."""
import argparse,copy,hashlib,json,math,os,shutil,subprocess,sys,time
from pathlib import Path
HOME=Path(__file__).resolve().parent
RUNTIME=HOME/'runtime' if (HOME/'runtime').exists() else HOME.parent/'clean-uml-next'
sys.path.insert(0,str(RUNTIME/'scripts'))
from layout_ir import build
from clean_uml import generate
from tree_layout import tree_graph,draw
from audit import audit_svg
from audit import configure_path_cache
from marker_labels import findings
from joint_labels import solve
from route_metrics import measure
from drawio_export import export_drawio

def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def flatten(g):
    nodes=[];edges=[];containers={'root':(0,0)};pending=[]
    def visit(group,ox=0,oy=0):
        for node in group.get('children',[]):
            x=ox+node.get('x',0);y=oy+node.get('y',0)
            if 'children' in node:containers[node['id']]=(x,y);visit(node,x,y)
            else:
                n=copy.deepcopy(node);n['x']=x;n['y']=y;nodes.append(n)
        pending.extend((edge,ox,oy) for edge in group.get('edges',[]))
    visit(g)
    for edge,ox,oy in pending:
            ox,oy=containers.get(edge.get('container'),(ox,oy))
            e=copy.deepcopy(edge)
            if len(e.get('sections',[]))!=1:raise ValueError('Compound proposal has unsupported multi-section edge')
            for section in e['sections']:
                for p in [section['startPoint']]+section.get('bendPoints',[])+[section['endPoint']]:p['x']+=ox;p['y']+=oy
            for label in e.get('labels',[]):label['x']+=ox;label['y']+=oy
            edges.append(e)
    return dict(id='root',width=g['width'],height=g['height'],children=nodes,edges=edges)

def run(args):
    start=time.perf_counter();out=Path(args.output).resolve()
    configure_path_cache(not getattr(args,'no_path_cache',False))
    if getattr(args,'vector_only',False) and getattr(args,'candidate_previews',False):raise ValueError('Vector-only generation cannot request PNG previews')
    if out.exists():raise ValueError('Output directory already exists; choose a new directory')
    out.mkdir(parents=True)
    source_bytes=(json.dumps(args.input_model,ensure_ascii=False,indent=2).encode('utf-8') if getattr(args,'input_model',None) is not None else Path(args.model).read_bytes())
    model=json.loads(source_bytes.decode('utf-8-sig'));ir=build(model);save(out/'layout-ir.json',ir)
    (out/'original-model.json').write_bytes(source_bytes)
    if 'input_bindings' in ir:save(out/'type-binding-audit.json',ir['input_bindings'])
    if 'input_namespaces' in ir:save(out/'namespace-audit.json',ir['input_namespaces'])
    save(out/'model.json',ir['facts'])
    sharp=str(Path(args.sharp_module).resolve()) if args.sharp_module else str(RUNTIME/'node_modules/sharp')
    elk=str(Path(args.elk_module).resolve()) if args.elk_module else str(RUNTIME/'node_modules/elkjs/lib/elk.bundled.js')
    env=os.environ.copy()
    if args.fontconfig:env['FONTCONFIG_FILE']=str(Path(args.fontconfig).resolve())
    extra_layout_calls=0;layout_cache={}
    def node(script,*values):
        nonlocal extra_layout_calls
        if script=='layout.cjs':
            cache_key=hashlib.sha256(Path(values[1]).read_bytes()).hexdigest()
            if cache_key in layout_cache:
                Path(values[2]).write_bytes(layout_cache[cache_key]);return
            extra_layout_calls+=1
        subprocess.run([args.node,str(RUNTIME/'scripts'/script),*map(str,values)],check=True,capture_output=True,env=env,timeout=90)
        if script=='layout.cjs':layout_cache[cache_key]=Path(values[2]).read_bytes()
    baseline=out/'baseline'
    bargs=argparse.Namespace(model=str(out/'model.json'),output=str(baseline),root=args.root,requirements=getattr(args,'requirements',None),node=args.node,sharp_module=sharp,elk_module=elk,fontconfig=args.fontconfig,rank_policy='uniform',compact_auxiliary=False,no_compact_bands=False,no_joint_straight=False,reuse_marker_scene=not getattr(args,'no_marker_cache',False),render_png=False)
    br=generate(bargs)
    model=json.loads((baseline/'model.json').read_text(encoding='utf-8-sig'));metrics=json.loads((baseline/'metrics.json').read_text(encoding='utf-8-sig'))
    baseline_metrics=json.loads((baseline/'route-metrics.json').read_text(encoding='utf-8-sig'))
    baseline_scene=json.loads((baseline/'layout.json').read_text(encoding='utf-8-sig'))
    baseline_hierarchy=all(baseline_scene['nodes'][r['target']]['y']+baseline_scene['nodes'][r['target']]['height']<baseline_scene['nodes'][r['source']]['y'] for r in model['relations'] if r['kind'] in ('generalization','realization'))
    rows=[dict(candidate='baseline',metrics=baseline_metrics,status=br['status'],valid=baseline_hierarchy and not json.loads((baseline/'visual-audit.json').read_text(encoding='utf-8-sig'))['findings'] and not findings((baseline/'diagram.svg').read_bytes()))]
    incident={r[side]for r in model['relations']for side in('source','target')}
    independent_enums=[n['id']for n in model['nodes']if n['kind']=='enum'and n['id']not in incident]
    balanced=bool(independent_enums)and not getattr(args,'no_balanced',False)
    arms=('compact-global','spread-global')+(('balanced-global',)if balanced else())+(('intrinsic-global',) if getattr(args,'research_intrinsic',False) else ())+(('regions','regions-reversed','coarse','spine') if getattr(args,'research_regions',False) else ())
    arms=list(arms)
    for arm in arms:
        if arm=='qualifier-clearance' and any(r['valid'] for r in rows):continue
        folder=out/arm;folder.mkdir()
        try:
            g=tree_graph(model,metrics,routing='ORTHOGONAL',root=args.root,sized=arm!='intrinsic-global')
            if arm in ('compact-global','spread-global','balanced-global','intrinsic-global','qualifier-clearance'):
                from coarse_layout import propose
                from region_partition import propose as partition
                t,_=propose(model,g,partition(ir,'singletons'),folder,node,elk,label_aware=True,route_all=True,corner_routes=True,tight_regions=True,compact_spacing=True,root=args.root,spread_ports=arm in('spread-global','balanced-global','qualifier-clearance'),component_pack=arm=='balanced-global'and not getattr(args,'no_component_packing',False),center_sources=arm=='balanced-global'and not getattr(args,'no_source_centering',False),qualifier_gap=arm=='qualifier-clearance')
            elif arm in ('coarse','spine'):
                from coarse_layout import propose
                t,_=propose(model,g,ir,folder,node,elk,label_aware=True,route_all=True,corner_routes=True,spine=arm=='spine',root=args.root)
            else:
                byid={n['id']:n for n in g['children']}
                regions=ir['regions'] if arm=='regions' else list(reversed(ir['regions']))
                g['children']=[dict(id=r['id'],children=[byid[n] for n in r['members']],layoutOptions={'elk.direction':'DOWN','elk.padding':'[top=24,left=24,bottom=24,right=24]'}) if len(r['members'])>1 else byid[r['members'][0]] for r in regions]
                g['layoutOptions']['elk.hierarchyHandling']='INCLUDE_CHILDREN'
                g['layoutOptions']['elk.layered.considerModelOrder.strategy']='NODES_AND_EDGES'
                save(folder/'elk-input.json',g);node('layout.cjs',elk,folder/'elk-input.json',folder/'elk-layout.json')
                t=flatten(json.loads((folder/'elk-layout.json').read_text(encoding='utf-8-sig')))
            assert len(t['children'])==len(model['nodes']) and len(t['edges'])==len(model['relations'])
            # Labels are solved after final geometry. No 2.x fan/family repair chain.
            solved=solve(t,limit=10000,model=model,preserve_edges={e['id'] for e in t['edges'] if not e.get('needs_label_placement')})
            if not solved:
                save(folder/'failed-layout.json',t)
                raise ValueError('Joint labels have no feasible placement. Provisional label coordinates are not rendered; see failed-layout.json.')
            svg,scene=draw(model,metrics,t);audit=audit_svg(svg,model);markers=findings(svg);rm=measure(scene)
            hierarchy=all(scene['nodes'][r['target']]['y']+scene['nodes'][r['target']]['height']<scene['nodes'][r['source']]['y'] for r in model['relations'] if r['kind'] in ('generalization','realization'))
            (folder/'diagram.svg').write_bytes(svg);(folder/'diagram.drawio').write_bytes(export_drawio(model,scene,svg));save(folder/'final-layout.json',t);save(folder/'route-metrics.json',rm)
            save(folder/'audit.json',dict(geometry=audit,markers=markers,labels_solved=solved,hierarchy=hierarchy))
            rows.append(dict(candidate=arm,metrics=rm,valid=solved and hierarchy and not audit['findings'] and not markers,status='audited'))
        except (ValueError,AssertionError,subprocess.SubprocessError,KeyError,ZeroDivisionError) as error:
            save(folder/'failure.json',dict(error=str(error)));rows.append(dict(candidate=arm,valid=False,status='failed',error=str(error)))
        if arm==arms[-1] and 'qualifier-clearance' not in arms and not getattr(args,'no_qualifier_clearance',False) and not any(r['valid'] for r in rows) and any(side+'_qualifier' in r for r in model['relations'] for side in ('source','target')):
            arms.append('qualifier-clearance')
    fan_enabled=not getattr(args,'no_fan_clearance',False)
    association_enabled=not getattr(args,'no_association_clearance',False)
    fan_repair=dict(enabled=fan_enabled or association_enabled,fan_enabled=fan_enabled,
                    association_enabled=association_enabled,triggered=False,
                    geometry_calls=0,label_solves=0,solver_limit=10000,manual_repairs=0)
    if fan_repair['enabled'] and not any(row['valid'] for row in rows):
        folder=out/'fan-clearance';folder.mkdir();fan_repair['triggered']=True
        try:
            from fan_clearance import stage
            sys.path.insert(0,str(HOME/'refinement'))
            from path_labels import solve as prefix_solve
            original=json.loads((baseline/'final-layout.json').read_text(encoding='utf-8-sig'))
            owner={n['id']:n['id'] for n in original['children']}
            for n in original['children']:owner.update({p['id']:n['id'] for p in n.get('ports',[])})
            for e in original['edges']:e['sources']=[owner[e['sources'][0]]];e['targets']=[owner[e['targets'][0]]]
            t,changes=stage(original,model) if fan_enabled else (copy.deepcopy(original),[])
            fan_repair.update(geometry_calls=int(fan_enabled),changed_routes=changes)
            if not changes and not association_enabled:raise ValueError('No eligible fan geometry to repair')
            trace={};fan_repair['label_solves']=1
            solved=prefix_solve(t,model=model,traverse=True,preserve_edges={e['id'] for e in t['edges']} - set(changes),limit=10000,trace=trace)
            fan_repair['solver']=trace
            if not solved and association_enabled:
                from association_clearance import repair
                t,association_trace=repair(t,model,metrics,trace,changed=changes)
                fan_repair['association']=association_trace
                fan_repair['label_solves']+=association_trace['label_solves']
                solved=association_trace['accepted']
            if not solved:
                save(folder/'failed-layout.json',t);raise ValueError('Fan end labels remain infeasible')
            svg,scene=draw(model,metrics,t);audit=audit_svg(svg,model);markers=findings(svg);rm=measure(scene)
            hierarchy=all(scene['nodes'][r['target']]['y']+scene['nodes'][r['target']]['height']<scene['nodes'][r['source']]['y'] for r in model['relations'] if r['kind'] in ('generalization','realization'))
            longest_before=max((sum(math.dist(a,b) for a,b in zip(e['points'],e['points'][1:])) for e in baseline_scene['edges']),default=0)
            longest_after=max((sum(math.dist(a,b) for a,b in zip(e['points'],e['points'][1:])) for e in scene['edges']),default=0)
            protected=all(rm[k]<=baseline_metrics[k]+1e-6 for k in ('proper_crossings','other_contacts','shared_track_length','bends','route_length','area')) and longest_after<=longest_before+1e-6
            fan_repair.update(longest_route_before=longest_before,longest_route_after=longest_after)
            valid=hierarchy and protected and not audit['findings'] and not markers
            (folder/'diagram.svg').write_bytes(svg);(folder/'diagram.drawio').write_bytes(export_drawio(model,scene,svg))
            from check_exports import verify
            verify(folder/'diagram.drawio',model)
            save(folder/'final-layout.json',t);save(folder/'route-metrics.json',rm)
            save(folder/'audit.json',dict(geometry=audit,markers=markers,labels_solved=True,hierarchy=hierarchy,protected_geometry=protected))
            rows.append(dict(candidate='fan-clearance',metrics=rm,valid=valid,status='audited'))
        except (ValueError,AssertionError,KeyError,ZeroDivisionError) as error:
            save(folder/'failure.json',dict(error=str(error)));rows.append(dict(candidate='fan-clearance',valid=False,status='failed',error=str(error)))
    save(out/'fan-clearance.json',fan_repair)
    # Valid notation is required before geometry can rank usable candidates.
    # Preserve conservative dominance when the baseline itself passes its gates.
    keys=('proper_crossings','other_contacts','shared_track_length','bends','route_length','area')
    baseline_valid=rows[0]['valid']
    eligible=[r for r in rows if r['valid'] and (not baseline_valid or all(r['metrics'][k]<=baseline_metrics[k] for k in keys))]
    winner=min(eligible,key=lambda r:tuple(r['metrics'][k] for k in keys)) if eligible else rows[0]
    selected=out/winner['candidate']
    for filename in ('diagram.svg','diagram.drawio'):shutil.copyfile(selected/filename,out/filename)
    # Vector audits decide first. The normal path rasterizes exactly one winner.
    png_exports=0
    if not getattr(args,'vector_only',False):
        node('rasterize.cjs',sharp,out/'diagram.svg',out/'diagram.png');png_exports=1
    if getattr(args,'candidate_previews',False):
        for row in rows:
            folder=out/row['candidate']
            if not (folder/'diagram.svg').exists():continue
            if folder==selected:shutil.copyfile(out/'diagram.png',folder/'diagram.png')
            else:node('rasterize.cjs',sharp,folder/'diagram.svg',folder/'diagram.png');png_exports+=1
    save(out/'run.json',dict(stage='4.4 phase product: one selected raster and optional rendered text review',png_exports=png_exports,candidate_previews=getattr(args,'candidate_previews',False),candidate_pngs_inside_search=0,selected=winner['candidate'],selected_valid=winner['valid'],root=args.root,research_regions=getattr(args,'research_regions',False),research_intrinsic=getattr(args,'research_intrinsic',False),independent_enums=independent_enums,balance=dict(candidate_enabled=balanced,component_packing=balanced and not getattr(args,'no_component_packing',False),source_centering=balanced and not getattr(args,'no_source_centering',False)),candidates=rows,layout_calls=br['layout_calls']+extra_layout_calls,seconds=time.perf_counter()-start,semantic_regions=ir['diagnostics'],scope='Baseline plus compact and spread routing; balanced packing/centering candidate only when declared enums are disconnected. A measured qualifier-clearance candidate is added only if all preceding candidates fail. Complete label-feasible non-loop routing. Width and region hypotheses are opt-in research. Global permutation search is not implemented.',selection=dict(baseline_valid=baseline_valid,policy='Strict geometry dominance over a valid baseline; otherwise choose the best passing candidate',geometry_delta_from_baseline={k:round(winner.get('metrics',baseline_metrics)[k]-baseline_metrics[k],2) for k in keys}),fallback='Invalid baseline is diagnostic only when a valid candidate exists; report failure if every candidate fails',human_readability='not_certified'))
    record=json.loads((out/'run.json').read_text(encoding='utf-8'))
    record['fan_clearance']=fan_repair
    record['internal_geometry_repairs']=int(fan_repair['triggered'])
    record['manual_repairs']=0
    record['first_pass_without_internal_repair']=bool(winner['valid']) and not fan_repair['triggered']
    save(out/'run.json',record)
    import html
    cards=''.join(f'<section><h2>{r["candidate"]} · {r["status"]} · valid={r["valid"]}</h2><a href="{r["candidate"]}/diagram.drawio">draw.io</a><img src="{r["candidate"]}/diagram.svg" loading="lazy"></section>' if (out/r['candidate']/'diagram.svg').exists() else f'<section><h2>{r["candidate"]} · failed</h2><p>{html.escape(r.get("error",""))}</p><a href="{r["candidate"]}/failure.json">失败诊断</a></section>' for r in rows)
    image_file='diagram.png' if png_exports else 'diagram.svg'
    png_link=' · <a href="diagram.png">PNG</a>' if png_exports else ''
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Clean UML 阶段原型</title><style>body{font:16px Arial;margin:24px}img{max-width:100%;display:block}section{border-top:1px solid #aaa;margin-top:24px}</style><h1>Clean UML</h1><p>选择：'+winner['candidate']+'。请检查复杂关系与标签归属。</p><a href="diagram.drawio">draw.io</a> · <a href="diagram.svg">SVG</a>'+png_link+' · <a href="run.json">检查记录</a><img src="'+image_file+'" alt="选中类图"><details><summary>候选与诊断</summary>'+cards+'</details>',encoding='utf-8')
    print(json.dumps(dict(output=str(out),selected=winner['candidate'],selected_valid=winner['valid'],candidates=[(r['candidate'],r['valid']) for r in rows]),ensure_ascii=False))
    return winner['valid']

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model');p.add_argument('-o','--output',required=True);p.add_argument('--root');p.add_argument('--requirements');p.add_argument('--vector-only',action='store_true',help='Keep audited SVG/draw.io without PNG for optional measured refinement');p.add_argument('--candidate-previews',action='store_true',help='Render candidate PNGs only after selection for optional inspection/ablation');p.add_argument('--research-regions',action='store_true');p.add_argument('--research-intrinsic',action='store_true');p.add_argument('--no-balanced',action='store_true');p.add_argument('--no-component-packing',action='store_true');p.add_argument('--no-source-centering',action='store_true');p.add_argument('--no-association-clearance',action='store_true',help='Disable the bounded failed-association rescue');p.add_argument('--no-fan-clearance',action='store_true',help='Disable the one bounded fan end-label repair');p.add_argument('--no-qualifier-clearance',action='store_true',help='Ablate the measured qualifier-spacing fallback');p.add_argument('--no-marker-cache',action='store_true',help='Ablate exact label-only renderer reuse');p.add_argument('--no-path-cache',action='store_true',help='Ablate bounded exact SVG path sampling cache');p.add_argument('--node',default='node');p.add_argument('--sharp-module');p.add_argument('--elk-module');p.add_argument('--fontconfig');sys.exit(0 if run(p.parse_args()) else 2)
