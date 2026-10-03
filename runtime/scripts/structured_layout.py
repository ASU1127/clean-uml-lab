import argparse,json,sys,subprocess,os,math,xml.etree.ElementTree as ET
from pathlib import Path
from lane_layout import render as lane_render,key,NS,element
from spread_layout import move_node
from audit import audit_svg
from notation import node_title,end_lines,qualifier_name
from qualifier_layout import geometry as qualifier_geometry
OPTIONS={'elk.algorithm':'layered','elk.direction':'RIGHT','elk.edgeRouting':'ORTHOGONAL','elk.hierarchyHandling':'INCLUDE_CHILDREN','elk.spacing.nodeNode':'52','elk.layered.spacing.nodeNodeBetweenLayers':'100','elk.spacing.edgeNode':'24','elk.spacing.edgeEdge':'18','elk.layered.spacing.edgeNodeBetweenLayers':'32','elk.layered.spacing.edgeEdgeBetweenLayers':'18','elk.spacing.labelLabel':'12','elk.edgeLabels.inline':'false','elk.layered.mergeEdges':'false','elk.layered.mergeHierarchyEdges':'false','elk.randomSeed':'42','elk.padding':'[top=24,left=24,bottom=24,right=24]'}
def graph(model,metrics,groups=None,direction='RIGHT',orient=False,port_space=48,loop_ports=False,root=None,rank_policy="uniform"):
 def w(s,italic=False):return metrics['items'][key(s,italic)]['width']+4
 children=[];degree={n['id']:0 for n in model['nodes']}
 for r in model['relations']:degree[r['source']]+=1;degree[r['target']]+=1
 for n in model['nodes']:
  fields=[m for m in n['members'] if '(' not in m];methods=[m for m in n['members'] if '(' in m]
  header=48 if n['kind'] in ('interface','enum') else 28
  width=max([w(node_title(model,n),n['kind']=='abstract')]+[w(m) for m in n['members']]+([w('«interface»')] if n['kind']=='interface' else [w('«enumeration»')] if n['kind']=='enum' else []))+24
  children.append({'id':n['id'],'width':width,'height':max(header+len(n['members'])*22+12+(6 if fields and methods else 0),degree[n['id']]*port_space+20),'layoutOptions':{'elk.spacing.portPort':str(port_space)}})
 rank={};adj={n['id']:set() for n in model['nodes']}
 for r in model['relations']:adj[r['source']].add(r['target']);adj[r['target']].add(r['source'])
 while len(rank)<len(adj):
  start=root if root is not None and root not in rank else max((n for n in adj if n not in rank),key=lambda n:(len(adj[n]),n));rank[start]=0;queue=[start]
  for n in queue:
   for other in sorted(adj[n]):
    if other not in rank:rank[other]=rank[n]+1;queue.append(other)
 if orient=='color':
  rank={}
  while len(rank)<len(adj):
   n=max((n for n in adj if n not in rank),key=lambda n:(len({rank[x] for x in adj[n] if x in rank}),len(adj[n]),n))
   used={rank[x] for x in adj[n] if x in rank};rank[n]=next(k for k in range(len(adj)) if k not in used)
 if rank_policy not in ('uniform','typed-distance'):raise ValueError('Unknown rank policy')
 if orient=='bfs':
  from orientation import inheritance_safe_rank,relation_distance_rank
  rank=relation_distance_rank(model,root) if rank_policy=='typed-distance' else inheritance_safe_rank(model,rank)
 edges=[]
 for i,r in enumerate(model['relations']):
  reverse=r['kind'] in ('generalization','realization')
  if orient and r['kind'] not in ('generalization','realization'):reverse=(rank[r['source']],r['source'])>(rank[r['target']],r['target'])
  e={'id':f'edge_{i}','semanticReverse':reverse,'sources':[r['target'] if reverse else r['source']],'targets':[r['source'] if reverse else r['target']],'labels':[]}
  for side,pos in [('source','TAIL'),('target','HEAD'),('center','CENTER')]:
   if reverse and side!='center':pos='HEAD' if pos=='TAIL' else 'TAIL'
   lines=([r['label']] if 'label' in r else []) if side=='center' else end_lines(r,side)
   if lines:e['labels'].append({'id':f'label_{i}_{side}','text':'\n'.join(lines),'lines':lines,'width':max(w(s) for s in lines),'height':18*len(lines),'layoutOptions':{'elk.edgeLabels.placement':pos}})
  for side in ('source','target'):
   if side+'_qualifier' in r:
    e.setdefault('qualifier_sizes',{})[side]={'width':max(44,w(qualifier_name(r,side))+16),'height':28}
    owner=next(n for n in children if n['id']==r[side]);owner['width']=max(owner['width'],e['qualifier_sizes'][side]['width']+16)
  if loop_ports and r['source']==r['target']:
   node=next(n for n in children if n['id']==r['source']);node['layoutOptions']['elk.portConstraints']='FIXED_SIDE'
   for side in ['source','target']:
    pid=f'port_{i}_{side}';node.setdefault('ports',[]).append({'id':pid,'width':0,'height':0,'layoutOptions':{'elk.port.side':'EAST'}});e[side+'s']=[pid]
  edges.append(e)
 if groups:
  byid={n['id']:n for n in children};used=set();parents=[]
  for j,g in enumerate(groups):
   if any(n not in byid or n in used for n in g):raise ValueError('invalid groups')
   used.update(g);parents.append({'id':f'group_{j}','children':[byid[n] for n in g],'layoutOptions':{'elk.direction':'RIGHT','elk.padding':'[top=24,left=24,bottom=24,right=24]'}})
  children=parents+[n for n in children if n['id'] not in used]
 return {'id':'root','layoutOptions':{**OPTIONS,'elk.direction':direction},'children':children,'edges':edges}
def draw(model,metrics,g):
 base,old=lane_render(model,metrics,compact=True,reuse=True,nodes_only=True);base=ET.fromstring(base)
 root=ET.Element('{'+NS+'}svg',{'viewBox':f'0 0 {g["width"]} {g["height"]}','width':str(g['width']),'height':str(g['height'])})
 element(root,'rect',x=0,y=0,width=g['width'],height=g['height'],fill='white')
 nodes={};edges=[];containers={'root':(0,0)}
 def collect(c,ox=0,oy=0):
  for n in c.get('children',[]):
   x=ox+n.get('x',0);y=oy+n.get('y',0)
   if 'children' in n:containers[n['id']]=(x,y);collect(n,x,y)
   else:nodes[n['id']]={**n,'x':x,'y':y}
  for e in c.get('edges',[]):edges.append((e,ox,oy))
 collect(g);paths=[]
 for edge,ox,oy in edges:
  ox,oy=containers.get(edge.get('container'),(ox,oy))
  i=int(edge['id'].split('_')[1]);r=model['relations'][i];kind=r['kind'];reverse=edge.get('semanticReverse',kind in ('generalization','realization'))
  group=element(root,'g',id=edge['id'],**{'class':'link','data-entity-1':'node_'+r['source'],'data-entity-2':'node_'+r['target']})
  for section in edge.get('sections',[]):
   points=[(p['x']+ox,p['y']+oy) for p in [section['startPoint']]+section.get('bendPoints',[])+[section['endPoint']]]
   if reverse:points.reverse()
   points,qualifiers=qualifier_geometry(model,nodes,r,points,edge.get('qualifier_sizes',{}))
   source,target=points[0],points[-1];su=(points[1][0]-source[0],points[1][1]-source[1]);tu=(points[-2][0]-target[0],points[-2][1]-target[1]);sl=math.hypot(*su);tl=math.hypot(*tu);su=(su[0]/sl,su[1]/sl);tu=(tu[0]/tl,tu[1]/tl)
   visible=list(points)
   def polygon(p,u,kind):
    x,y=p;ux,uy=u;px,py=-uy,ux
    if kind=='triangle':coords=[p,(x+ux*12+px*6,y+uy*12+py*6),(x+ux*12-px*6,y+uy*12-py*6)]
    else:coords=[p,(x+ux*8+px*5,y+uy*8+py*5),(x+ux*16,y+uy*16),(x+ux*8-px*5,y+uy*8-py*5)]
    element(group,'polygon',points=' '.join(f'{a},{b}' for a,b in coords),fill='black' if kind=='composition' else 'white',stroke='black')
   if kind in ('composition','aggregation'):visible[0]=(source[0]+su[0]*16,source[1]+su[1]*16)
   if kind in ('generalization','realization'):visible[-1]=(target[0]+tu[0]*12,target[1]+tu[1]*12)
   path=element(group,'path',d='M'+' L'.join(f'{x},{y}' for x,y in visible),fill='none',stroke='black',stroke_width=1.1)
   if kind in ('dependency','realization'):path.set('stroke-dasharray','6,4')
   if kind in ('composition','aggregation'):polygon(source,su,kind)
   if kind in ('generalization','realization'):polygon(target,tu,'triangle')
   if kind=='dependency':
    x,y=target;ux,uy=tu;px,py=-uy,ux;element(group,'path',d=f'M{x+ux*10+px*5},{y+uy*10+py*5} L{x},{y} L{x+ux*10-px*5},{y+uy*10-py*5}',fill='none',stroke='black')
   navigation=r.get('navigability','--')
   for side,p,u in [('source',source,su),('target',target,tu)]:
    if (side=='source' and navigation not in ('<-','<->')) or (side=='target' and navigation not in ('->','<->')):continue
    x,y=p;ux,uy=u;px,py=-uy,ux
    element(group,'path',d=f'M{x+ux*10+px*5},{y+uy*10+py*5} L{x},{y} L{x+ux*10-px*5},{y+uy*10-py*5}',fill='none',stroke='black',**{'data-marker':'navigability','data-end':side})
   paths.append({'index':i,'points':points,**({'qualifiers':qualifiers} if qualifiers else {})})
  for label in edge.get('labels',[]):
   for j,s in enumerate(label['lines']):
    t=element(group,'text',x=label['x']+ox,y=label['y']+oy+14+18*j,font_family='Arial',font_size=16,fill='black',textLength=metrics['items'][key(s)]['width']+4,lengthAdjust='spacingAndGlyphs');t.text=s
  for side,q in qualifiers.items():
   widget=element(group,'g',id=edge['id']+'_qualifier_'+side,**{'class':'qualifier','data-end':side,'data-classifier':q['classifier']})
   element(widget,'rect',x=q['x'],y=q['y'],width=q['width'],height=q['height'],fill='white',stroke='black',stroke_width=1)
   text=element(widget,'text',x=q['x']+8,y=q['y']+20,font_family='Arial',font_size=16,fill='black',textLength=metrics['items'][key(q['name'])]['width']+4,lengthAdjust='spacingAndGlyphs');text.text=q['name']
 for nid,n in nodes.items():
  group=base.find(f'.//*[@id="node_{nid}"]');move_node(group,n['x']-old['nodes'][nid]['x'],n['y']-old['nodes'][nid]['y']);group.find('{'+NS+'}rect').set('height',str(n['height']));root.append(group)
 return ET.tostring(root,encoding='utf-8',xml_declaration=True),{'nodes':nodes,'edges':paths,'width':g['width'],'height':g['height']}
