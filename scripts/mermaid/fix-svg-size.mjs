/**
 * Mermaid xuất SVG với width="100%" và không có height — nhiều trình xem
 * (Word, Inkscape, thư viện SVG cũ) không suy ra được kích thước.
 * Script gán width/height tuyệt đối từ viewBox và bỏ max-width.
 */
import fs from "node:fs/promises";
import path from "node:path";

const DIR = process.argv[2];
const files = (await fs.readdir(DIR)).filter((f) => f.endsWith(".svg")).sort();

for (const file of files) {
  const target = path.join(DIR, file);
  const svg = await fs.readFile(target, "utf8");

  const viewBox = svg.match(/viewBox="([\d.\-\s]+)"/);
  if (!viewBox) {
    console.log(`SKIP ${file}: không có viewBox`);
    continue;
  }

  const [, , vbWidth, vbHeight] = viewBox[1].trim().split(/\s+/).map(Number);
  const width = Math.ceil(vbWidth);
  const height = Math.ceil(vbHeight);

  const openTagEnd = svg.indexOf(">");
  let openTag = svg.slice(0, openTagEnd);
  const rest = svg.slice(openTagEnd);

  openTag = openTag
    .replace(/\swidth="[^"]*"/, "")
    .replace(/\sheight="[^"]*"/, "")
    .replace(/max-width:\s*[^;"]+;?/, "")
    .replace(/<svg/, `<svg width="${width}" height="${height}"`);

  await fs.writeFile(target, openTag + rest, "utf8");
  console.log(`OK   ${file}  ${width}x${height}`);
}

console.log(`\nDone: ${files.length} file`);
