"""Linhas de comando montadas exatamente como o app monta.

Porte de cloud-caserver/mcp-xportpro/src/comandos.js (userapp/src/motor.js e blind.js).

  send,1,<cmd_id>,<gw>             botão
  send,2,<cmd_id>,<gw>,<valor>     switch / deslizante (percentual 0..100)
  send,3,<cmd_id>,<gw>,<v>,<idx>   RGBW: idx 0 cor 0xRRGGBB, 1 ganho 0..100, 2 efeito 1..9
  sendScene,<id>                   cena
"""
from __future__ import annotations

import re

from .catalog import is_blind_slider, to_int

_RX_MARK = re.compile(r"<?min:\d+:max:\d+>?")

EFFECTS = ["Cores 1", "Cores 2", "Cores 3", "Pisca 1", "Pisca 2", "Pisca 3", "Trovão", "Sirene", "Branco"]


def _mp_string(c: dict, d: dict) -> str:
    p = c.get("p") or ""
    a = p.split(",")
    cid, gw = c["id"], d["gw"]
    if p[:1] == "{":
        mk = _RX_MARK.search(p)
        return f"send,2,{cid},{gw},{mk.group(0)}" if mk else f"send,1,{cid},{gw}"
    if a[0] in ("mdcmd_sendmd", "mdcmd_msendmd"):
        return f"send,2,{cid},{gw},{a[5]}" if len(a) == 6 else f"send,1,{cid},{gw}"
    if a[0] == "mdcmd_setallonmd" and len(a) == 4:
        return f"send,2,{cid},{gw},min:0:max:255"
    if a[0] in ("mdcmd_msendrele", "mdcmd_msenddimmer"):
        return f"send,2,{cid},{gw},{a[5]}" if len(a) == 6 else p
    if a[0] == "mdcmd_sendcmd":
        return f"send,2,{cid},{gw},{a[5]}" if len(a) > 6 else p
    if a[0] == "blindpos":
        return f"send,2,{cid},{gw},min:0:max:100"
    return f"send,1,{cid},{gw}"


def _minmax_of(msg: str) -> tuple[str, int]:
    s = msg.split(",")
    cv = s[4] if len(s) == 5 else "<VALOR>"
    mm = cv.split(":")
    return cv, (to_int(mm[3]) if len(mm) == 4 else 200)


def switch_command(c: dict, d: dict, on: bool) -> str:
    msg = _mp_string(c, d)
    s = msg.split(",")
    cv, vmax = _minmax_of(msg)
    if s[0] == "mdcmd_setallonmd":
        return f"{'mdcmd_setallonmd' if on else 'mdcmd_setalloffmd'},{s[1]},{s[2]},{s[3]}"
    if (c.get("p") or "")[:1] == "{":
        return msg.replace(cv, "100" if on else "0", 1)
    return msg.replace(cv, str(vmax) if on else "0", 1)


def slider_command(c: dict, d: dict, val: float) -> str:
    """Deslizante 0..100. Abaixo de 3 vira 0, como no app."""
    if is_blind_slider(c) and (c.get("p") or "").startswith("blindpos,"):
        p = round(val)
        # perto das pontas vai 0/100: fim de curso, a central recalibra a posição
        return f"send,2,{c['id']},{d['gw']},{0 if p < 3 else 100 if p > 97 else p}"
    msg = _mp_string(c, d)
    cv, _ = _minmax_of(msg)
    return msg.replace(cv, str(0 if val < 3 else int(val)), 1)


def button_command(c: dict, d: dict) -> str:
    return f"send,1,{c['id']},{d['gw']}"


def rgb_command(c: dict, d: dict, value: int, idx: int) -> str:
    return f"send,3,{c['id']},{d['gw']},{value},{idx}"


def scene_command(scene_id: int) -> str:
    return f"sendScene,{scene_id}"
