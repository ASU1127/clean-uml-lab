const fs = require('fs');
const [moduleName, input, output] = process.argv.slice(2);
const sharp = require(moduleName);
const escape = s => s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
(async () => {
 const items = JSON.parse(fs.readFileSync(input, 'utf8'));
 const result = {};
 for (const item of items) {
  const m = await sharp({text:{text:escape(item.text),font:item.italic?'Arial Italic 16':'Arial 16',dpi:72}}).metadata();
  result[item.key] = {width:m.width,height:m.height};
 }
 fs.writeFileSync(output,JSON.stringify({font:'Arial',size:16,method:'Sharp/Pango text measurement, same font config as PNG',items:result},null,2));
})().catch(error => {console.error(error.message);process.exitCode=1;});
