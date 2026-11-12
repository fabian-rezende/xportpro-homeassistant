"""Conexão com a central pela rede local (TCP 4998) e a memória do estado dos módulos.

Uma única conexão por central (o pool da central é de 7 a 9 clientes). O estado chega por
push: a central manda as linhas setXXmd a todos os clientes a cada mudança. Regras tiradas
do userapp (motor.js):

  - KEEPALIVE_KEEPALIVE ao conectar e a cada 25 s (a central devolve o eco);
  - getmodulesstatus uma vez ao conectar (a central aceita 1 a cada 5 s);
  - mdcmd_getmd em lotes de 12 linhas a cada 150 ms (o buffer da central é de ~5 KB);
  - a cada 60 s, mdcmd_getmd só dos módulos sem notícia há mais de 60 s: o xConfig cala os
    avisos por ~5 s quando sincroniza, e uma mudança nessa janela se perde.

Sem dependência do Home Assistant.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import logging
import socket
import time
from typing import Any

from .ac import AcState, parse_setacmd
from .catalog import KINDS_FB, Binding, Index, to_int, value_from_line

_LOGGER = logging.getLogger(__name__)

KEEPALIVE_S = 25
RX_TIMEOUT_S = 90          # 3 keepalives sem eco: conexão morta
RESWEEP_S = 60
BATCH = 12
BATCH_PAUSE_S = 0.15
CONNECT_TIMEOUT_S = 10
MAX_BACKOFF_S = 60

Listener = Callable[[], None]


class XPortHub:
    """Sessão com uma central xPortPro."""

    def __init__(self, host: str, port: int, index: Index, on_sync_counter: Callable[[int], None] | None = None) -> None:
        self.host = host
        self.port = port
        self.index = index
        self.connected = False
        self._on_sync_counter = on_sync_counter
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._first = asyncio.Event()
        self._closing = False
        self._listeners: dict[str, set[Listener]] = {}
        # ADDR -> { kind -> (fields, t), "bm": { par -> (fields, t) } }
        self._fb: dict[str, dict[str, Any]] = {}
        self._seen: dict[str, float] = {}
        self._timeouts: set[str] = set()
        self._ac: dict[int, AcState] = {}
        # o que as plataformas criaram: o que não estiver aqui saiu do projeto e é removido
        self.unique_ids: set[str] = set()
        self.device_ids: set[str] = {index.serial}
        # endereço -> linha de leitura, de todos os dispositivos com módulo
        self._targets: dict[str, str] = {}
        for d in index.devices:
            b: Binding | None = d["_c"].b
            if b and b.get:
                self._targets.setdefault(b.addr, b.get)

    # ------------------------------------------------------------------ ciclo de vida
    async def start(self) -> None:
        """Abre a conexão e espera a primeira tentativa. ConnectionError se a central não atender."""
        self._task = asyncio.create_task(self._run(), name=f"xportpro-{self.host}")
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._first.wait(), CONNECT_TIMEOUT_S + 2)
        if not self.connected:
            await self.stop()
            raise ConnectionError(f"a central em {self.host}:{self.port} não atendeu")

    async def stop(self) -> None:
        self._closing = True
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        self._set_connected(False)

    async def _run(self) -> None:
        backoff = 2
        while not self._closing:
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT_S)
            except (OSError, asyncio.TimeoutError) as err:
                _LOGGER.debug("xPortPro %s: sem conexão (%s)", self.host, err)
                self._first.set()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_S)
                continue
            backoff = 2
            sock = writer.get_extra_info("socket")
            if sock is not None:
                with contextlib.suppress(OSError):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self._writer = writer
            self._seen.clear()
            self._timeouts.clear()
            self._set_connected(True)
            self._first.set()
            chores = asyncio.create_task(self._chores())
            try:
                while True:
                    raw = await asyncio.wait_for(reader.readline(), RX_TIMEOUT_S)
                    if not raw:
                        break
                    line = raw.decode("latin-1").strip()
                    if line:
                        self._on_line(line)
            except (OSError, asyncio.TimeoutError, ValueError, asyncio.IncompleteReadError) as err:
                _LOGGER.debug("xPortPro %s: conexão caiu (%s)", self.host, err)
            finally:
                chores.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await chores
                self._writer = None
                writer.close()
                self._set_connected(False)
            if not self._closing:
                await asyncio.sleep(backoff)

    async def _chores(self) -> None:
        """Estado inicial, keepalive e a revisão periódica."""
        with contextlib.suppress(ConnectionError, OSError):
            await self.send("KEEPALIVE_KEEPALIVE")
            await self.send("getmodulesstatus")
            await asyncio.sleep(1.2)
            await self._sweep(max_age=None)
            last_sweep = time.monotonic()
            while True:
                await asyncio.sleep(KEEPALIVE_S)
                await self.send("KEEPALIVE_KEEPALIVE")
                if time.monotonic() - last_sweep >= RESWEEP_S:
                    last_sweep = time.monotonic()
                    await self._sweep(max_age=RESWEEP_S)

    async def _sweep(self, max_age: float | None) -> None:
        """mdcmd_getmd dos módulos sem notícia (todos os que ainda não falaram, se max_age=None)."""
        now = time.monotonic()
        lines = [
            get for addr, get in self._targets.items()
            if addr not in self._seen or (max_age is not None and now - self._seen[addr] > max_age)
        ]
        for i in range(0, len(lines), BATCH):
            if i:
                await asyncio.sleep(BATCH_PAUSE_S)
            await self.send(*lines[i:i + BATCH])

    # ------------------------------------------------------------------ envio
    async def send(self, *lines: str) -> None:
        """Manda uma ou mais linhas. ConnectionError se a central não está conectada."""
        writer = self._writer
        if writer is None or writer.is_closing():
            raise ConnectionError("a central xPortPro não está conectada")
        writer.write("".join(line + "\r\n" for line in lines).encode("latin-1"))
        await writer.drain()

    # ------------------------------------------------------------------ recepção
    def _on_line(self, line: str) -> None:
        f = line.split(",")
        k = f[0]
        if k in KINDS_FB and len(f) > 1:
            addr = f[1].strip().upper()
            now = time.monotonic()
            mod = self._fb.setdefault(addr, {"bm": {}})
            if k == "setbmcb0md":
                if len(f) > 2:
                    mod["bm"][str(to_int(f[2]))] = (f, now)
            else:
                mod[k] = (f, now)
            self._seen[addr] = now
            self._timeouts.discard(addr)
            self._notify(addr)
        elif k == "timeout" and len(f) > 1:
            addr = f[1].strip().upper()
            if addr in self._targets:
                self._timeouts.add(addr)
                self._seen[addr] = time.monotonic()
                self._notify(addr)
        elif k == "setacmd":
            parsed = parse_setacmd(f)
            if parsed:
                self._ac[parsed[0]] = parsed[1]
                self._notify(f"ac:{parsed[0]}")
        elif k == "sync_counter" and len(f) > 1 and self._on_sync_counter:
            n = to_int(f[1], -1)
            if n >= 0 and n != self.index.sync_counter:
                self._on_sync_counter(n)

    # ------------------------------------------------------------------ leitura
    def value(self, b: Binding) -> tuple[str, str] | None:
        """Último (valor, linha de origem) do canal de um dispositivo."""
        mod = self._fb.get(b.addr)
        if not mod:
            return None
        if b.kinds[0] == "setbmcb0md":
            rec = mod["bm"].get(str(to_int(b.ch)))
            if not rec:
                return None
            v = value_from_line("setbmcb0md", rec[0], b.ch)
            return None if v is None else (v, "setbmcb0md")
        best: tuple[str, tuple[list[str], float]] | None = None
        for k in b.kinds:
            rec = mod.get(k)
            if rec and (best is None or rec[1] > best[1][1]):
                best = (k, rec)
        if best is None:
            return None
        v = value_from_line(best[0], best[1][0], b.ch)
        return None if v is None else (v, best[0])

    def module_ok(self, addr: str) -> bool:
        """False quando o módulo não respondeu à central (linha timeout)."""
        return addr not in self._timeouts

    def ac_state(self, dev_id: int) -> AcState | None:
        return self._ac.get(dev_id)

    # ------------------------------------------------------------------ ouvintes
    def listen(self, key: str, cb: Listener) -> Callable[[], None]:
        """Avisa cb quando muda o módulo `key` (endereço), o ar "ac:<id>" ou a conexão."""
        self._listeners.setdefault(key, set()).add(cb)

        def remove() -> None:
            self._listeners.get(key, set()).discard(cb)

        return remove

    def _notify(self, key: str) -> None:
        for cb in list(self._listeners.get(key, ())):
            cb()

    def _set_connected(self, state: bool) -> None:
        if state == self.connected:
            return
        self.connected = state
        _LOGGER.info("xPortPro %s: %s", self.host, "conectada" if state else "desconectada")
        for cbs in list(self._listeners.values()):
            for cb in list(cbs):
                cb()
