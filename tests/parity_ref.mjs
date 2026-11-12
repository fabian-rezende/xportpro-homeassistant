// Referência: o motor do MCP (porte fiel do userapp). Uso: node parity_ref.mjs <src do mcp> <appdata.json>
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const [src, file] = process.argv.slice(2);
const imp = (f) => import(pathToFileURL(path.join(src, f)).href);
const { indexar } = await imp('catalogo.js');
const { switchCommand, sliderCommand } = await imp('comandos.js');
const { valueFromLine } = await imp('estado.js');
const IX = indexar(JSON.parse(fs.readFileSync(file, 'utf8')));
const out = [];
for (const d of IX.dev.values()) {
  const k = d._c, b = k.b;
  const t = (f) => { try { return f(); } catch (e) { return 'ERR'; } };
  out.push({
    id: d.id, tipo: k.tipo, sensor: k.sensor || null,
    b: b ? { kinds: b.kinds, addr: b.addr, ch: String(b.ch), vmin: b.vmin, vmax: b.vmax, get: b.get } : null,
    sw: k.sw ? [t(() => switchCommand(k.sw, d, true)), t(() => switchCommand(k.sw, d, false))] : null,
    sl: k.sl ? [0, 2, 50, 99, 100].map(v => t(() => sliderCommand(k.sl, d, v))) : null,
    botoes: k.botoes.map(c => c.id), cortina: Object.fromEntries(Object.entries(k.cortina || {}).map(([p, c]) => [p, c.id])),
  });
}
console.log(JSON.stringify(out));
