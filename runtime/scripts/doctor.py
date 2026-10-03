"""Check local rendering dependencies; no diagram or network upload."""
import argparse,json,subprocess,sys
from clean_uml import runtime
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--node',default='node');p.add_argument('--sharp-module');p.add_argument('--elk-module');a=p.parse_args()
try:
 sharp,elk=runtime(a.node,a.sharp_module,a.elk_module)
 script='const sharp=require(process.argv[1]);const ELK=require(process.argv[2]);Promise.all([sharp({text:{text:"UML 中文",font:"Arial 16",dpi:72}}).metadata(),new ELK().knownLayoutAlgorithms()]).then(([m,alg])=>{if(!alg.some(a=>a.id==="org.eclipse.elk.layered"))throw Error("Layered unavailable");process.stdout.write(JSON.stringify({sharp:sharp.versions.sharp,textWidth:m.width,layered:true}))}).catch(e=>{console.error(e);process.exit(1)})'
 result=subprocess.run([a.node,'-e',script,sharp,elk],check=True,capture_output=True,text=True,timeout=30)
 print(json.dumps({'python':sys.version.split()[0],'node':subprocess.check_output([a.node,'--version'],text=True).strip(),'runtime':json.loads(result.stdout),'note':'Text measurement success does not prove Chinese glyph coverage; inspect the example PNG.'},ensure_ascii=False))
except (ValueError,OSError,subprocess.SubprocessError) as e:print('Clean UML doctor: '+str(e),file=sys.stderr);sys.exit(2)
