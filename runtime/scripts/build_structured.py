"""Preview: one deterministic layout and one PNG, without visual search."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from lane_layout import measurements
from spread_layout import render
from structured_layout import graph,draw
from tree_layout import tree_graph,draw as tree_draw,simplify
from family_layout import improve
from marker_labels import improve as improve_labels
from drawio_export import export_drawio
from audit import audit_svg
from route_metrics import measure

def build(model_path,out,node='node',sharp='sharp',elk='elkjs/lib/elk.bundled.js',fontconfig=None,policy='tree',root=None,model_order=False,render_png=True,rank_policy='uniform',reuse_marker_scene=True):
 start=time.perf_counter();scripts=Path(__file__).parent;out=Path(out);env=os.environ.copy()
 if fontconfig:env['FONTCONFIG_FILE']=str(Path(fontconfig).resolve())
 raw=Path(model_path).read_bytes();model=json.loads(raw);request=measurements(model)
 if root is not None and (policy!='tree' or root not in {n['id'] for n in model['nodes']}):raise ValueError('--root requires tree policy and an existing node ID')
 if model_order and policy!='tree':raise ValueError('--model-order requires tree policy')
 out.mkdir(parents=True,exist_ok=False);(out/'model.json').write_bytes(raw)
 def save(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
 save('measure-request.json',request)
 def run(args):subprocess.run([node,*map(str,args)],env=env,check=True,capture_output=True,timeout=60)
 run([scripts/'measure.cjs',sharp,out/'measure-request.json',out/'metrics.json'])
 metrics=json.loads((out/'metrics.json').read_text(encoding='utf-8'))
 if policy=='tree':
  inp=tree_graph(model,metrics,routing='ORTHOGONAL',root=root,rank_policy=rank_policy)
  if model_order:inp['layoutOptions']['elk.layered.considerModelOrder.strategy']='NODES_AND_EDGES'
  save('elk-input.json',inp)
  run([scripts/'layout.cjs',elk,out/'elk-input.json',out/'elk-layout.json'])
  final=simplify(json.loads((out/'elk-layout.json').read_text(encoding='utf-8')));final,events=improve(model,metrics,final);save('family-adjustments.json',events);final,label_events=improve_labels(model,metrics,final,reuse_scene=reuse_marker_scene);save('marker-label-audit.json',label_events);save('final-layout.json',final)
  svg,scene=tree_draw(model,metrics,final);strategy='tree-hybrid'
 elif len(model['nodes'])<=5:
  svg,scene=render(model,metrics,'single',True,True);strategy=scene['strategy']
 else:
  inp=graph(model,metrics,orient='color' if policy=='compact' else False,loop_ports=True);inp['layoutOptions']['elk.spacing.nodeSelfLoop']='100';save('elk-input.json',inp)
  run([scripts/'layout.cjs',elk,out/'elk-input.json',out/'elk-layout.json'])
  svg,scene=draw(model,metrics,json.loads((out/'elk-layout.json').read_text(encoding='utf-8')));strategy='colored-layered' if policy=='compact' else 'layered'
 if len(scene['edges'])!=len(model['relations']):raise ValueError('Rendered relation count differs from input')
 (out/'diagram.svg').write_bytes(svg);save('layout.json',scene)
 (out/'diagram.drawio').write_bytes(export_drawio(model,scene,svg))
 if render_png:run([scripts/'rasterize.cjs',sharp,out/'diagram.svg',out/'diagram.png'])
 audit=audit_svg(svg,model);routes=measure(scene);save('visual-audit.json',audit);save('route-metrics.json',routes)
 result={'version':'1.9-preview','model_order':model_order,'requested_root':root,'status':'needs_review','policy':policy,'strategy':strategy,'geometry_status':audit['status'],'warnings':len(audit['findings']),'proper_crossings':routes['proper_crossings'],'seconds':time.perf_counter()-start,'input_sha256':hashlib.sha256(raw).hexdigest(),'svg_sha256':hashlib.sha256(svg).hexdigest(),'png_exports':int(render_png),'layout_calls':int(strategy in ('layered','colored-layered','tree-hybrid')),'visual_model_calls':0,'elk_module':elk,'fontconfig':fontconfig,'readability':'not_certified'}
 save('run.json',result);return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('model');p.add_argument('-o',required=True);p.add_argument('--node',default='node');p.add_argument('--sharp-module',default='sharp');p.add_argument('--elk-module',default='elkjs/lib/elk.bundled.js');p.add_argument('--fontconfig');p.add_argument('--layout-policy',choices=['tree','wide','compact'],default='tree');p.add_argument('--root',help='Business root ID for ordinary relation BFS orientation; inheritance keeps its own direction');p.add_argument('--model-order',action='store_true',help='Experimental soft node/edge input order preference');a=p.parse_args()
 print(json.dumps(build(a.model,a.o,a.node,a.sharp_module,a.elk_module,a.fontconfig,a.layout_policy,a.root,a.model_order)))
