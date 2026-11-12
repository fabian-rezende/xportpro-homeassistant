"""Teste ao vivo, só leitura: lê o catálogo de uma central e mostra o estado de cada dispositivo.

Uso: python live_read.py <ip> [segundos]. Não aciona nada: manda só o que o app manda ao abrir
(KEEPALIVE, getmodulesstatus e mdcmd_getmd).
"""
import asyncio
import collections
import json
import sys
import urllib.request

import conftest  # noqa: F401
from xportpro_pure.ac import clamp
from xportpro_pure.catalog import Index, describe
from xportpro_pure.hub import XPortHub


async def main(host: str, seconds: float) -> None:
    raw = await asyncio.to_thread(lambda: urllib.request.urlopen(f"http://{host}/appdata.json", timeout=30).read())
    ix = Index(json.loads(raw))
    print(f"catálogo: {len(raw)} B, central {ix.serial}, projeto '{ix.project_name}', contador {ix.sync_counter}")
    print("tipos:", dict(collections.Counter(d["_c"].tipo for d in ix.devices)), "| cenas:", len(ix.scenes))
    changes = []
    hub = XPortHub(host, 4998, ix, on_sync_counter=changes.append)
    await hub.start()
    await asyncio.sleep(seconds)
    ok = sem = 0
    for d in ix.devices:
        k = d["_c"]
        room = ix.room_name(d.get("room")) or "-"
        if k.tipo == "ar":
            st = hub.ac_state(d["id"])
            print(f"  [{k.tipo:9}] {room} / {d.get('name')}: {clamp(d, st) if st else 'sem estado na central'}")
            continue
        if not k.b:
            continue
        got = hub.value(k.b)
        if got:
            ok += 1
            print(f"  [{k.tipo:9}] {room} / {d.get('name')}: {describe(d, got[0], got[1])}  ({k.b.addr} ch {k.b.ch}, {got[1]})")
        else:
            sem += 1
            print(f"  [{k.tipo:9}] {room} / {d.get('name')}: SEM LEITURA ({k.b.addr} ch {k.b.ch})")
    print(f"com leitura: {ok}, sem leitura: {sem}, contador diferente do catálogo: {changes}")
    await hub.stop()


asyncio.run(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 7))
