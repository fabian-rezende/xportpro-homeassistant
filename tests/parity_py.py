"""O mesmo relatório do parity_ref.mjs, pelo porte em Python. Uso: python parity_py.py <appdata.json>"""
import json
import sys

import conftest  # noqa: F401
from xportpro_pure.catalog import Index
from xportpro_pure.commands import slider_command, switch_command


def attempt(f):
    try:
        return f()
    except Exception:  # noqa: BLE001
        return "ERR"


ix = Index(json.load(open(sys.argv[1], encoding="utf-8")))
out = []
for d in ix.devices:
    k, b = d["_c"], d["_c"].b
    out.append({
        "id": d["id"], "tipo": k.tipo, "sensor": k.sensor,
        "b": {"kinds": b.kinds, "addr": b.addr, "ch": str(b.ch), "vmin": b.vmin, "vmax": b.vmax, "get": b.get} if b else None,
        "sw": [attempt(lambda: switch_command(k.sw, d, True)), attempt(lambda: switch_command(k.sw, d, False))] if k.sw else None,
        "sl": [attempt(lambda v=v: slider_command(k.sl, d, v)) for v in (0, 2, 50, 99, 100)] if k.sl else None,
        "botoes": [c["id"] for c in k.botoes], "cortina": {p: c["id"] for p, c in k.cortina.items()},
    })
print(json.dumps(out))
