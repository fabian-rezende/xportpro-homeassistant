"""Ar-condicionado no Modo smart. Porte de cloud-caserver/mcp-xportpro/src/ar.js.

  acset,<gw>,<cmd_id>,<dev>,<ligado>,<modo>,<vel>,<temp>   comando (firmware 21.01+)
  setacmd,<dev>,<ligado>,<modo>,<vel>,<temp>                estado, em broadcast

modo e vel são ÍNDICES em ac.modes / ac.fans. O cmd_id é o botão de alias
ac:<modo>:<vel>:<temp> (desligado: ac:off). O estado é o último comando que a central
mandou: o controle remoto do próprio ar não aparece aqui.

ON discreto (ac.on): o ar tem um IR só para ligar (alias ac:on). Desligado, o ajuste
fica travado até ligar.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


class AcError(Exception):
    """O projeto não tem o comando para o estado pedido."""


@dataclass(frozen=True)
class AcState:
    power: int = 0
    mode: int = 0
    fan: int = 0
    temp: int = 22


def has_discrete_on(d: dict) -> bool:
    return bool((d.get("ac") or {}).get("on"))


def _limits(d: dict) -> tuple[int, int]:
    ac = d["ac"]
    tmin, tmax = ac.get("tmin"), ac.get("tmax")
    return (16 if tmin is None else int(tmin), 30 if tmax is None else int(tmax))


def clamp(d: dict, st: AcState) -> AcState:
    """Estado guardado ajustado ao catálogo atual (o instalador pode ter tirado um modo)."""
    ac = d["ac"]
    tmin, tmax = _limits(d)
    return AcState(
        power=1 if st.power else 0,
        mode=st.mode if 0 <= st.mode < len(ac.get("modes") or []) else 0,
        fan=st.fan if 0 <= st.fan < len(ac.get("fans") or []) else 0,
        temp=min(max(tmin, st.temp), tmax),
    )


def default_state(d: dict) -> AcState:
    """Sem estado na central: desligado, 1º modo, 1ª velocidade, meio da faixa (ou a posição de fábrica)."""
    ac = d["ac"]
    tmin, tmax = _limits(d)
    st = AcState(temp=round((tmin + tmax) / 2))
    f = ac.get("onState") if has_discrete_on(d) else None
    if not isinstance(f, dict):
        return st
    modes, fans = ac.get("modes") or [], ac.get("fans") or []
    if f.get("mode") in modes:
        st = replace(st, mode=modes.index(f["mode"]))
    if f.get("fan") in fans:
        st = replace(st, fan=fans.index(f["fan"]))
    t = f.get("temp")
    if isinstance(t, int) and tmin <= t <= tmax:
        st = replace(st, temp=t)
    return st


def command(d: dict, st: AcState, *, turn_on_only: bool = False) -> str:
    """Linha acset para o estado. turn_on_only: no ON discreto vai o botão ac:on."""
    modes, fans = d["ac"].get("modes") or [], d["ac"].get("fans") or []
    cmds = d.get("commands") or []

    def by_alias(alias: str) -> dict | None:
        return next((c for c in cmds if c.get("alias") == alias), None)

    if turn_on_only and st.power and has_discrete_on(d):
        on = by_alias("ac:on")
        if not on:
            raise AcError(f'"{d.get("name")}" liga com comando próprio, mas está sem o comando Ligar (ac:on) no projeto')
        return f"acset,{d['gw']},{on['id']},{d['id']},1,{st.mode},{st.fan},{st.temp}"
    alias = f"ac:{modes[st.mode]}:{fans[st.fan]}:{st.temp}" if st.power else "ac:off"
    cmd = by_alias(alias)
    if not cmd:
        if not st.power:
            raise AcError(f'"{d.get("name")}" não tem o comando Desligar (ac:off) no projeto')
        raise AcError(f'"{d.get("name")}" não tem comando para {modes[st.mode]} / {fans[st.fan]} / {st.temp} °C')
    return f"acset,{d['gw']},{cmd['id']},{d['id']},{st.power},{st.mode},{st.fan},{st.temp}"


def parse_setacmd(f: list[str]) -> tuple[int, AcState] | None:
    """Linha setacmd -> (id do dispositivo, estado); None se não for."""
    if f[0] != "setacmd" or len(f) < 6:
        return None
    try:
        dev, power, mode, fan, temp = (int(x) for x in f[1:6])
    except ValueError:
        return None
    return dev, AcState(power, mode, fan, temp)
