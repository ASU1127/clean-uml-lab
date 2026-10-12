const fs = require('node:fs');
const [moduleName, input, output] = process.argv.slice(2);
const sharp = require(moduleName);
const escape = s => s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
(async () => {
  const items=JSON.parse(fs.readFileSync(input,'utf8')), result={};
  for(const item of items){
    const m=await sharp({text:{text:escape(item.text),font:`Arial ${item.size}`,dpi:72}}).metadata();
    result[item.key]={width:m.width,height:m.height};
  }
  fs.writeFileSync(output,JSON.stringify({method:'Sharp/Pango; same font configuration as PNG',items:result},null,2));
})().catch(e=>{console.error(e.message);process.exitCode=1;});
