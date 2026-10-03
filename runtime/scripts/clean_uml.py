"""Clean UML: one command, bounded layout selection, local editable artifacts."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from compile_model import compile_model
from type_bindings import normalize_model
from build_structured import build
from fan_layout import improve as fan_improve
from tree_layout import draw as final_draw
from drawio_export import export_drawio
from audit import audit_svg
from marker_labels import findings as marker_findings
from route_metrics import measure

HOME=Path(__file__).resolve().parent.parent

def canonical(model):
 model,_=normalize_model(model)
 compile_model(model,validate_only=True)
 return {**model,'nodes':sorted(model['nodes'],key=lambda n:n['id']),
         'relations':sorted(model['relations'],key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))}

def runtime(node,sharp,elk):
 values=[]
 for explicit,module in [(sharp,'sharp'),(elk,'elkjs/lib/elk.bundled.js')]:
  script='process.stdout.write(require.resolve(process.argv[1],{paths:[process.argv[2]]}))'
  found=subprocess.run([node,'-e',script,explicit or module,str(HOME)],capture_output=True,text=True,timeout=20)
  if found.returncode:raise ValueError(f'Cannot resolve {explicit or module}. Run npm install in {HOME}, or pass --sharp-module/--elk-module.')
  values.append(found.stdout.strip())
 return values

def verify_requirements(model,path):
 if not path:return {'status':'not_provided','scope':'No natural-language requirements verification'}
 data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
 if not isinstance(data,dict) or set(data)-{'required_nodes','required_relations','forbidden_nodes','forbidden_relations'}:raise ValueError('Invalid requirements fields')
 problems=[]
 for key,patterns in data.items():
  if not isinstance(patterns,list) or any(not isinstance(p,dict) or not p for p in patterns):raise ValueError('Requirements must be lists of nonempty objects')
  pool=model['nodes'] if key.endswith('nodes') else model['relations']
  for p in patterns:
   exists=any(all(item.get(k)==v for k,v in p.items()) for item in pool)
   if exists==key.startswith('forbidden'):problems.append({'rule':key,'pattern':p})
 if problems:raise ValueError('Requirements mismatch: '+json.dumps(problems,ensure_ascii=False))
 return {'status':'passed','scope':'Only explicit caller-provided assertions checked'}

def generate(args):
 start=time.perf_counter();raw=Path(args.model).read_bytes();model=canonical(json.loads(raw.decode('utf-8-sig')))
 requirements=verify_requirements(model,args.requirements)
 if args.root and args.root not in {n['id'] for n in model['nodes']}:raise ValueError('Unknown root ID')
 out=Path(args.output)
 if out.exists():raise ValueError('Output directory already exists; choose a new path')
 sharp,elk=runtime(args.node,args.sharp_module,args.elk_module)
 env=os.environ.copy()
 if args.fontconfig:env['FONTCONFIG_FILE']=str(Path(args.fontconfig).resolve())
 out.mkdir(parents=True)
 def save(name,data):(out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/'original-model.json').write_bytes(raw);save('model.json',model);save('requirements-check.json',requirements)
 if 'imports' in json.loads(raw.decode('utf-8-sig')):save('type-binding-audit.json',normalize_model(json.loads(raw.decode('utf-8-sig')))[1])
 if args.requirements:shutil.copyfile(args.requirements,out/'requirements.json')
 candidates=[]
 for label,order in [('A',False),('B',True)]:
  directory=out/'candidates'/label
  result=build(out/'model.json',directory,node=args.node,sharp=sharp,elk=elk,fontconfig=args.fontconfig,root=args.root,model_order=order,render_png=False,rank_policy=args.rank_policy,reuse_marker_scene=getattr(args,'reuse_marker_scene',True))
  routes=json.loads((directory/'route-metrics.json').read_text(encoding='utf-8-sig'));audit=json.loads((directory/'visual-audit.json').read_text(encoding='utf-8'));markers=json.loads((directory/'marker-label-audit.json').read_text(encoding='utf-8'))
  scene=json.loads((directory/'layout.json').read_text(encoding='utf-8-sig'));inheritance=all(scene['nodes'][r['target']]['y']<scene['nodes'][r['source']]['y'] for r in model['relations'] if r['kind'] in ('generalization','realization'))
  score=[int(not inheritance),sum(f.get('level')=='error' for f in audit['findings']),len(audit['findings'])+len(markers['after']),routes['proper_crossings'],routes['other_contacts'],routes['shared_track_length'],routes['bends'],routes['route_length'],routes['area']]
  candidates.append({'candidate':label,'score':score,'routes':routes,'seconds':result['seconds']})
 original_winner=min(candidates,key=lambda c:(c['score'],c['candidate']))
 # Bounded heuristic: do not spend postprocessing time on candidates already
 # dominated in every measured dimension. This is not a global-optimality proof.
 frontier=[c for c in candidates if not any(all(x<=y for x,y in zip(other['score'],c['score'])) and other['score']!=c['score'] for other in candidates)]
 finished={}
 for candidate in frontier:
  source=out/'candidates'/candidate['candidate'];post_start=time.perf_counter()
  graph=json.loads((source/'final-layout.json').read_text(encoding='utf-8'));metrics=json.loads((source/'metrics.json').read_text(encoding='utf-8-sig'))
  graph,events=fan_improve(model,metrics,graph);group_events=None
  if args.compact_auxiliary:
   from auxiliary_groups import improve as compact_groups
   graph,group_events=compact_groups(model,metrics,graph)
  svg,scene=final_draw(model,metrics,graph);audit=audit_svg(svg,model);routes=measure(scene);markers=marker_findings(svg)
  inheritance=all(scene['nodes'][r['target']]['y']<scene['nodes'][r['source']]['y'] for r in model['relations'] if r['kind'] in ('generalization','realization'))
  score=[int(not inheritance),sum(f.get('level')=='error' for f in audit['findings']),len(audit['findings'])+len(markers),routes['proper_crossings'],routes['other_contacts'],routes['shared_track_length'],routes['bends'],routes['route_length'],routes['area']]
  candidate['final_score']=score;candidate['postprocess_seconds']=time.perf_counter()-post_start
  finished[candidate['candidate']]=(graph,events,group_events,svg,scene,audit,routes,markers)
  post=source/'postprocessed';post.mkdir()
  (post/'diagram.svg').write_bytes(svg)
  (post/'final-layout.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
  (post/'score.json').write_text(json.dumps({'score':score,'routes':routes,'audit':audit,'markers':markers},ensure_ascii=False,indent=2),encoding='utf-8')
 baseline_score=original_winner['final_score']
 # Preserve the old output unless a final candidate is no worse on *every*
 # measured dimension, including area. Tiny line savings must not hide expansion.
 eligible=[c for c in frontier if all(x<=y for x,y in zip(c['final_score'],baseline_score))]
 winner=min(eligible,key=lambda c:(c['final_score'],c['candidate']))
 save('selection.json',{'method':'postprocess non-dominated candidates, then require final metric dominance over original selection','original_selected':original_winner['candidate'],'processed':[c['candidate'] for c in frontier],'selected':winner['candidate'],'global_optimum_guaranteed':False})
 source=out/'candidates'/winner['candidate']
 for name in ('diagram.svg','diagram.drawio','layout.json','final-layout.json','metrics.json','visual-audit.json','marker-label-audit.json','route-metrics.json','family-adjustments.json'):
  shutil.copyfile(source/name,out/name)
 final_graph,fan_events,group_events,final_svg,final_scene,final_audit,final_routes,final_markers=finished[winner['candidate']]
 if not args.no_compact_bands:
  from compact_bands import improve as compact_bands
  metrics=json.loads((source/'metrics.json').read_text(encoding='utf-8-sig'))
  compact_start=time.perf_counter()
  final_graph,band_events=compact_bands(model,metrics,final_graph)
  save('band-compaction.json',{'events':band_events,'seconds':time.perf_counter()-compact_start,'extra_layout_calls':0})
  final_svg,final_scene=final_draw(model,metrics,final_graph)
  final_audit=audit_svg(final_svg,model);final_routes=measure(final_scene);final_markers=marker_findings(final_svg)
 if not args.no_joint_straight:
  from joint_straight import improve as joint_straight
  metrics=json.loads((source/'metrics.json').read_text(encoding='utf-8-sig'));joint_start=time.perf_counter()
  final_graph,joint_events=joint_straight(model,metrics,final_graph)
  save('joint-straightening.json',{'events':joint_events,'seconds':time.perf_counter()-joint_start,'extra_layout_calls':0})
  final_svg,final_scene=final_draw(model,metrics,final_graph)
  final_audit=audit_svg(final_svg,model);final_routes=measure(final_scene);final_markers=marker_findings(final_svg)
 if group_events is not None:save('auxiliary-groups.json',group_events)
 (out/'diagram.svg').write_bytes(final_svg);(out/'diagram.drawio').write_bytes(export_drawio(model,final_scene,final_svg))
 save('final-layout.json',final_graph);save('layout.json',final_scene)
 save('visual-audit.json',final_audit);save('route-metrics.json',final_routes)
 save('marker-label-audit.json',{'after':final_markers,'scope':'Polygon marker clearance; see candidates for earlier label adjustment traces'})
 save('fan-adjustments.json',fan_events)
 subprocess.run([args.node,str(HOME/'scripts/rasterize.cjs'),sharp,str(out/'diagram.svg'),str(out/'diagram.png')],env=env,check=True,capture_output=True,timeout=60)
 needs_review=bool(final_audit['findings'] or final_markers or any(final_routes[k] for k in ('proper_crossings','other_contacts','shared_track_length')) or winner['final_score'][0])
 result={'version':'2.2.0-rc.3','rank_policy':args.rank_policy,'compact_auxiliary':args.compact_auxiliary,'compact_bands':not args.no_compact_bands,'joint_straight':not args.no_joint_straight,'postprocessing':{'method':'root centering plus joint straight routes and labels','before':winner['routes'],'after':final_routes},'status':'needs_review' if needs_review else 'checks_passed','human_readability':'not_certified','selected':winner['candidate'],'layout_calls':2,'png_exports':1,'visual_model_calls':0,'canonical_input_order':True,'seconds':time.perf_counter()-start,'requirements':requirements,'candidates':candidates,'input_sha256':hashlib.sha256(raw).hexdigest(),'svg_sha256':hashlib.sha256((out/'diagram.svg').read_bytes()).hexdigest(),'limitations':['Class diagram subset only','No automatic business fact verification without explicit assertions','Editing may introduce collisions; arbitrary shrinking and full GUI interaction are not certified','Geometry metrics do not certify aesthetics']}
 save('run.json',result)
 (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Clean UML</title><style>body{font:16px system-ui;margin:24px}img{max-width:100%}p{line-height:1.8}</style><p>Clean UML · '+result['status']+' · <a href="diagram.svg">SVG</a> · <a href="diagram.png">PNG</a> · <a href="diagram.drawio">可编辑 draw.io</a> · <a href="run.json">运行与候选记录</a></p><p>自动检查不等于审美验收。复杂图请检查长线、交叉及标签归属。</p><img src="diagram.svg" alt="完整 UML 类图">',encoding='utf-8')
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('model');p.add_argument('-o','--output',required=True);p.add_argument('--compact-auxiliary',action='store_true',help='Experimental bounded relocation of weak-relation groups; at least 5 percent line saving and no extra bends');p.add_argument('--rank-policy',choices=['uniform','typed-distance'],default='uniform',help='Experimental relation-weighted hierarchy; may increase long routes');p.add_argument('--root');p.add_argument('--requirements');p.add_argument('--node',default='node');p.add_argument('--sharp-module');p.add_argument('--elk-module');p.add_argument('--fontconfig');p.add_argument('--no-compact-bands',action='store_true',help='Disable bounded whitespace compression for paired ablation');p.add_argument('--no-joint-straight',action='store_true',help='Disable straight-route joint label refinement for ablation');args=p.parse_args()
 try:
  result=generate(args);print(json.dumps({'status':result['status'],'output':str(Path(args.output).resolve()),'selected':result['selected'],'seconds':result['seconds']},ensure_ascii=False))
 except (ValueError,OSError,subprocess.SubprocessError) as e:
  print('Clean UML: '+str(e),file=sys.stderr);return 2
 return 0

if __name__=='__main__':sys.exit(main())
