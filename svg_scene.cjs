/** Geometry extraction inside the isolated offline vendor test browser. */
async function extract(page,svg,model,engine,step=2){
 return page.evaluate(({svg,model,engine,step})=>{
  const parsed=new DOMParser().parseFromString(svg,'image/svg+xml');
  if(parsed.querySelector('parsererror')||parsed.documentElement.localName!=='svg')throw Error('Invalid standalone SVG');
  for(const el of parsed.querySelectorAll('script,iframe,object,embed'))el.remove();
  for(const el of parsed.querySelectorAll('*'))for(const attribute of [...el.attributes])if(/^on/i.test(attribute.name))el.removeAttribute(attribute.name);
  const root=document.importNode(parsed.documentElement,true);
  const holder=document.createElement('div');holder.style.cssText='position:absolute;width:8000px;height:8000px';holder.appendChild(root);document.body.appendChild(holder);
  const inverse=root.getScreenCTM().inverse(),box=(el)=>{
   const b=el.getBBox(),m=inverse.multiply(el.getScreenCTM());
   const p=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));
   const x=Math.min(...p.map(p=>p.x)),y=Math.min(...p.map(p=>p.y));return {x,y,width:Math.max(...p.map(p=>p.x))-x,height:Math.max(...p.map(p=>p.y))-y};
  };
  const nodeByGroup=new Map(),nodes=[],paths=[];
  function addNode(id,group,shape){if(!group||!shape)throw Error('Missing classifier shape '+id);if(nodes.some(n=>n.id===id))throw Error('Duplicate classifier '+id);nodeByGroup.set(group,id);nodes.push({id,...box(shape)});}
  for(const node of model.nodes){
   if(engine==='clean'){
    const group=root.querySelector('[id="node_'+node.id+'"]');addNode(node.id,group,group?.querySelector('rect'));
   }else if(engine==='plantuml'){
    const group=[...root.querySelectorAll('g.entity')].find(g=>g.dataset.qualifiedName===node.id);addNode(node.id,group,group?.querySelector('rect'));
   }else if(engine==='mermaid'){
    const group=[...root.querySelectorAll('g.node')].find(g=>new RegExp('-classId-'+node.id.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'-\\d+$').test(g.id));
    addNode(node.id,group,group?.querySelector('.label-container'));
   }else throw Error('Unknown engine '+engine);
  }
  if(engine==='plantuml'&&root.querySelectorAll('g.entity').length!==nodes.length)throw Error('Unexpected rendered classifier');
  if(engine==='mermaid'&&root.querySelectorAll('g.node').length!==nodes.length)throw Error('Unexpected rendered classifier');
  function owner(el){for(let p=el.parentElement;p&&p!==root;p=p.parentElement)if(nodeByGroup.has(p))return nodeByGroup.get(p);return null;}
  if(engine==='clean'){
   for(const group of root.querySelectorAll('g[id^="edge_"]')){
    if(!/^edge_\d+$/.test(group.id))continue;const path=group.querySelector('path');if(!path)throw Error('Missing connector path '+group.id);paths.push({index:Number(group.id.slice(5)),path});
   }
  }else if(engine==='plantuml'){
   const entityBySvg=new Map([...nodeByGroup].map(([g,id])=>[g.id,id]));
   const groups=[...root.querySelectorAll('g.link')].sort((a,b)=>Number(a.dataset.sourceLine)-Number(b.dataset.sourceLine));
   for(const [index,g] of groups.entries()){
    const r=model.relations[index];if(!r)throw Error('Extra PlantUML connector');
    const a=entityBySvg.get(g.getAttribute('data-entity-1')),b=entityBySvg.get(g.getAttribute('data-entity-2'));
    if(!([a,b].includes(r.source)&&[a,b].includes(r.target)))throw Error('PlantUML declared endpoints do not match '+index);
    const path=g.querySelector('path');if(!path)throw Error('Missing PlantUML path '+index);paths.push({index,path});
   }
  }else{
   for(const path of root.querySelectorAll('path[data-edge="true"]')){
    const index=Number(path.dataset.id?.match(/_(\d+)$/)?.[1])-1,r=model.relations[index];
    if(!r||!(path.dataset.id===`id_${r.source}_${r.target}_${index+1}`||(['generalization','realization'].includes(r.kind)&&path.dataset.id===`id_${r.target}_${r.source}_${index+1}`)))throw Error('Mermaid edge id does not match declared endpoints '+path.dataset.id);
    paths.push({index,path});
   }
  }
  if(nodes.length!==model.nodes.length||paths.length!==model.relations.length||new Set(paths.map(e=>e.index)).size!==paths.length)throw Error('Incomplete or duplicated rendered topology');
  function simplify(points,epsilon=.2){
   if(points.length<=2)return points;
   const a=points[0],b=points.at(-1),dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy;let maximum=-1,pick=-1;
   for(let i=1;i<points.length-1;i++){
    const p=points[i],t=den?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)):0;
    const d=Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);if(d>maximum){maximum=d;pick=i;}
   }
   if(maximum<=epsilon)return [a,b];return [...simplify(points.slice(0,pick+1),epsilon).slice(0,-1),...simplify(points.slice(pick),epsilon)];
  }
  function turning(points){let value=0;for(let i=1;i<points.length-1;i++){
   const a=[points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]],b=[points[i+1][0]-points[i][0],points[i+1][1]-points[i][1]];
   if(Math.hypot(...a)>.0001&&Math.hypot(...b)>.0001)value+=Math.abs(Math.atan2(a[0]*b[1]-a[1]*b[0],a[0]*b[0]+a[1]*b[1]))*180/Math.PI;
  }return value;}
  const edges=paths.map(({index,path})=>{
   const length=path.getTotalLength(),count=Math.max(1,Math.ceil(length/step)),m=inverse.multiply(path.getScreenCTM());
   if(count>20000)throw Error('Connector exceeds sampling budget');
   const ps=Array.from({length:count+1},(_,i)=>{const p=path.getPointAtLength(length*i/count),t=new DOMPoint(p.x,p.y).matrixTransform(m);return [t.x,t.y];});
   return {index,source:model.relations[index].source,target:model.relations[index].target,points:simplify(ps),turn_degrees:turning(ps),length};
  });
  const texts=[];
  for(const text of root.querySelectorAll('text,foreignObject')){
   if(text.closest('defs'))continue;const value=(text.textContent||'').trim();if(!value)continue;
   let bounds;
   if(text.tagName==='foreignObject'){
    const walker=document.createTreeWalker(text,NodeFilter.SHOW_TEXT),rects=[];let part;
    while(part=walker.nextNode())if(part.textContent.trim()){
     const range=document.createRange();range.selectNodeContents(part);for(const r of range.getClientRects())if(r.width&&r.height)rects.push(r);range.detach();
    }
    if(!rects.length)continue;
    const p=rects.flatMap(r=>[[r.left,r.top],[r.right,r.top],[r.left,r.bottom],[r.right,r.bottom]]).map(([x,y])=>new DOMPoint(x,y).matrixTransform(inverse));
    const x=Math.min(...p.map(p=>p.x)),y=Math.min(...p.map(p=>p.y));bounds={x,y,width:Math.max(...p.map(p=>p.x))-x,height:Math.max(...p.map(p=>p.y))-y};
   }else bounds=box(text);
   const fontTarget=text.tagName==='foreignObject'?text.querySelector('span,p,div')||text:text;
   const size=parseFloat(getComputedStyle(fontTarget).fontSize);
   texts.push({text:value,node:owner(text),font_size:size,...bounds});
  }
  const vb=root.viewBox.baseVal;
  const result={width:vb.width,height:vb.height,nodes,edges,texts,engine,scope:'Actual rendered paths sampled in root SVG coordinates. Curves flattened to 0.2px tolerance; font and text bounds measured by the offline browser. Sampling is approximate and does not establish human preference or full UML conformance.',sampling_step:step};
  holder.remove();return result;
 },{svg,model,engine,step});
}
module.exports={extract};
