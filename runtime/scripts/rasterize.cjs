// Final SVG is the source of pixels. All experiment arms use the same rasterizer.
const [moduleName, input, output] = process.argv.slice(2);
require(moduleName)(input).flatten({background:'#ffffff'}).png().toFile(output).catch(error => { console.error(error.message); process.exitCode=1; });
