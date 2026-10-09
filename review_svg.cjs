#!/usr/bin/env node
/** Offline text-bounds reviewer for complete Clean/PlantUML/Mermaid class SVGs. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),cp=require('node:child_process');
const {extract}=require('./svg_scene.cjs');
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const save=(p,v)=>fs.writeFileSync(p,JSON.stringify(v,null,2));
async function main(){
 const argv=process.argv.slice(2),svgFile=argv.shift(),opts={};
 for(let i=0;i<argv.length;i+=2){if(!argv[i].startsWith('--')||!argv[i+1])throw Error('Expected --option value');opts[argv[i].slice(2)]=argv[i+1];}
 if(!svgFile||!opts.model||!opts.output||!['clean','plantuml','mermaid'].includes(opts.engine))throw Error('Usage: node review_svg.cjs diagram.svg --model model.json --engine clean|plantuml|mermaid --output NEW_DIR [--browser PATH] [--puppeteer-module PATH] [--python PATH]');
 if(Object.keys(opts).some(k=>!['model','output','engine','browser','puppeteer-module','python'].includes(k)))throw Error('Unknown option');
 const src=path.resolve(svgFile),modelPath=path.resolve(opts.model),out=path.resolve(opts.output);
 if(fs.existsSync(out))throw Error('Output already exists; use a new directory');
 if(fs.statSync(src).size>10*1024*1024)throw Error('SVG exceeds 10 MB fixture budget');
 const model=JSON.parse(fs.readFileSync(modelPath,'utf8').replace(/^\uFEFF/,''));
 if(!Array.isArray(model.nodes)||!Array.isArray(model.relations)||model.nodes.length>100||model.relations.length>200)throw Error('Expected a bounded companion class model');
 const moduleName=opts['puppeteer-module']||'puppeteer-core',puppeteer=require(moduleName);
 const browserPath=opts.browser||['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe','/usr/bin/google-chrome','/usr/bin/chromium','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find(p=>fs.existsSync(p));
 if(!browserPath)throw Error('Pass --browser PATH for an installed Chrome/Chromium/Edge executable');
 fs.mkdirSync(out,{recursive:true});const start=Date.now();
 const provenance={scope:'One isolated offline SVG measurement and identical text-bounds rules. Does not operate a user browser or certify all UML semantics, pixel-ink collisions or human aesthetics.',engine:opts.engine,input_svg_sha256:sha(src),input_model_sha256:sha(modelPath),max_browser_measurements:1,max_layout_calls:0,max_pngs:0,repairs:0,browser_executable:browserPath,profile_policy:'New explicit profile under output; retained after closing. No recursive cleanup.'};save(path.join(out,'provenance.json'),provenance);
 let browser;
 try{
  browser=await puppeteer.launch({executablePath:browserPath,headless:true,timeout:30000,protocolTimeout:30000,userDataDir:path.join(out,'browser-profile'),args:['--disable-gpu','--disable-software-rasterizer','--disable-background-networking','--disable-component-update','--disable-default-apps','--disable-sync','--no-first-run','--no-default-browser-check']});
  const page=await browser.newPage();await page.setViewport({width:4000,height:3000,deviceScaleFactor:1});await page.setRequestInterception(true);
  page.on('request',r=>r.url().startsWith('data:')||r.url()==='about:blank'?r.continue():r.abort());
  await page.goto('about:blank');const scene=await extract(page,fs.readFileSync(src,'utf8'),model,opts.engine);save(path.join(out,'scene.json'),scene);
  const p=cp.spawnSync(opts.python||'python',['-X','utf8',path.join(__dirname,'review_rendered.py'),path.join(out,'scene.json'),'-o',path.join(out,'review.json')],{windowsHide:true,timeout:30000});
  if(p.status!==0)throw Error('Reviewer failed: '+p.stderr?.toString().slice(-600));
  const report=JSON.parse(fs.readFileSync(path.join(out,'review.json'),'utf8'));
  provenance.seconds=(Date.now()-start)/1000;provenance.source_unchanged=sha(src)===provenance.input_svg_sha256&&sha(modelPath)===provenance.input_model_sha256;provenance.completed=true;
  save(path.join(out,'provenance.json'),provenance);
  console.log(JSON.stringify({output:out,status:report.status,label_label:report.label_label_conflicts.length,label_classifier:report.label_classifier_conflicts.length,seconds:provenance.seconds}));
  process.exitCode=report.status==='needs_review'?2:0;
 }catch(e){provenance.error=e.message;provenance.completed=false;save(path.join(out,'provenance.json'),provenance);throw e;}
 finally{if(browser)await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=3;});
