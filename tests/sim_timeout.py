"""Central simulada com um módulo que não responde.

Confere o comportamento do app: a linha `timeout,<addr>` não bloqueia nada, o módulo fica sem
leitura, a janela de leitura fecha (settled) e o comando continua sendo enviado.

Uso: python sim_timeout.py
"""
import asyncio

import conftest  # noqa: F401
from xportpro_pure import hub as hub_mod
from xportpro_pure.catalog import Index
from xportpro_pure.commands import switch_command

CATALOG = {
    "project": {"device_id": "XPR0-000000-0000", "name": "Simulada", "sync_counter": 1},
    "device_types": [{"id": 10, "cat": 1, "name": "Iluminação"}],
    "rooms": [{"id": 1, "section": 1, "name": "Estoque"}],
    "modules": [],
    "scenes": [],
    "devices": [
        # igual ao circuito Estoque da .226: liga/desliga pelo setallonmd
        {"id": 52, "type": 10, "gw": 1, "room": 1, "name": "Estoque", "visible": 1,
         "commands": [{"id": 2710, "gui": 4, "p": "mdcmd_setallonmd,1,228,105"}]},
        {"id": 53, "type": 10, "gw": 1, "room": 1, "name": "Responde", "visible": 1,
         "commands": [{"id": 2711, "gui": 4, "p": "mdcmd_setallonmd,1,228,106"}]},
    ],
}


async def main() -> None:
    received: list[str] = []

    async def central(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while raw := await reader.readline():
            line = raw.decode().strip()
            received.append(line)
            if line == "KEEPALIVE_KEEPALIVE":
                writer.write(b"KEEPALIVE_KEEPALIVE\r\n")
            elif line == "mdcmd_getmd,1,228,105":
                writer.write(b"timeout,01-E4-69\r\n")          # o módulo do Estoque não responde
            elif line == "mdcmd_getmd,1,228,106":
                writer.write(b"setmd,01-E4-6A,0,0,0,1,0,0\r\n")  # este responde: ligado
            await writer.drain()

    server = await asyncio.start_server(central, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    hub_mod.READ_WINDOW_S = 1  # não precisa esperar 6 s no teste
    ix = Index(CATALOG)
    estoque, responde = ix.devices
    hub = hub_mod.XPortHub("127.0.0.1", port, ix)
    notified: list[str] = []
    hub.listen(estoque["_c"].b.addr, lambda: notified.append("estoque"))
    await hub.start()

    await asyncio.sleep(1.6)
    assert hub.connected
    assert not hub.settled, "a janela de leitura ainda não devia ter fechado"
    assert hub.value(estoque["_c"].b) is None, "módulo com timeout não tem leitura"
    assert hub.value(responde["_c"].b) == ("1", "setmd"), hub.value(responde["_c"].b)
    await asyncio.sleep(1.2)
    assert hub.settled, "a janela de leitura devia ter fechado"
    assert "estoque" in notified, "as entidades precisam ser avisadas quando a janela fecha"
    assert not hasattr(hub, "module_ok"), "não existe mais bloqueio por módulo"

    cmd = switch_command(estoque["_c"].sw, estoque, True)
    await hub.send(cmd)
    await asyncio.sleep(0.2)
    # o mesmo que o app manda para o setallonmd: send,2 com o valor máximo
    assert cmd == "send,2,2710,1,255" and cmd in received, (cmd, received)

    await hub.stop()
    server.close()
    print("OK: timeout não bloqueia; sem leitura; janela fechou; comando enviado:", cmd)


asyncio.run(main())
