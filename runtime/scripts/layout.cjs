const fs=require('fs');
const [elkModule,input,output]=process.argv.slice(2);
const ELK=require(elkModule);
new ELK().layout(JSON.parse(fs.readFileSync(input,'utf8'))).then(g=>fs.writeFileSync(output,JSON.stringify(g,null,2))).catch(e=>{console.error(e);process.exitCode=1});
