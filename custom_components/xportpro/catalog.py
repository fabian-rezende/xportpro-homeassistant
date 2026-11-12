"""Catálogo da central (appdata.json, slot 3) e o estado de cada dispositivo.

Porte fiel de cloud-caserver/mcp-xportpro/src/estado.js e catalogo.js, que por sua vez
espelham o userapp (userapp/src/motor.js). Sem dependência do Home Assistant.

  binding_for      device + comando -> endereço do módulo, canal, faixa e a linha de leitura
  value_from_line  linha setXXmd do módulo -> valor do canal
  describe         valor cru -> estado (ligado, nível, posição, cor, sensor)

Cortina: a central usa 0 = ABERTA e 100 = FECHADA. O cover.py inverte para o Home Assistant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

_INT = re.compile(r"^\s*([-+]?\d+)")


def to_int(value: Any, default: int = 0) -> int:
    """parseInt do JavaScript: lê os dígitos do começo ("200>" -> 200)."""
    m = _INT.match("" if value is None else str(value))
    return int(m.group(1)) if m else default


def _hex2(n: int) -> str:
    return f"{n & 255:02X}"


def addr_from_dec(a: Any, b: Any, c: Any) -> str:
    return f"{_hex2(to_int(a))}-{_hex2(to_int(b))}-{_hex2(to_int(c))}"


# device_types com endereço, canal e feedback. 30/31 são o Acionamento do Nexo Hub.
MODULE_TYPES = {10, 11, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 30, 31}
DIMMER_MT = {5, 7, 15, 19, 20, 21, 29}
MR_TYPES = {25, 26, 27, 28}
RX_TYPES = {29}
ALIAS_AUDIO = re.compile(r"^(mr|rx|av):", re.I)
KINDS_FB = frozenset(
    {
        "setmd", "setkp3x3md", "setkp4x3md", "setkp6x3md", "setbmmd", "seti433md",
        "setrgbwmd", "setcmd", "setdmmd", "setbmcb0md",
    }
)


def is_hub_relay(t: int) -> bool:
    return t in (22, 30)


def is_hub_dimmer(t: int) -> bool:
    return t in (23, 31)


@dataclass
class Binding:
    kinds: list[str]
    addr: str
    ch: str = "0"
    vmin: int = 0
    vmax: int = 255
    get: str = ""
    rf: bool = False
    tv: bool = False


@dataclass
class Kind:
    """O que o card do app usa: tipo, comando do estado e comandos de ação."""

    tipo: str
    principal: dict | None = None
    b: Binding | None = None
    sw: dict | None = None
    sl: dict | None = None
    sens: dict | None = None
    rgb: dict | None = None
    botoes: list[dict] = field(default_factory=list)
    cortina: dict[str, dict] = field(default_factory=dict)
    sensor: str | None = None
    tv: dict[str, dict | None] = field(default_factory=dict)


_RX_ADDR = re.compile(r'"targetaddr"\s*:\s*"([0-9A-Fa-f]{2})[:-]([0-9A-Fa-f]{2})[:-]([0-9A-Fa-f]{2})"')
_RX_MOTOR = re.compile(r'"cmd"\s*:\s*"motor\.')
_RX_PAIR = re.compile(r'"pair"\s*:\s*(\d+)')
_RX_N = re.compile(r'"n"\s*:\s*(\d+)')
_RX_MM = re.compile(r"min:(\d+):max:(\d+)")


def _binding_for_json(d: dict, c: dict) -> Binding | None:
    p = c.get("p") or ""
    ad = _RX_ADDR.search(p)
    if not ad:
        return None
    curtain = d["type"] == 24 or bool(_RX_MOTOR.search(p))
    ch = (_RX_PAIR if curtain else _RX_N).search(p)
    mm = _RX_MM.search(p)
    hx = [ad.group(i).upper() for i in (1, 2, 3)]
    if curtain:
        kinds = ["setbmcb0md"]
    elif is_hub_dimmer(d["type"]):
        kinds = ["setdmmd"]
    else:
        # a linha que volta é a do MÓDULO: há circuito do Hub Dimmer cadastrado como Hub Relé
        kinds = ["setcmd", "setdmmd"]
    return Binding(
        kinds=kinds,
        addr="-".join(hx),
        ch=str(to_int(ch.group(1))) if ch else "0",
        vmin=0 if curtain else (to_int(mm.group(1)) if mm else 0),
        vmax=255 if curtain else (to_int(mm.group(2)) if mm else 255),
        get="mdcmd_getmd," + ",".join(str(int(x, 16)) for x in hx),
    )


def blind_config(d: dict) -> dict | None:
    """Cortina RF com tempos (tipo 3): blind_config normalizado, ou None."""
    if not d or d.get("type") != 3:
        return None
    c = d.get("blind_config")
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except ValueError:
            return None
    if not isinstance(c, dict):
        return None

    def num(v: Any) -> int | None:
        m = _INT.match("" if v is None else str(v))
        return int(m.group(1)) if m else None

    up, down = num(c.get("up")), num(c.get("down"))
    if up is None or down is None:
        return None
    return {"up": up, "down": down, "stop": num(c.get("stop")), "slider": bool(c.get("slider"))}


def is_blind_slider(c: dict | None) -> bool:
    return bool(c) and (c.get("alias") == "blind:pos" or (c.get("p") or "").startswith("blindpos,"))


def blind_binding(d: dict) -> Binding:
    """Posição estimada por tempo: a central publica no endereço falso 7E-<hi>-<lo>."""
    hi, lo = (d["id"] >> 8) & 255, d["id"] & 255
    return Binding(["setbmcb0md"], f"7E-{_hex2(hi)}-{_hex2(lo)}", "0", 0, 255, f"mdcmd_getmd,126,{hi},{lo}", rf=True)


def av_config(d: dict) -> dict | None:
    c = d.get("av_config")
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except ValueError:
            c = None
    return c if isinstance(c, dict) else None


def tv_binding(d: dict) -> Binding:
    """TV ligada/desligada na memória da central: setmd,7D-<hi>-<lo>,0,0,0,<0|1>,0,0."""
    hi, lo = (d["id"] >> 8) & 255, d["id"] & 255
    return Binding(["setmd"], f"7D-{_hex2(hi)}-{_hex2(lo)}", "0", 0, 1, f"mdcmd_getmd,125,{hi},{lo}", tv=True)


def binding_for(d: dict, c: dict | None) -> Binding | None:
    if blind_config(d):
        return blind_binding(d) if c and is_blind_slider(c) else None
    if d["type"] not in MODULE_TYPES or not c or not c.get("p"):
        return None
    p: str = c["p"]
    if p[0] == "{":
        return _binding_for_json(d, c)
    a = p.split(",")
    if len(a) < 4:
        return None
    kinds = {
        12: ["seti433md"], 14: ["setbmmd"], 15: ["setrgbwmd"], 18: ["setcmd"],
        20: ["setdmmd"], 21: ["setbmcb0md"],
    }.get(d["type"], ["setmd", "setkp3x3md", "setkp4x3md", "setkp6x3md"])
    b = Binding(
        kinds=kinds, addr=addr_from_dec(a[1], a[2], a[3]), ch="0", vmin=30, vmax=200,
        get=f"mdcmd_getmd,{to_int(a[1])},{to_int(a[2])},{to_int(a[3])}",
    )
    mm = (a[5] if len(a) > 5 else "").split(":")
    if len(mm) == 4:
        b.vmin, b.vmax = to_int(mm[1]), to_int(mm[3])
    cmd = a[0]
    a4 = a[4] if len(a) > 4 else ""
    if cmd in ("mdcmd_sendmd", "mdcmd_msendmd"):
        b.ch = str(to_int(a4))
        if cmd == "mdcmd_msendmd" and c.get("gui") != 5:
            chn = to_int(a4)
            b.ch = "0" if chn & 1 else "1" if chn & 2 else "2" if chn & 4 else "3" if chn & 8 else b.ch
    elif cmd == "mdcmd_setallonmd":
        b.ch, b.vmin, b.vmax = "0", 0, 255
    elif cmd == "mdcmd_sendrgbmd":
        b.ch, b.vmin, b.vmax = "4", 0, 255
    elif cmd == "mdcmd_msendrele":
        chn = to_int(a4)
        b.ch = next((str(i) for i in range(10) if chn & (1 << i)), "0")
        b.vmin, b.vmax = 0, 255
    elif cmd == "mdcmd_msenddimmer":
        chn = to_int(a4)
        b.ch = next((str(i) for i in range(9) if chn & (1 << i)), "0")
        if len(mm) != 4:
            b.vmin, b.vmax = 0, 255
    elif cmd == "mdcmd_sendcmd":
        b.ch, b.vmin, b.vmax = str(to_int(a[6] if len(a) > 6 else "")), 0, 255
    else:
        return None
    return b


def value_from_line(k: str, f: list[str], ch: Any) -> str | None:
    """Valor do canal numa linha de feedback (None = a linha não traz esse canal)."""
    c, n = to_int(ch), len(f)

    def at(i: int) -> str | None:
        return f[i] if i < n else None

    if k == "setmd":
        return at(5 + c) if (c < 3 or n == 9) else None
    if k == "setkp3x3md":
        return at(8 + c) if c < 3 else None
    if k == "setkp4x3md":
        return at(9 + c) if c < 3 else None
    if k == "setkp6x3md":
        return at(11 + c) if c < 3 else None
    if k == "setbmmd":
        return at(6) if c == 0 else None
    if k == "setcmd":
        return at(14 + c) if (n == 24 and c < 10) else None
    if k == "setdmmd":
        return at(14 + c) if (n == 23 and c < 9) else None
    if k == "setbmcb0md":
        return f[5] if (n == 6 and to_int(f[2]) == c) else None
    if k == "setrgbwmd":
        if c != 4 or n < 10:
            return None
        color = (to_int(f[5]) << 16) | (to_int(f[6]) << 8) | to_int(f[7])
        return f"{to_int(f[9])}:{color}"
    if k == "seti433md":
        v = to_int(at(2 + c))
        if v <= 0:
            return None
        typ, st, bat = (v >> 5) & 7, (v >> 1) & 3, v & 1
        if typ == 1:
            return ("1" if bat else "-1") if st == 2 else ("2" if bat else "-2") if st == 1 else "0"
        if typ == 2:
            return ("3" if bat else "-3") if st == 2 else ("4" if bat else "-4") if st == 1 else "0"
        return "0"
    return None


def pct_of(b: Binding, v: Any) -> int:
    n = to_int(v)
    if n <= 0:
        return 0
    span = (b.vmax - b.vmin) or 1
    return max(1, min(100, round(100 / span * (n - b.vmin))))


def _seta_de(c: dict) -> str | None:
    t = str(c.get("text") or c.get("alias") or "").lower()
    if re.search(r"abr|sob|sub|cima|open|up", t):
        return "abrir"
    if re.search(r"par|paus|stop", t):
        return "parar"
    if re.search(r"fech|desc|baix|close|down", t):
        return "fechar"
    return None


def _setas_de_botoes(d: dict) -> dict[str, dict] | None:
    """Cortina só de botões: até 3 botões, cada um com um sentido pelo texto."""
    cmds = d["commands"]
    bts = [c for c in cmds if c.get("gui") == 0]
    if not bts or len(bts) > 3 or any(c.get("gui") not in (0, 1, 2) for c in cmds):
        return None
    s: dict[str, dict] = {}
    for c in bts:
        k = _seta_de(c)
        if not k or k in s:
            return None
        s[k] = c
    return s


_RX_ABRIR = re.compile(r"^(abr|sub|up\b|open)", re.I)
_RX_PARAR = re.compile(r"^(par|stop|pare)", re.I)
_RX_FECHAR = re.compile(r"^(fech|desc|down\b|close)", re.I)
_RX_MOTOR_CMD = re.compile(r'"cmd"\s*:\s*"(up|stop|down)"')


def _papel_cortina(c: dict) -> str | None:
    t = str(c.get("text") or "").strip()
    if _RX_ABRIR.search(t):
        return "abrir"
    if _RX_PARAR.search(t):
        return "parar"
    if _RX_FECHAR.search(t):
        return "fechar"
    p = c.get("p") or ""
    a = p.split(",")
    if a[0] == "mdcmd_sendcmd" and len(a) > 5 and a[4] == "2":
        return {0: "abrir", 1: "parar", 2: "fechar"}.get(to_int(a[5], -1))
    mj = _RX_MOTOR_CMD.search(p)
    if mj and "motor.cmd" in p:
        return {"up": "abrir", "stop": "parar", "down": "fechar"}[mj.group(1)]
    return None


def is_ac_smart(d: dict) -> bool:
    return d.get("type") == 5 and bool(d.get("ac_smart")) and bool(d.get("ac"))


class Index:
    """O catálogo indexado, com cada dispositivo já classificado (d["_c"])."""

    def __init__(self, db: dict) -> None:
        self.db = db
        project = db.get("project") or {}
        self.serial: str = str(project.get("device_id") or "")
        self.project_name: str = str(project.get("name") or "")
        self.sync_counter: int = to_int(project.get("sync_counter"))
        self.types = {t["id"]: t for t in db.get("device_types") or []}
        self.rooms = {r["id"]: r for r in db.get("rooms") or []}
        self.modules = {m["id"]: m for m in db.get("modules") or []}
        self.devices: list[dict] = db.get("devices") or []
        self.scenes: list[dict] = db.get("scenes") or []
        for d in self.devices:
            d["cat"] = (self.types.get(d.get("type")) or {}).get("cat") or 0
            d["commands"] = d.get("commands") or []
        for d in self.devices:
            d["_c"] = self._classify(d)

    def room_name(self, room_id: Any) -> str | None:
        return (self.rooms.get(room_id) or {}).get("name") or None

    def _is_dimmer(self, d: dict) -> bool:
        if d["cat"] != 1 and not is_hub_relay(d["type"]) and not is_hub_dimmer(d["type"]):
            return False
        m = self.modules.get(d.get("module")) if d.get("module") else None
        if m and m.get("type") in DIMMER_MT:
            return True
        return any(c.get("gui") == 3 or (c.get("p") or "").startswith("mdcmd_msenddimmer") for c in d["commands"])

    def _classify(self, d: dict) -> Kind:
        cmds: list[dict] = d["commands"]
        is_mod = d["type"] in MODULE_TYPES

        def find(g: int) -> dict | None:
            return next((c for c in cmds if c.get("gui") == g), None)

        sw = find(4) if is_mod else None
        sl = find(3) if is_mod else None
        sens = find(5) if is_mod else None
        rgb = find(6)
        botoes = [c for c in cmds if c.get("gui") == 0 and not ALIAS_AUDIO.search(c.get("alias") or "")]

        if is_ac_smart(d):
            return Kind("ar", botoes=botoes)
        if d["type"] in MR_TYPES:
            return Kind("multiroom")
        if d["type"] in RX_TYPES:
            return Kind("receiver")
        av = av_config(d) if d["type"] == 4 else None
        if av and (av.get("mr") or av.get("rx")):
            return Kind("audio_video", botoes=botoes)

        bl = blind_config(d)
        if bl:
            by_id = {c.get("id"): c for c in cmds}
            cortina = {k: by_id[i] for k, i in (("abrir", bl["up"]), ("parar", bl["stop"]), ("fechar", bl["down"])) if i in by_id}
            slb = next((c for c in cmds if is_blind_slider(c)), None) if bl["slider"] else None
            return Kind("cortina", principal=slb, b=blind_binding(d), sl=slb, botoes=botoes, cortina=cortina)

        sensor: str | None = None
        if d["type"] == 9:
            tipo = "camera"
        elif not is_mod:
            setas = _setas_de_botoes(d) if d["cat"] == 5 else None
            if setas:
                return Kind("cortina", botoes=botoes, cortina=setas)
            if av and av.get("tv"):
                tv = {
                    "ligar": next((c for c in botoes if c.get("alias") == "POWER_ON"), None),
                    "desligar": next((c for c in botoes if c.get("alias") == "POWER_OFF"), None),
                }
                return Kind("tv", b=tv_binding(d), botoes=botoes, tv=tv)
            tipo = "controle" if botoes else "outro"
        elif d["type"] in (14, 21, 24) or d["cat"] == 5:
            tipo = "cortina"
        elif d["type"] == 16 and sw:
            tipo, sensor = "sensor", "onoff"
        elif d["type"] == 15 or rgb:
            tipo = "rgbw"
        elif d["type"] in (12, 16) or (sens and not sw and not sl):
            tipo = "sensor"
        elif self._is_dimmer(d):
            tipo = "dimmer"
        elif sw:
            tipo = "rele"
        elif sl:
            tipo = "dimmer"
        else:
            tipo = "controle" if botoes else "outro"

        principal = None
        if tipo == "cortina":
            principal = sl
        elif tipo == "rgbw":
            principal = rgb or sl
        elif tipo == "sensor":
            principal = sw if sensor == "onoff" else sens
        elif tipo in ("dimmer", "rele"):
            principal = sw or sl
        b = binding_for(d, principal) if principal else None
        if not b and is_mod and tipo != "controle":
            # cortina só com botões: o endereço vem de qualquer comando
            b = next((x for x in (binding_for(d, c) for c in cmds) if x), None)
        if b and tipo != "cortina" and b.vmax == b.vmin:
            b.vmax = b.vmin + 1
        cortina = {}
        if tipo == "cortina":
            for c in botoes:
                papel = _papel_cortina(c)
                if papel and papel not in cortina:
                    cortina[papel] = c
        return Kind(tipo, principal, b, sw, sl, sens, rgb, botoes, cortina, sensor)


def describe(d: dict, v: Any, k: str) -> dict[str, Any]:
    """Valor cru -> estado, conforme o tipo. k = a linha de onde ele veio."""
    kind: Kind = d["_c"]
    b = kind.b
    assert b is not None
    if k == "setdmmd" and b.vmax <= 1:
        # setdmmd traz o nível 0..255 mesmo quando o comando é liga/desliga (min:0:max:1)
        b = Binding(b.kinds, b.addr, b.ch, 0, 255, b.get)
    s = str(v).strip()
    if kind.tipo == "rgbw":
        gain, _, color = s.partition(":")
        g, n = to_int(gain), to_int(color)
        return {"on": g > 0, "brightness": g, "rgb": ((n >> 16) & 255, (n >> 8) & 255, n & 255)}
    if kind.tipo == "tv":
        return {"on": to_int(s) > 0}
    if kind.tipo == "sensor" and kind.sensor == "onoff":
        return {"on": pct_of(b, s) > 0}
    if kind.tipo == "sensor":
        n = to_int(s)
        a = abs(n)
        # 1 fechado, 2 aberto (abertura); 3 livre, 4 presença (movimento); negativo = bateria fraca
        return {"on": a in (2, 4), "class": "opening" if a in (1, 2) else "motion" if a in (3, 4) else None, "low_battery": n < 0}
    if kind.tipo == "cortina":
        return {"position": pct_of(b, s)}
    if kind.tipo == "dimmer":
        p = pct_of(b, s)
        return {"on": p > 0, "level": p}
    return {"on": to_int(s) > 0}
