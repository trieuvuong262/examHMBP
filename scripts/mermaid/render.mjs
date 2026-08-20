import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import path from "node:path";

const execFileAsync = promisify(execFile);

const SRC = process.argv[2];
const OUT = process.argv[3];
const CONFIG = path.join(import.meta.dirname, "mermaid.config.json");
const MMDC_REL = path.join("node_modules", "@mermaid-js", "mermaid-cli", "src", "cli.js");

/** Trên Windows không spawn được mmdc.cmd (EINVAL) — phải gọi trực tiếp cli.js bằng node. */
async function resolveMmdc() {
  if (process.env.MMDC_CLI) return process.env.MMDC_CLI;
  let dir = import.meta.dirname;
  for (let i = 0; i < 6; i += 1) {
    for (const candidate of [
      path.join(dir, MMDC_REL),
      path.join(dir, ".tooling", "mermaid", MMDC_REL),
    ]) {
      try {
        await fs.access(candidate);
        return candidate;
      } catch {
        /* thử ứng viên tiếp theo */
      }
    }
    dir = path.dirname(dir);
  }
  throw new Error(
    "Không tìm thấy mermaid-cli. Chạy `npm install @mermaid-js/mermaid-cli` " +
      "rồi đặt MMDC_CLI trỏ tới node_modules/@mermaid-js/mermaid-cli/src/cli.js",
  );
}

const MMDC = await resolveMmdc();

const extractBlocks = (text) =>
  [...text.matchAll(/```mermaid\r?\n([\s\S]*?)```/g)].map((m) => m[1].trimEnd());

await fs.mkdir(OUT, { recursive: true });
const files = (await fs.readdir(SRC)).filter((f) => f.endsWith(".md")).sort();

const tmp = path.join(OUT, ".mmd");
await fs.mkdir(tmp, { recursive: true });

let ok = 0;
const failed = [];

for (const file of files) {
  const base = path.basename(file, ".md");
  const blocks = extractBlocks(await fs.readFile(path.join(SRC, file), "utf8"));

  for (const [i, block] of blocks.entries()) {
    const name = blocks.length > 1 ? `${base}-${i + 1}` : base;
    const mmdPath = path.join(tmp, `${name}.mmd`);
    const svgPath = path.join(OUT, `${name}.svg`);
    await fs.writeFile(mmdPath, block, "utf8");

    try {
      await execFileAsync(
        process.execPath,
        [MMDC, "-i", mmdPath, "-o", svgPath, "-c", CONFIG, "-b", "white"],
        { maxBuffer: 32 * 1024 * 1024 },
      );
      const { size } = await fs.stat(svgPath);
      console.log(`OK   ${name}.svg  ${(size / 1024).toFixed(0)} KB`);
      ok += 1;
    } catch (err) {
      console.log(`FAIL ${name}: ${(err.stderr || err.message).split("\n")[0]}`);
      failed.push(name);
    }
  }
}

await fs.rm(tmp, { recursive: true, force: true });
console.log(`\nDone: ${ok} SVG${failed.length ? `, failed: ${failed.join(", ")}` : ""}`);
