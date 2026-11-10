#!/usr/bin/env python3
r"""

# =============================================================================
# PROJETO:       PrintaAí 
# DESCRIÇÃO:     Ferramenta de captura de tela (Screenshot)
#                Inspirada no conceito do Lightshot.
#
# DESENVOLVEDOR: Marcos Barros
# LINGUAGEM:     Python
# VERSÃO:        1.2.1
# DATA:          10/11/2026
#
# FUNCIONALIDADES:
#   - Captura de regiões específicas da tela
#   - Seleção e edição de imagens
#   - Anotações e marcações sobre capturas
#   - Salvamento de screenshots
#   - Cópia de imagens para a área de transferência
#
# =============================================================================
cmd /c "C:\Print\gerar_exe.bat"

"""

import base64
import io
import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from tkinter import colorchooser, filedialog, messagebox, simpledialog

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageGrab, ImageTk

WINDOWS = sys.platform.startswith("win")

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    # Evita que a escala de DPI desalinhe as coordenadas da tela
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ----------------------------------------------------------------------------
# Tema
# ----------------------------------------------------------------------------
UI = {"esc": 1.0}  # fator de escala da interface (DPI), definido ao iniciar
FONTE_UI = "Segoe UI" if WINDOWS else "DejaVu Sans"
T = {
    "painel": "#111216", "painel_borda": "#2a2d34",
    "card": "#191b20", "card_borda": "#24272e", "card_hover": "#20232a",
    "btn": "#25282f", "btn_hover": "#30343c", "borda_btn": "#3a3e47",
    "texto": "#f1f2f4", "texto2": "#a3a8b3", "apagado": "#5a5f6a",
    "azul": "#1677ff", "azul_hover": "#3a8dff",
    "ativo_fundo": "#0f2547", "ativo_hover": "#14305a",
    "selecao": "#1e8fff", "verde": "#4cd471", "vermelho": "#ff6b6b",
}
CORES = ["#ff3b30", "#ff9500", "#ffd60a", "#34c759",
         "#0a84ff", "#af52de", "#000000", "#ffffff"]
CURSORES = {"nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw",
            "sw": "size_ne_sw", "n": "size_ns", "s": "size_ns",
            "e": "size_we", "w": "size_we"}
SECOES = ("captura", "ferramentas", "aparencia", "acoes")
FERRAMENTAS = (("caneta", "Pincel", "pincel"), ("linha", "Linha", "linha"),
               ("seta", "Seta", "seta"), ("retangulo", "Retângulo", "retangulo"),
               ("elipse", "Círculo", "circulo"), ("texto", "Texto", "texto"))
DICA_INICIAL = "Arraste para selecionar a área   •   F  tela inteira   •   J  janela ativa   •   Esc  cancela"
DICA_EDICAO = "Enter  copia e fecha   •   Ctrl+S  salvar como   •   Ctrl+Z  desfaz   •   Esc  cancela"


def px(v):
    """Converte unidades lógicas em pixels reais (escala de DPI)."""
    return int(round(v * UI["esc"]))


def fonte(tam, peso="normal"):
    return (FONTE_UI, -px(tam), peso)


def pasta_inicial():
    home = os.path.expanduser("~")
    for p in (os.path.join(home, "Pictures"), os.path.join(home, "Imagens"), home):
        if os.path.isdir(p):
            return p
    return os.getcwd()


ULTIMA_PASTA = {"v": None}

# ----------------------------------------------------------------------------
# Configurações salvas (%APPDATA%\PrintaAí\config.json)
# ----------------------------------------------------------------------------
CONFIG = {}


def caminho_config():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "PrintaAí", "config.json")


def carregar_config():
    padrao = {"pasta": pasta_inicial(), "formato": "png", "cor": CORES[0], "largura": 4,
              "ferramenta": "caneta", "recolhidos": [], "imgbb_chave": ""}
    try:
        with open(caminho_config(), encoding="utf-8") as f:
            dados = json.load(f)
        if isinstance(dados, dict):
            padrao.update({k: v for k, v in dados.items() if k in padrao})
    except Exception:
        pass
    CONFIG.clear()
    CONFIG.update(padrao)


def salvar_config():
    try:
        p = caminho_config()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Upload para o ImgBB (link público de compartilhamento)
# ----------------------------------------------------------------------------
# Chave usada quando o usuário não definiu a sua nas Configurações.
# Preencha antes de gerar o .exe para que ninguém precise criar uma conta.
IMGBB_CHAVE_PADRAO = ""
IMGBB_SITE_CHAVE = "https://api.imgbb.com/"


def chave_imgbb():
    return (CONFIG.get("imgbb_chave") or IMGBB_CHAVE_PADRAO or "").strip()


def enviar_imgbb(dados, chave, nome):
    """Envia a imagem (bytes) ao ImgBB e devolve o link direto público."""
    corpo = urllib.parse.urlencode({
        "image": base64.b64encode(dados).decode("ascii"),
        "name": nome,
    }).encode("ascii")
    req = urllib.request.Request(
        "https://api.imgbb.com/1/upload?key=" + urllib.parse.quote(chave),
        data=corpo, headers={"User-Agent": "PrintaAi"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as ex:
        try:
            msg = json.load(ex).get("error", {}).get("message") or ""
        except Exception:
            msg = ""
        if ex.code in (400, 401, 403) and "key" in msg.lower():
            raise RuntimeError("Chave da API do ImgBB inválida. Confira em Configurações.")
        raise RuntimeError(f"O ImgBB recusou o envio (HTTP {ex.code}). {msg}".strip())
    except urllib.error.URLError as ex:
        raise RuntimeError(f"Sem conexão com o ImgBB: {ex.reason}")
    dados_resp = resp.get("data") or {}
    link = dados_resp.get("url") or dados_resp.get("url_viewer")
    if not link:
        raise RuntimeError("Resposta inesperada do ImgBB.")
    return link


# ----------------------------------------------------------------------------
# Área de transferência (copiar imagem para colar em chats)
# ----------------------------------------------------------------------------
def copiar_imagem_para_clipboard(img):
    if WINDOWS:
        saida = io.BytesIO()
        img.convert("RGB").save(saida, "BMP")
        dados = saida.getvalue()[14:]  # remove o cabeçalho do arquivo BMP -> DIB
        saida.close()

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE

        GMEM_MOVEABLE, CF_DIB = 0x0002, 8
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dados))
        ptr = kernel32.GlobalLock(h)
        ctypes.memmove(ptr, dados, len(dados))
        kernel32.GlobalUnlock(h)

        for _ in range(20):  # a área de transferência pode estar ocupada
            if user32.OpenClipboard(None):
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("Não foi possível abrir a área de transferência.")
        try:
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_DIB, h)
        finally:
            user32.CloseClipboard()

    elif sys.platform == "darwin":
        caminho = os.path.join(tempfile.gettempdir(), "captura_tmp.png")
        img.save(caminho, "PNG")
        subprocess.run(
            ["osascript", "-e",
             f'set the clipboard to (read (POSIX file "{caminho}") as «class PNGf»)'],
            check=True,
        )
    else:  # Linux
        saida = io.BytesIO()
        img.save(saida, "PNG")
        dados = saida.getvalue()
        for cmd in (["wl-copy", "--type", "image/png"],
                    ["xclip", "-selection", "clipboard", "-t", "image/png"]):
            try:
                subprocess.run(cmd, input=dados, check=True)
                return
            except FileNotFoundError:
                continue
        raise RuntimeError("Instale 'wl-clipboard' ou 'xclip' para copiar imagens.")


# ----------------------------------------------------------------------------
# Geometria e renderização final (resolução original, com suavização)
# ----------------------------------------------------------------------------
def geometria_seta(p1, p2, largura):
    """Retorna (fim_da_haste, [pontos do triângulo da ponta])."""
    x1, y1 = p1
    x2, y2 = p2
    ang = math.atan2(y2 - y1, x2 - x1)
    comp = math.hypot(x2 - x1, y2 - y1)
    tam = min(max(14, largura * 4.5), max(comp, 1) * 0.9)
    abertura = math.pi / 7
    esq = (x2 - tam * math.cos(ang - abertura), y2 - tam * math.sin(ang - abertura))
    dir_ = (x2 - tam * math.cos(ang + abertura), y2 - tam * math.sin(ang + abertura))
    base = ((esq[0] + dir_[0]) / 2, (esq[1] + dir_[1]) / 2)
    return base, [(x2, y2), esq, dir_]


_FONTES = {}


def fonte_pil(tam):
    tam = max(8, int(tam))
    if tam in _FONTES:
        return _FONTES[tam]
    fonte_ = None
    for nome in ("segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf",
                 "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            fonte_ = ImageFont.truetype(nome, tam)
            break
        except Exception:
            continue
    if fonte_ is None:
        try:
            fonte_ = ImageFont.load_default(size=tam)
        except TypeError:
            fonte_ = ImageFont.load_default()
    _FONTES[tam] = fonte_
    return fonte_


def compor(imagem, sel, anotacoes):
    """Recorta a seleção da imagem e desenha as anotações por cima."""
    x0, y0, x1, y1 = [int(round(v)) for v in sel]
    base = imagem.crop((x0, y0, x1, y1)).convert("RGBA")
    if not anotacoes:
        return base.convert("RGB")

    cw, ch = base.size
    area = cw * ch
    ss = 3 if area <= 2_000_000 else (2 if area <= 5_000_000 else 1)
    camada = Image.new("RGBA", (cw * ss, ch * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)

    def loc(p):
        return (p[0] - x0, p[1] - y0)

    def esc(p):
        return (p[0] * ss, p[1] * ss)

    for a in anotacoes:
        cor, larg, tipo = a["cor"], a["largura"], a["tipo"]
        w = max(1, round(larg * ss))
        r = w / 2
        pts = [loc(p) for p in a["pontos"]]

        def bolinha(p, r=r, cor=cor):
            q = esc(p)
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=cor)

        if tipo == "caneta":
            sp = [esc(p) for p in pts]
            if len(sp) >= 2:
                d.line(sp, fill=cor, width=w, joint="curve")
            bolinha(pts[0])
            bolinha(pts[-1])
        elif tipo == "linha":
            d.line([esc(pts[0]), esc(pts[-1])], fill=cor, width=w)
            bolinha(pts[0])
            bolinha(pts[-1])
        elif tipo == "seta":
            base_h, cab = geometria_seta(pts[0], pts[-1], larg)
            d.line([esc(pts[0]), esc(base_h)], fill=cor, width=w)
            bolinha(pts[0])
            d.polygon([esc(p) for p in cab], fill=cor)
        elif tipo in ("retangulo", "elipse"):
            (xa, ya), (xb, yb) = pts[0], pts[-1]
            box = [min(xa, xb) * ss - r, min(ya, yb) * ss - r,
                   max(xa, xb) * ss + r, max(ya, yb) * ss + r]
            if tipo == "retangulo":
                d.rectangle(box, outline=cor, width=w)
            else:
                d.ellipse(box, outline=cor, width=w)
        elif tipo == "texto":
            d.text(esc(pts[0]), a["texto"], fill=cor, font=fonte_pil(a["tamanho"] * ss))

    if ss > 1:
        camada = camada.resize((cw, ch), Image.LANCZOS)
    return Image.alpha_composite(base, camada).convert("RGB")


# ----------------------------------------------------------------------------
# Captura da tela, monitores e janela ativa
# ----------------------------------------------------------------------------
def capturar_tela():
    ox = oy = 0
    try:
        img = ImageGrab.grab(all_screens=True)
        if WINDOWS:
            gm = ctypes.windll.user32.GetSystemMetrics
            ox, oy = gm(76), gm(77)  # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN
    except TypeError:
        img = ImageGrab.grab()
    return img.convert("RGB"), (ox, oy)


if WINDOWS:
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def posicao_cursor():
    if not WINDOWS:
        return None
    try:
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return None


def monitor_em(x, y):
    """Retângulo (l, t, r, b) do monitor que contém o ponto (coordenadas de tela)."""
    if not WINDOWS:
        return None
    try:
        u = ctypes.windll.user32
        u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        u.MonitorFromPoint.restype = wintypes.HANDLE
        u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        h = u.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if u.GetMonitorInfoW(h, ctypes.byref(mi)):
            rc = mi.rcMonitor
            return (rc.left, rc.top, rc.right, rc.bottom)
    except Exception:
        pass
    return None


def rect_janela_ativa():
    """Retângulo (coordenadas de tela) da janela em primeiro plano (ignora a barra de tarefas)."""
    if not WINDOWS:
        return None
    try:
        u = ctypes.windll.user32
        dwm = ctypes.windll.dwmapi
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        u.GetWindow.restype = wintypes.HWND
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsIconic.argtypes = [wintypes.HWND]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                              wintypes.LPVOID, wintypes.DWORD]
        ignorar = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW",
                   "TkTopLevel", "NotifyIconOverflowWindow", "Windows.UI.Core.CoreWindow",
                   "TopLevelWindowForOverflowXamlIsland", "XamlExplorerHostIslandWindow",
                   CLASSE_BANDEJA}
        buf = ctypes.create_unicode_buffer(256)
        h = u.GetForegroundWindow()
        for _ in range(500):
            if not h:
                break
            if u.IsWindowVisible(h) and not u.IsIconic(h):
                u.GetClassNameW(h, buf, 256)
                ex = u.GetWindowLongW(h, -20)  # GWL_EXSTYLE
                oculta = ctypes.c_int(0)
                dwm.DwmGetWindowAttribute(h, 14, ctypes.byref(oculta), 4)  # DWMWA_CLOAKED
                if (buf.value not in ignorar and not (ex & 0x80) and not oculta.value
                        and u.GetWindowTextLengthW(h) > 0):
                    rc = wintypes.RECT()
                    if dwm.DwmGetWindowAttribute(h, 9, ctypes.byref(rc), ctypes.sizeof(rc)) != 0:
                        u.GetWindowRect(h, ctypes.byref(rc))
                    if rc.right - rc.left > 20 and rc.bottom - rc.top > 20:
                        return (rc.left, rc.top, rc.right, rc.bottom)
            h = u.GetWindow(h, 2)  # GW_HWNDNEXT
    except Exception:
        pass
    return None


def forcar_foco(win):
    win.update_idletasks()
    win.lift()
    win.focus_force()
    if WINDOWS:
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Gráficos da interface: retângulos arredondados e ícones suavizados (PIL)
# ----------------------------------------------------------------------------
_CACHE_IMG = {}


def _rgba(cor, alfa=255):
    cor = cor.lstrip("#")
    return tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4)) + (alfa,)


def img_retangulo(w, h, r, fundo=None, borda=None, esp=1.0):
    """Retângulo arredondado suavizado (PhotoImage) em pixels reais."""
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    r = max(0.0, min(float(r), w / 2, h / 2))
    chave = ("rr", w, h, round(r, 1), fundo, borda, round(esp, 2))
    if chave in _CACHE_IMG:
        return _CACHE_IMG[chave]
    k = 3
    im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    if fundo or borda:
        d = ImageDraw.Draw(im)
        e = max(1, int(round(esp * k))) if borda else 0
        d.rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=r * k,
                            fill=_rgba(fundo) if fundo else None,
                            outline=_rgba(borda) if borda else None, width=e)
        im = im.resize((w, h), Image.LANCZOS)
    else:
        im = im.resize((w, h))
    foto = ImageTk.PhotoImage(im)
    _CACHE_IMG[chave] = foto
    return foto


def icone_pil(nome, tam, cor):
    """Desenha um ícone de traço (grade 24×24) com suavização."""
    k = 4
    N = max(8, int(tam)) * k
    u = N / 24.0
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = _rgba(cor)
    w = (2.3 if nome == "logo" else 1.85) * u
    W = max(1, int(round(w)))
    m = w / 2

    def L(*pts, fechar=False, esp=1.0):
        q = [(x * u, y * u) for x, y in pts]
        if fechar:
            q.append(q[0])
        ww = max(1, int(round(w * esp)))
        d.line(q, fill=c, width=ww, joint="curve")
        r = ww / 2
        for x, y in q:
            d.ellipse([x - r, y - r, x + r, y + r], fill=c)

    def R(x0, y0, x1, y1, r=0):
        d.rounded_rectangle([x0 * u - m, y0 * u - m, x1 * u + m, y1 * u + m],
                            radius=r * u + m, outline=c, width=W)

    def C(cx, cy, r, cheio=False):
        if cheio:
            d.ellipse([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u], fill=c)
        else:
            d.ellipse([(cx - r) * u - m, (cy - r) * u - m, (cx + r) * u + m, (cy + r) * u + m],
                      outline=c, width=W)

    def A(cx, cy, r, a0, a1):
        d.arc([(cx - r) * u - m, (cy - r) * u - m, (cx + r) * u + m, (cy + r) * u + m],
              a0, a1, fill=c, width=W)

    if nome == "logo":
        R(2.6, 5, 21.4, 19.6, 4.2)
        C(12, 12.3, 3.6)
        C(6.7, 8.6, 1.0, True)
    elif nome == "selecao":
        L((4, 7.5), (4, 4), (7.5, 4)); L((16.5, 4), (20, 4), (20, 7.5))
        L((20, 16.5), (20, 20), (16.5, 20)); L((7.5, 20), (4, 20), (4, 16.5))
        L((10.5, 4), (13.5, 4)); L((10.5, 20), (13.5, 20))
        L((4, 10.5), (4, 13.5)); L((20, 10.5), (20, 13.5))
    elif nome == "foco":
        L((3.5, 8), (3.5, 3.5), (8, 3.5)); L((16, 3.5), (20.5, 3.5), (20.5, 8))
        L((20.5, 16), (20.5, 20.5), (16, 20.5)); L((8, 20.5), (3.5, 20.5), (3.5, 16))
        C(12, 12, 3.2)
    elif nome == "monitor":
        R(3, 4, 21, 16, 2); L((12, 16), (12, 20)); L((8, 20), (16, 20))
    elif nome == "janela":
        R(3, 4.5, 21, 19.5, 2); L((3, 9), (21, 9))
    elif nome == "mira":
        C(12, 12, 7); C(12, 12, 1.6, True)
        L((12, 2.5), (12, 6)); L((12, 18), (12, 21.5)); L((2.5, 12), (6, 12)); L((18, 12), (21.5, 12))
    elif nome == "editar":
        L((11, 4), (4, 4), (4, 20), (20, 20), (20, 13))
        L((18.5, 2.5), (21.5, 5.5), (12, 15), (8, 16), (9, 12), fechar=True)
    elif nome == "pincel":
        L((9.6, 11.6), (17.6, 3.6), (20.4, 6.4), (12.4, 14.4))
        C(7.3, 16.7, 3.0)
        L((4.4, 17.8), (2.8, 21), (7.6, 19.8))
    elif nome == "linha":
        L((5, 19), (19, 5))
    elif nome == "seta":
        L((5, 19), (19, 5)); L((10, 5), (19, 5), (19, 14))
    elif nome == "retangulo":
        R(4, 5, 20, 19, 1.5)
    elif nome == "circulo":
        C(12, 12, 8.5)
    elif nome == "texto":
        L((5, 7), (5, 4.5), (19, 4.5), (19, 7)); L((12, 4.5), (12, 19.5)); L((9, 19.5), (15, 19.5))
    elif nome == "desfazer":
        L((8.5, 14), (3.5, 9), (8.5, 4)); L((3.5, 9), (14.5, 9))
        A(14.5, 14.5, 5.5, -90, 90); L((14.5, 20), (10, 20))
    elif nome == "refazer":
        L((15.5, 14), (20.5, 9), (15.5, 4)); L((20.5, 9), (9.5, 9))
        A(9.5, 14.5, 5.5, 90, 270); L((9.5, 20), (14, 20))
    elif nome == "salvar":
        R(4, 4, 20, 20, 2.5)
        L((7.5, 4), (7.5, 8.5), (15, 8.5), (15, 4)); L((7.5, 20), (7.5, 13.5), (16.5, 13.5), (16.5, 20))
    elif nome == "copiar":
        R(9, 9, 20.5, 20.5, 2); L((9, 15), (4.5, 15), (4.5, 4.5), (15, 4.5), (15, 9))
    elif nome == "lapis":
        L((16, 3.5), (20.5, 8), (8.5, 20), (3.5, 20.5), (4, 15.5), fechar=True); L((13.5, 6), (18, 10.5))
    elif nome == "fechar":
        L((6, 6), (18, 18)); L((18, 6), (6, 18))
    elif nome == "minimizar":
        L((5, 12), (19, 12))
    elif nome == "enviar":
        L((12, 15), (12, 3.5)); L((7, 8.5), (12, 3.5), (17, 8.5)); L((3.5, 15), (3.5, 20.5), (20.5, 20.5), (20.5, 15))
    elif nome == "download":
        L((12, 3.5), (12, 15)); L((7, 10), (12, 15), (17, 10)); L((3.5, 15), (3.5, 20.5), (20.5, 20.5), (20.5, 15))
    elif nome == "engrenagem":
        C(12, 12, 3); C(12, 12, 6.6)
        for i in range(8):
            a = i * math.pi / 4
            L((12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
              (12 + 9.3 * math.cos(a), 12 + 9.3 * math.sin(a)), esp=1.7)
    elif nome == "paleta":
        C(12, 12, 9); C(7.8, 10.4, 1.3, True); C(11, 7.0, 1.3, True)
        C(15.6, 8.6, 1.3, True); C(14.6, 15.8, 2.1)
    elif nome == "camadas":
        L((12, 3), (21, 8), (12, 13), (3, 8), fechar=True)
        L((3, 12.5), (12, 17.5), (21, 12.5)); L((3, 16.5), (12, 21.5), (21, 16.5))
    elif nome == "chevron_baixo":
        L((6, 9), (12, 15), (18, 9))
    elif nome == "chevron_dir":
        L((9, 6), (15, 12), (9, 18))
    elif nome == "check":
        L((5, 12.5), (10, 17.5), (19, 7))
    elif nome == "pasta":
        L((3.5, 6), (3.5, 19), (20.5, 19), (20.5, 8.5), (11.5, 8.5), (9.5, 5.5), (3.5, 5.5), fechar=True)
    return im.resize((N // k, N // k), Image.LANCZOS)


def img_icone(nome, tam, cor):
    tam = max(8, int(round(tam)))
    chave = ("ic", nome, tam, cor)
    if chave not in _CACHE_IMG:
        _CACHE_IMG[chave] = ImageTk.PhotoImage(icone_pil(nome, tam, cor))
    return _CACHE_IMG[chave]


class Superficie:
    """Desenha controles num Canvas e cuida de clique e hover (sem widgets do Tk)."""

    def __init__(self, canvas):
        self.c = canvas
        self.alvos = []
        self.hover = None
        self.pressionado = None

    # --- áreas clicáveis -------------------------------------------------------
    def alvo(self, r, acao, bg=None, imgs=None, ok=True, grupo=""):
        a = {"r": r, "acao": acao, "bg": bg, "imgs": imgs, "ok": ok, "grupo": grupo}
        self.alvos.append(a)
        return a

    def limpar(self, grupo):
        self.c.delete(grupo)
        self.alvos = [a for a in self.alvos if a["grupo"] != grupo]
        if self.hover is not None and self.hover["grupo"] == grupo:
            self.hover = None
        if self.pressionado is not None and self.pressionado["grupo"] == grupo:
            self.pressionado = None

    def em(self, x, y):
        for a in reversed(self.alvos):
            x0, y0, x1, y1 = a["r"]
            if x0 <= x < x1 and y0 <= y < y1:
                return a
        return None

    def mover(self, x, y):
        a = self.em(x, y)
        novo = a if (a is not None and a["ok"] and a["acao"]) else None
        if novo is not self.hover:
            self._pintar(self.hover, False)
            self.hover = novo
            self._pintar(novo, True)
        return a

    def _pintar(self, a, ligado):
        if a and a["bg"] and a["imgs"]:
            try:
                self.c.itemconfigure(a["bg"], image=a["imgs"][1 if ligado else 0])
            except tk.TclError:
                pass

    def pressionar(self, x, y):
        self.pressionado = self.em(x, y)
        return self.pressionado

    def soltar(self, x, y):
        a, self.pressionado = self.pressionado, None
        if a is not None and a["ok"] and a["acao"] and a is self.em(x, y):
            a["acao"]()
        return a is not None

    # --- primitivas --------------------------------------------------------------
    def fundo(self, x, y, w, h, r, fundo, borda, grupo, esp=1.0):
        return self.c.create_image(int(x), int(y), anchor="nw",
                                   image=img_retangulo(w, h, r, fundo, borda, esp), tags=(grupo,))

    def botao(self, x, y, w, h, acao, grupo, r=8, fundo=None, hover=None, borda=None,
              borda_hover=None, esp=1.0, ok=True):
        x, y, w, h = int(x), int(y), int(w), int(h)
        i0 = img_retangulo(w, h, r, fundo, borda, esp)
        i1 = img_retangulo(w, h, r, hover if hover is not None else fundo,
                           borda_hover or borda, esp)
        bid = self.c.create_image(x, y, anchor="nw", image=i0, tags=(grupo,))
        self.alvo((x, y, x + w, y + h), acao, bg=bid, imgs=(i0, i1), ok=ok, grupo=grupo)
        return (x, y, x + w, y + h)

    def ic(self, x, y, nome, tam, cor, grupo, anchor="center"):
        return self.c.create_image(int(x), int(y), anchor=anchor,
                                   image=img_icone(nome, tam, cor), tags=(grupo,))

    def tx(self, x, y, texto, tam, cor, grupo, peso="normal", anchor="center", largura=None):
        kw = {"width": int(largura), "justify": "center" if anchor in ("n", "center", "s") else "left"} \
            if largura else {}
        return self.c.create_text(int(x), int(y), text=texto, fill=cor, font=fonte(tam, peso),
                                  anchor=anchor, tags=(grupo,), **kw)

    def botao_rotulo(self, x, y, w, h, texto, icone, acao, grupo, estilo="primario", tam=14):
        if estilo == "primario":
            fundo, hover, borda, cor = T["azul"], T["azul_hover"], None, "#ffffff"
        else:
            fundo, hover, borda, cor = T["card"], T["btn"], T["borda_btn"], T["texto"]
        self.botao(x, y, w, h, acao, grupo, r=px(9), fundo=fundo, hover=hover, borda=borda,
                   esp=max(1.0, 1.3 * UI["esc"]))
        cx, cy = x + w / 2, y + h / 2
        t = self.tx(cx + (px(12) if icone else 0), cy, texto, tam, cor, grupo, peso="bold")
        if icone:
            b = self.c.bbox(t)
            self.ic(b[0] - px(13), cy, icone, px(19), cor, grupo)

    def segmentos(self, x, y, w, h, opcoes, grupo):
        """opcoes: lista de (rótulo ou função desenhar(cx, cy, cor), ativo, ação)."""
        self.fundo(x, y, w, h, px(8), T["btn"], None, grupo)
        p = px(3)
        ow = (w - 2 * p) / len(opcoes)
        for i, (rotulo, ativo, acao) in enumerate(opcoes):
            bx = int(x + p + i * ow)
            self.botao(bx, y + p, int(ow), h - 2 * p, acao, grupo, r=px(6),
                       fundo=T["azul"] if ativo else None,
                       hover=T["azul_hover"] if ativo else T["btn_hover"])
            cor = "#ffffff" if ativo else T["texto2"]
            cx, cy = bx + int(ow) // 2, y + h // 2
            if callable(rotulo):
                rotulo(cx, cy, cor)
            else:
                self.tx(cx, cy, rotulo, 12, cor, grupo, peso="bold")

    def interruptor(self, x, y, ligado, grupo):
        w, h = px(40), px(22)
        self.fundo(x, y, w, h, h / 2, T["azul"] if ligado else "#3a3d45", None, grupo)
        k = h - px(6)
        kx = x + w - px(3) - k if ligado else x + px(3)
        self.fundo(kx, y + px(3), k, k, k / 2, "#ffffff", None, grupo)


# ----------------------------------------------------------------------------
# Tela de seleção + edição com painel lateral (estilo PrintaAí)
# ----------------------------------------------------------------------------
class Overlay(tk.Toplevel):
    PW = 268  # largura do painel (unidades lógicas)
    CONTEUDO = {"captura": 143, "ferramentas": 118, "aparencia": 70, "acoes": 118}

    def __init__(self, master, imagem, origem, ao_concluir, janela_ativa=None, inicial=None):
        super().__init__(master)
        self.withdraw()
        self.imagem = imagem
        self.ox, self.oy = origem
        self.w, self.h = imagem.size
        self.ao_concluir = ao_concluir
        self.janela_ativa = janela_ativa
        self.s = UI["esc"]

        self.sel = None          # (x0, y0, x1, y1) em coordenadas da imagem
        self.editando = False    # True depois que a seleção foi concluída
        self.modo = None         # nova | nova_pendente | redim | desenho | ui
        self.inicio = (0, 0)
        self.alca = None
        nomes = [f[0] for f in FERRAMENTAS]
        self.ferramenta = CONFIG.get("ferramenta") if CONFIG.get("ferramenta") in nomes else "caneta"
        self.cor = CONFIG.get("cor") or CORES[0]
        self.largura = CONFIG.get("largura") if CONFIG.get("largura") in (2, 4, 8) else 4
        self.recolhidos = set(CONFIG.get("recolhidos") or []) & set(SECOES)
        self.auto_rec = set()
        self.auto_calculado = False
        self.minimizado = False
        self.anotacoes = []
        self.refeitos = []
        self.anot_visiveis = True
        self.atual = None
        self.modo_captura = "area"
        self.painel_visivel = False
        self.painel_rect = None
        self.mon_painel = (0, 0, self.w, self.h)
        self.ancoras = {}
        self.popup = None
        self.popup_widgets = []
        self.campos = []
        self._popup_fechado = None
        self.enviando = False
        self._aviso_id = None
        self.entry = self.entry_id = self.entry_info = None
        self.fechado = False
        self.ultimo_mouse = (-1, -1)

        self.overrideredirect(True)
        self.geometry(f"{self.w}x{self.h}+{self.ox}+{self.oy}")
        self.attributes("-topmost", True)
        self.configure(bg="black")

        self.tk_escura = ImageTk.PhotoImage(ImageEnhance.Brightness(imagem).enhance(0.45))
        self.tk_recorte = None
        c = self.canvas = tk.Canvas(self, width=self.w, height=self.h, bg="black",
                                    highlightthickness=0, bd=0, cursor="crosshair")
        c.pack()
        c.create_image(0, 0, anchor="nw", image=self.tk_escura, tags="fundo")
        self.ui = Superficie(c)
        pos = posicao_cursor()
        self.mon_cursor = (self.monitor_img(pos[0] - self.ox, pos[1] - self.oy) if pos
                           else (0, 0, self.w, self.h))
        self.mostrar_dica(DICA_INICIAL)

        c.bind("<ButtonPress-1>", self.pressionou)
        c.bind("<B1-Motion>", self.arrastou)
        c.bind("<ButtonRelease-1>", self.soltou)
        c.bind("<Motion>", self.movimento)
        c.bind("<ButtonPress-3>", lambda e: self.cancelar())
        self.bind("<Escape>", lambda e: self.tecla_esc())
        for seq in ("<Control-c>", "<Control-C>", "<Return>"):
            self.bind(seq, lambda e: self.tecla_copiar())
        for seq in ("<Control-s>", "<Control-S>"):
            self.bind(seq, lambda e: self.salvar_como())
        for seq in ("<Control-d>", "<Control-D>"):
            self.bind(seq, lambda e: None if self.digitando() else self.enviar_link())
        for seq in ("<Control-z>", "<Control-Z>"):
            self.bind(seq, self.tecla_z)
        for seq in ("<Control-y>", "<Control-Y>"):
            self.bind(seq, lambda e: self.tecla_refazer())
        for k in "fF":
            self.bind(f"<KeyPress-{k}>", lambda e: self.tecla_modo("tela"))
        for k in "jJ":
            self.bind(f"<KeyPress-{k}>", lambda e: self.tecla_modo("janela"))

        self.update_idletasks()
        self.deiconify()
        forcar_foco(self)
        self.canvas.focus_set()
        if inicial == "tela":
            self.after(20, self.captura_tela_inteira)
        elif inicial == "janela":
            self.after(20, self.captura_janela)

    # --- utilidades -------------------------------------------------------
    def limitar(self, x, y):
        return min(max(x, 0), self.w), min(max(y, 0), self.h)

    def limitar_sel(self, x, y):
        x0, y0, x1, y1 = self.sel
        return min(max(x, x0), x1), min(max(y, y0), y1)

    def dentro(self, x, y):
        if not self.sel:
            return False
        x0, y0, x1, y1 = self.sel
        return x0 <= x <= x1 and y0 <= y <= y1

    def monitor_img(self, x, y):
        """Monitor que contém o ponto (coordenadas da imagem)."""
        m = monitor_em(x + self.ox, y + self.oy)
        if not m:
            return (0, 0, self.w, self.h)
        l, t, r, b = m[0] - self.ox, m[1] - self.oy, m[2] - self.ox, m[3] - self.oy
        return (max(0, l), max(0, t), min(self.w, r), min(self.h, b))

    def alcas(self):
        x0, y0, x1, y1 = self.sel
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        return {"nw": (x0, y0), "n": (mx, y0), "ne": (x1, y0), "e": (x1, my),
                "se": (x1, y1), "s": (mx, y1), "sw": (x0, y1), "w": (x0, my)}

    def alca_em(self, x, y):
        if not self.sel:
            return None
        tol = px(8)
        for nome, (hx, hy) in self.alcas().items():
            if abs(x - hx) <= tol and abs(y - hy) <= tol:
                return nome
        return None

    def digitando(self):
        try:
            return isinstance(self.focus_get(), tk.Entry)
        except Exception:
            return False

    def dialogo(self, funcao, **kw):
        """Abre um diálogo do sistema por cima da tela de captura."""
        self.attributes("-topmost", False)
        try:
            return funcao(parent=self, **kw)
        finally:
            if not self.fechado:
                self.attributes("-topmost", True)
                forcar_foco(self)
                self.canvas.focus_set()

    # --- dica / rótulo ------------------------------------------------------
    def mostrar_dica(self, texto):
        c = self.canvas
        c.delete("dica")
        if not texto:
            return
        l, t, r, b = self.mon_cursor
        tid = c.create_text((l + r) // 2, t + px(36), text=texto, fill=T["texto"],
                            font=fonte(12, "bold"), tags="dica")
        x0, y0, x1, y1 = c.bbox(tid)
        ph, pv = px(16), px(8)
        bg = self.ui.fundo(x0 - ph, y0 - pv, x1 - x0 + 2 * ph, y1 - y0 + 2 * pv, px(10),
                           T["painel"], T["painel_borda"], "dica", esp=max(1.0, self.s))
        c.tag_lower(bg, tid)
        self.reordenar()

    def aviso(self, texto, ms=2400):
        self.mostrar_dica(texto)
        if self._aviso_id:
            self.after_cancel(self._aviso_id)
        self._aviso_id = self.after(ms, self._fim_aviso)

    def _fim_aviso(self):
        self._aviso_id = None
        if not self.fechado:
            self.mostrar_dica(DICA_EDICAO if self.editando else DICA_INICIAL)

    def rotulo_tamanho(self):
        c = self.canvas
        x0, y0, x1, y1 = self.sel
        txt = f"{int(x1 - x0)} × {int(y1 - y0)} px"
        if y0 > px(36):
            ax, ay, anc = x0, y0 - px(12), "sw"
        else:
            ax, ay, anc = x0 + px(10), y0 + px(10), "nw"
        tid = c.create_text(ax + px(9), ay - (px(5) if anc == "sw" else -px(5)), text=txt,
                            anchor=anc, fill="#ffffff", font=fonte(12, "bold"), tags="rotulo")
        b = c.bbox(tid)
        bg = self.ui.fundo(b[0] - px(9), b[1] - px(5), b[2] - b[0] + px(18), b[3] - b[1] + px(10),
                           px(7), "#16171b", None, "rotulo")
        c.tag_lower(bg, tid)

    def reordenar(self):
        for tag in ("ann", "borda", "alca", "rotulo", "dica", "painel", "popup"):
            self.canvas.tag_raise(tag)

    # --- seleção ----------------------------------------------------------
    def atualizar_selecao(self):
        c = self.canvas
        x0, y0, x1, y1 = self.sel
        c.delete("brilho", "borda", "alca", "rotulo")
        if x1 - x0 >= 1 and y1 - y0 >= 1:
            self.tk_recorte = ImageTk.PhotoImage(self.imagem.crop((x0, y0, x1, y1)))
            c.create_image(x0, y0, anchor="nw", image=self.tk_recorte, tags="brilho")
            c.tag_raise("brilho", "fundo")
        c.create_rectangle(x0, y0, x1, y1, outline=T["selecao"], width=max(2, px(2)), tags="borda")
        if self.editando:
            t = px(5)
            for hx, hy in self.alcas().values():
                c.create_rectangle(hx - t, hy - t, hx + t, hy + t, fill="white",
                                   outline=T["selecao"], width=max(1, px(1.5)), tags="alca")
        self.rotulo_tamanho()
        self.reordenar()

    def definir_selecao(self, x0, y0, x1, y1, modo):
        x0, y0 = self.limitar(int(x0), int(y0))
        x1, y1 = self.limitar(int(x1), int(y1))
        if x1 - x0 < 6 or y1 - y0 < 6:
            return False
        self.fechar_popup()
        self.confirmar_texto()
        self.sel = (x0, y0, x1, y1)
        self.modo_captura = modo
        primeira = not self.editando
        self.editando = True
        self.atualizar_selecao()
        if primeira:
            self.mostrar_dica(DICA_EDICAO)
        self.mostrar_painel(reposicionar=True)
        return True

    def limpar_tudo(self):
        self.cancelar_texto()
        self.fechar_popup()
        self.atual = None
        for a in self.anotacoes:
            for i in a["ids"]:
                self.canvas.delete(i)
        self.anotacoes = []
        self.refeitos = []
        self.anot_visiveis = True
        self.canvas.delete("brilho", "borda", "alca", "rotulo", "ann")
        self.ocultar_painel()
        self.sel = None
        self.editando = False
        self.modo_captura = "area"
        self.mostrar_dica(DICA_INICIAL)

    def redimensionar(self, mx, my):
        x0, y0, x1, y1 = self.sel
        h = self.alca
        mx, my = self.limitar(mx, my)
        if "w" in h:
            x0 = mx
        if "e" in h:
            x1 = mx
        if "n" in h:
            y0 = my
        if "s" in h:
            y1 = my
        if x0 > x1:
            x0, x1 = x1, x0
            h = h.replace("w", "%").replace("e", "w").replace("%", "e")
        if y0 > y1:
            y0, y1 = y1, y0
            h = h.replace("n", "%").replace("s", "n").replace("%", "s")
        self.alca = h
        self.sel = (x0, y0, x1, y1)
        self.atualizar_selecao()

    # --- modos de captura ------------------------------------------------------
    def captura_area(self):
        if self.modo_captura != "area":
            self.limpar_tudo()

    def captura_tela_inteira(self):
        if self.sel:
            cx, cy = (self.sel[0] + self.sel[2]) / 2, (self.sel[1] + self.sel[3]) / 2
        else:
            l, t, r, b = self.mon_cursor
            cx, cy = (l + r) / 2, (t + b) / 2
        self.definir_selecao(*self.monitor_img(cx, cy), "tela")

    def captura_janela(self):
        if not self.janela_ativa:
            self.aviso("Nenhuma janela ativa encontrada.")
            return
        l, t, r, b = self.janela_ativa
        if not self.definir_selecao(l - self.ox, t - self.oy, r - self.ox, b - self.oy, "janela"):
            self.aviso("A janela ativa está fora da tela.")

    def aplicar_personalizada(self):
        try:
            larg, alt, x, y = [int(float(e.get().strip().replace(",", "."))) for e in self.campos]
        except (ValueError, tk.TclError):
            for e in self.campos:
                e.config(highlightbackground=T["vermelho"])
            return
        x0, y0 = x - self.ox, y - self.oy
        if not self.definir_selecao(x0, y0, x0 + larg, y0 + alt, "personalizada"):
            for e in self.campos:
                e.config(highlightbackground=T["vermelho"])

    # --- mouse ------------------------------------------------------------
    def movimento(self, e):
        self.ultimo_mouse = (e.x, e.y)
        if self.modo and self.modo != "ui":
            return
        a = self.ui.mover(e.x, e.y)
        if a is not None:
            cur = "hand2" if (a["acao"] and a["ok"]) else "arrow"
        else:
            cur = "crosshair"
            if self.editando:
                h = self.alca_em(e.x, e.y)
                if h:
                    cur = CURSORES[h]
                elif self.dentro(e.x, e.y) and self.ferramenta == "texto":
                    cur = "xterm"
        try:
            self.canvas.config(cursor=cur)
        except tk.TclError:
            self.canvas.config(cursor="crosshair")

    def pressionou(self, e):
        self.confirmar_texto()
        if self.ui.pressionar(e.x, e.y) is not None:
            self.modo = "ui"
            return
        self.fechar_popup()
        if self.editando:
            h = self.alca_em(e.x, e.y)
            if h:
                self.modo, self.alca = "redim", h
                self.ocultar_painel()
                return
            if self.dentro(e.x, e.y):
                self.modo = "desenho"
                self.iniciar_desenho(*self.limitar_sel(e.x, e.y))
                return
            self.modo = "nova_pendente"
            self.inicio = (e.x, e.y)
            return
        self.modo = "nova"
        self.inicio = self.limitar(e.x, e.y)

    def arrastou(self, e):
        if self.modo == "ui":
            return
        if self.modo == "nova_pendente":
            if abs(e.x - self.inicio[0]) + abs(e.y - self.inicio[1]) < 4:
                return
            self.limpar_tudo()
            self.modo = "nova"
            self.inicio = self.limitar(*self.inicio)
        if self.modo == "nova":
            x0, y0 = self.inicio
            x, y = self.limitar(e.x, e.y)
            self.sel = (min(x0, x), min(y0, y), max(x0, x), max(y0, y))
            self.canvas.delete("dica")
            self.atualizar_selecao()
        elif self.modo == "redim":
            self.redimensionar(e.x, e.y)
        elif self.modo == "desenho":
            self.continuar_desenho(*self.limitar_sel(e.x, e.y))

    def soltou(self, e):
        modo, self.modo = self.modo, None
        if modo == "ui":
            a = self.ui.pressionado
            if self.popup and a is not None and a["grupo"] != "popup":
                self._popup_fechado = self.popup
                self.fechar_popup()
            self.ui.soltar(e.x, e.y)
            self._popup_fechado = None
            if not self.fechado:
                self.movimento(e)
            return
        if modo == "nova":
            if not self.sel or (self.sel[2] - self.sel[0] < 6) or (self.sel[3] - self.sel[1] < 6):
                self.limpar_tudo()
                return
            self.editando = True
            self.modo_captura = "area"
            self.atualizar_selecao()
            self.mostrar_dica(DICA_EDICAO)
            self.mostrar_painel(reposicionar=True)
        elif modo == "redim":
            self.modo_captura = "area"
            self.mostrar_painel(reposicionar=True)
        elif modo == "desenho":
            self.finalizar_desenho()

    # --- desenho das anotações ---------------------------------------------
    def iniciar_desenho(self, x, y):
        if not self.anot_visiveis:
            self.alternar_anotacoes()
        if self.ferramenta == "texto":
            self.modo = None
            self.iniciar_texto(x, y)
            return
        self.atual = {"tipo": self.ferramenta, "pontos": [(x, y)], "cor": self.cor,
                      "largura": self.largura, "ids": []}
        if self.ferramenta == "caneta":
            self.desenhar(self.atual)

    def continuar_desenho(self, x, y):
        a = self.atual
        if not a:
            return
        if a["tipo"] == "caneta":
            a["pontos"].append((x, y))
        else:
            a["pontos"] = [a["pontos"][0], (x, y)]
        self.desenhar(a)

    def finalizar_desenho(self):
        a, self.atual = self.atual, None
        if not a:
            return
        if a["tipo"] != "caneta":
            p1, p2 = a["pontos"][0], a["pontos"][-1]
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 3:
                for i in a["ids"]:
                    self.canvas.delete(i)
                return
        self.anotacoes.append(a)
        self.refeitos = []
        self.atualizar_painel()

    def desenhar(self, a):
        c = self.canvas
        for i in a["ids"]:
            c.delete(i)
        w, cor, pts, tipo = a["largura"], a["cor"], a["pontos"], a["tipo"]
        ids = []
        if tipo == "caneta":
            if len(pts) < 2:
                x, y = pts[0]
                r = w / 2
                ids.append(c.create_oval(x - r, y - r, x + r, y + r,
                                         fill=cor, outline=cor, tags="ann"))
            else:
                flat = [v for p in pts for v in p]
                ids.append(c.create_line(*flat, fill=cor, width=w, capstyle="round",
                                         joinstyle="round", tags="ann"))
        elif tipo == "linha":
            (x1, y1), (x2, y2) = pts[0], pts[-1]
            ids.append(c.create_line(x1, y1, x2, y2, fill=cor, width=w,
                                     capstyle="round", tags="ann"))
        elif tipo == "seta":
            p1, p2 = pts[0], pts[-1]
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 2:
                base, cab = geometria_seta(p1, p2, w)
                ids.append(c.create_line(p1[0], p1[1], base[0], base[1], fill=cor,
                                         width=w, capstyle="round", tags="ann"))
                ids.append(c.create_polygon(*[v for p in cab for v in p],
                                            fill=cor, outline=cor, tags="ann"))
        elif tipo in ("retangulo", "elipse"):
            (xa, ya), (xb, yb) = pts[0], pts[-1]
            criar = c.create_rectangle if tipo == "retangulo" else c.create_oval
            ids.append(criar(xa, ya, xb, yb, outline=cor, width=w, tags="ann"))
        elif tipo == "texto":
            ids.append(c.create_text(pts[0][0], pts[0][1], text=a["texto"], anchor="nw",
                                     fill=cor, font=(FONTE_UI, -a["tamanho"], "bold"),
                                     tags="ann"))
        a["ids"] = ids
        self.reordenar()

    def desfazer(self):
        if self.entry:
            self.cancelar_texto()
            return
        if self.anotacoes:
            a = self.anotacoes.pop()
            for i in a["ids"]:
                self.canvas.delete(i)
            a["ids"] = []
            self.refeitos.append(a)
            self.atualizar_painel()

    def refazer(self):
        if not self.refeitos:
            return
        self.cancelar_texto()
        a = self.refeitos.pop()
        self.desenhar(a)
        self.anotacoes.append(a)
        if not self.anot_visiveis:
            self.alternar_anotacoes()
        else:
            self.atualizar_painel()

    def alternar_anotacoes(self):
        self.anot_visiveis = not self.anot_visiveis
        self.canvas.itemconfigure("ann", state="normal" if self.anot_visiveis else "hidden")
        self.atualizar_painel()

    # --- texto --------------------------------------------------------------
    def iniciar_texto(self, x, y):
        self.confirmar_texto()
        tam = 10 + 3 * self.largura
        cor = self.cor
        r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))
        fundo = "#202124" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"
        ent = tk.Entry(self.canvas, font=(FONTE_UI, -tam, "bold"), fg=cor, bg=fundo,
                       insertbackground=cor, relief="flat", bd=0, width=12,
                       highlightthickness=1, highlightbackground=T["selecao"],
                       highlightcolor=T["selecao"])
        ent.bind("<Return>", lambda e: (self.confirmar_texto(), "break")[1])
        ent.bind("<Escape>", lambda e: (self.cancelar_texto(), "break")[1])
        ent.bind("<KeyRelease>", lambda e: ent.config(width=max(12, len(ent.get()) + 2)))
        self.entry = ent
        self.entry_info = {"x": x, "y": y, "cor": cor, "tamanho": tam, "largura": self.largura}
        self.entry_id = self.canvas.create_window(x, y, window=ent, anchor="nw")
        ent.focus_set()
        self.atualizar_painel()

    def confirmar_texto(self):
        if not self.entry:
            return
        txt = self.entry.get()
        info = self.entry_info
        self.cancelar_texto()
        if txt.strip():
            a = {"tipo": "texto", "pontos": [(info["x"] + 2, info["y"] + 2)],
                 "cor": info["cor"], "largura": info["largura"],
                 "tamanho": info["tamanho"], "texto": txt, "ids": []}
            self.desenhar(a)
            self.anotacoes.append(a)
            self.refeitos = []
            self.atualizar_painel()

    def cancelar_texto(self):
        if not self.entry:
            return
        try:
            self.canvas.delete(self.entry_id)
            self.entry.destroy()
        except tk.TclError:
            pass
        self.entry = self.entry_id = self.entry_info = None
        if not self.fechado:
            self.canvas.focus_set()

    # --- painel lateral -----------------------------------------------------------
    def _altura_card(self, chave, fechada):
        return 8 * 2 + 28 + (0 if fechada else 6 + self.CONTEUDO[chave])

    def _altura_painel(self, rec):
        h = 12 + 32 + 10
        if not self.minimizado:
            h += sum(self._altura_card(k, k in rec) + 8 for k in SECOES)
        h += 2 + 40
        if not self.minimizado:
            h += 8 + 38 + 8 + 38 + 8 + 32
        return h + 12

    def mostrar_painel(self, reposicionar=False):
        if not self.editando:
            return
        x0, y0, x1, y1 = self.sel
        if reposicionar or not self.painel_visivel:
            self.mon_painel = self.monitor_img((x0 + x1) / 2, (y0 + y1) / 2)
        if not self.auto_calculado:
            # Em telas baixas, recolhe seções até o painel caber
            self.auto_calculado = True
            l, t, r, b = self.mon_painel
            disponivel = (b - t) - px(24)
            for k in ("captura", "aparencia", "acoes", "ferramentas"):
                if px(self._altura_painel(self.recolhidos | self.auto_rec)) <= disponivel:
                    break
                if k not in self.recolhidos:
                    self.auto_rec.add(k)
        self.painel_visivel = True
        self.desenhar_painel()
        self.reordenar()
        self.ui.mover(*self.ultimo_mouse)

    def ocultar_painel(self):
        self.fechar_popup()
        self.ui.limpar("painel")
        self.painel_visivel = False

    def atualizar_painel(self):
        if self.painel_visivel and not self.fechado:
            self.desenhar_painel()
            self.reordenar()
            self.ui.mover(*self.ultimo_mouse)

    def desenhar_painel(self):
        ui, c, G = self.ui, self.canvas, "painel"
        ui.limpar(G)
        self.ancoras = {}
        rec = self.recolhidos | self.auto_rec
        PAD, CP = 12, 8
        IW = self.PW - 2 * PAD
        CW = IW - 2 * CP
        Wp, Hp = px(self.PW), px(self._altura_painel(rec))

        x0, y0, x1, y1 = self.sel
        l, t, r, b = self.mon_painel
        m = px(12)
        if x1 + m + Wp <= r:
            bx = x1 + m
        elif x0 - m - Wp >= l:
            bx = x0 - m - Wp
        else:
            bx = max(l, r - Wp - m)
        by = max(t, min(max(y0, t + m), b - Hp - m))
        self.painel_rect = (bx, by, bx + Wp, by + Hp)

        def X(v):
            return bx + px(v)

        def Y(v):
            return by + px(v)

        ui.fundo(bx, by, Wp, Hp, px(16), T["painel"], T["painel_borda"], G, esp=max(1.0, self.s))
        ui.alvo(self.painel_rect, None, grupo=G)

        # Cabeçalho: logo + nome + minimizar/fechar
        y = PAD
        ui.ic(X(PAD), Y(y + 16), "logo", px(32), T["azul"], G, anchor="w")
        t1 = ui.tx(X(PAD + 42), Y(y + 16), "Printa", 20, T["texto"], G, peso="bold", anchor="w")
        ui.tx(c.bbox(t1)[2] - 1, Y(y + 16), "Aí", 20, T["azul"], G, peso="bold", anchor="w")
        for i, (nome, acao) in enumerate((
                ("chevron_baixo" if self.minimizado else "minimizar", self.alternar_minimizado),
                ("fechar", self.cancelar))):
            bxx = self.PW - PAD - 28 - (1 - i) * 30
            ui.botao(X(bxx), Y(y + 2), px(28), px(28), acao, G, r=px(7), fundo=None,
                     hover=T["btn_hover"])
            ui.ic(X(bxx + 14), Y(y + 16), nome, px(17), T["azul"], G)
        y += 32 + 10

        if not self.minimizado:
            secoes = (("captura", "Captura", "foco", self._sec_captura),
                      ("ferramentas", "Ferramentas", "editar", self._sec_ferramentas),
                      ("aparencia", "Aparência", "paleta", self._sec_aparencia),
                      ("acoes", "Ações", "camadas", self._sec_acoes))
            for chave, titulo, icone, fn in secoes:
                fechada = chave in rec
                ch = self._altura_card(chave, fechada)
                ui.fundo(X(PAD), Y(y), px(IW), px(ch), px(12), T["card"], T["card_borda"], G,
                         esp=max(1.0, self.s))
                ui.botao(X(PAD + 3), Y(y + 3), px(IW - 6), px(CP + 28 - 2),
                         lambda k=chave: self.alternar_secao(k), G, r=px(9), fundo=None,
                         hover=T["card_hover"])
                ui.ic(X(PAD + CP + 10), Y(y + CP + 14), icone, px(20), T["azul"], G)
                ui.tx(X(PAD + CP + 28), Y(y + CP + 14), titulo, 15, T["texto"], G,
                      peso="bold", anchor="w")
                ui.ic(X(PAD + IW - CP - 10), Y(y + CP + 14),
                      "chevron_dir" if fechada else "chevron_baixo", px(16), T["azul"], G)
                if not fechada:
                    fn(X(PAD + CP), Y(y + CP + 34), px(CW))
                y += ch + 8

        y += 2
        ui.botao_rotulo(X(PAD), Y(y), px(IW), px(40), "Copiar e fechar", "copiar",
                        self.copiar_e_fechar, G)
        y += 40
        if not self.minimizado:
            y += 8
            ui.botao_rotulo(X(PAD), Y(y), px(IW), px(38), "Salvar como…", "download",
                            self.salvar_como, G, estilo="secundario")
            y += 38 + 8
            ui.botao_rotulo(X(PAD), Y(y), px(IW), px(38),
                            "Enviando…" if self.enviando else "Enviar e copiar link", "enviar",
                            self.enviar_link, G, estilo="secundario")
            y += 38 + 8
            self.ancoras["config"] = ui.botao(X(PAD), Y(y), px(IW), px(32),
                                              lambda: self.alternar_popup("config"), G,
                                              r=px(8), fundo=None, hover=T["btn"])
            ui.ic(X(PAD + 16), Y(y + 16), "engrenagem", px(19), T["texto2"], G)
            ui.tx(X(PAD + 34), Y(y + 16), "Configurações", 13, T["texto2"], G, anchor="w")

    def _sec_captura(self, ox, oy, cw):
        ui, G = self.ui, "painel"
        itens = (("area", "Selecionar área", "selecao", self.captura_area),
                 ("tela", "Tela inteira", "monitor", self.captura_tela_inteira),
                 ("janela", "Janela ativa", "janela", self.captura_janela),
                 ("personalizada", "Área personalizada", "mira",
                  lambda: self.alternar_popup("personalizada")))
        for i, (chave, rotulo, icone, acao) in enumerate(itens):
            y = oy + px(i * 37)
            ativo = chave == self.modo_captura
            self.ancoras[chave] = ui.botao(
                ox, y, cw, px(32), acao, G, r=px(8),
                fundo=T["azul"] if ativo else T["btn"],
                hover=T["azul_hover"] if ativo else T["btn_hover"])
            cor = "#ffffff" if ativo else T["texto"]
            ui.ic(ox + px(18), y + px(16), icone, px(19), cor, G)
            ui.tx(ox + px(37), y + px(16), rotulo, 13, cor, G, anchor="w")

    def _ladrilhos(self, ox, oy, cw, itens):
        ui, G = self.ui, "painel"
        gap, th = px(6), px(56)
        tw = (cw - 2 * gap) / 3
        for i, (rotulo, icone, acao, ativo, ok) in enumerate(itens):
            x = int(ox + (i % 3) * (tw + gap))
            y = oy + (i // 3) * (th + gap)
            w = int(tw)
            if ativo:
                fundo, hover, borda = T["ativo_fundo"], T["ativo_hover"], T["azul"]
            else:
                fundo, hover, borda = T["btn"], T["btn_hover"], None
            ui.botao(x, y, w, th, acao, G, r=px(9), fundo=fundo, hover=hover if ok else fundo,
                     borda=borda, esp=max(1.5, 1.6 * self.s), ok=ok)
            cor = T["texto"] if ok else T["apagado"]
            ui.ic(x + w // 2, y + px(21), icone, px(21), cor, G)
            ui.tx(x + w // 2, y + px(43), rotulo, 12, cor, G)

    def _sec_ferramentas(self, ox, oy, cw):
        itens = [(rotulo, icone, (lambda n=nome: self.escolher_ferramenta(n)),
                  nome == self.ferramenta, True) for nome, rotulo, icone in FERRAMENTAS]
        self._ladrilhos(ox, oy, cw, itens)

    def _sec_aparencia(self, ox, oy, cw):
        ui, G = self.ui, "painel"
        ui.tx(ox + px(2), oy + px(15), "Cor", 13, T["texto2"], G, anchor="w")
        bw, bh = px(70), px(30)
        bx = ox + cw - bw
        self.ancoras["cores"] = ui.botao(bx, oy, bw, bh, lambda: self.alternar_popup("cores"), G,
                                         r=px(8), fundo=T["btn"], hover=T["btn_hover"])
        ui.fundo(bx + px(5), oy + px(5), px(38), px(20), px(5), self.cor, "#4a4e57", G)
        ui.ic(bx + bw - px(14), oy + px(15), "chevron_baixo", px(14), T["texto2"], G)

        y2 = oy + px(40)
        ui.tx(ox + px(2), y2 + px(15), "Espessura", 13, T["texto2"], G, anchor="w")
        sw = px(126)
        opcoes = []
        for v, esp in ((2, 2), (4, 4), (8, 7)):
            def barra(cx, cy, cor, esp=esp):
                th = max(2, px(esp))
                ui.fundo(cx - px(11), cy - th // 2, px(22), th, th / 2, cor, None, G)
            opcoes.append((barra, v == self.largura, lambda v=v: self.escolher_largura(v)))
        ui.segmentos(ox + cw - sw, y2, sw, px(30), opcoes, G)

    def _sec_acoes(self, ox, oy, cw):
        itens = [("Desfazer", "desfazer", self.desfazer, False,
                  bool(self.anotacoes) or self.entry is not None),
                 ("Refazer", "refazer", self.refazer, False, bool(self.refeitos)),
                 ("Salvar", "salvar", self.salvar_rapido, False, True),
                 ("Copiar", "copiar", self.copiar, False, True),
                 ("Anotações", "lapis", self.alternar_anotacoes, not self.anot_visiveis,
                  bool(self.anotacoes) or not self.anot_visiveis),
                 ("Fechar", "fechar", self.cancelar, False, True)]
        self._ladrilhos(ox, oy, cw, itens)

    def alternar_secao(self, chave):
        if chave in self.recolhidos or chave in self.auto_rec:
            self.recolhidos.discard(chave)
            self.auto_rec.discard(chave)
        else:
            self.recolhidos.add(chave)
        self.fechar_popup()
        self.atualizar_painel()

    def alternar_minimizado(self):
        self.minimizado = not self.minimizado
        self.fechar_popup()
        self.atualizar_painel()

    def escolher_ferramenta(self, nome):
        self.confirmar_texto()
        self.ferramenta = nome
        self.atualizar_painel()

    def escolher_largura(self, v):
        self.largura = v
        self.atualizar_painel()

    def definir_cor(self, cor):
        self.cor = cor
        self.fechar_popup()
        self.atualizar_painel()

    def cor_personalizada(self):
        self.fechar_popup()
        resultado = self.dialogo(colorchooser.askcolor, color=self.cor)
        if resultado and resultado[1]:
            self.definir_cor(resultado[1])

    # --- janelas flutuantes (cores, área personalizada, configurações) -------------
    def alternar_popup(self, nome):
        if self._popup_fechado == nome:  # o clique que fechou era o próprio botão
            return
        if self.popup == nome:
            self.fechar_popup()
        else:
            self.abrir_popup(nome)

    def abrir_popup(self, nome):
        self.fechar_popup()
        self.popup = nome
        {"cores": self._popup_cores, "personalizada": self._popup_personalizada,
         "config": self._popup_config}[nome]()
        self.reordenar()
        self.ui.mover(*self.ultimo_mouse)

    def fechar_popup(self):
        if not self.popup:
            return
        self.popup = None
        for wdg in self.popup_widgets:
            try:
                wdg.destroy()
            except tk.TclError:
                pass
        self.popup_widgets = []
        self.campos = []
        self.ui.limpar("popup")
        if not self.fechado and self.entry is None:
            self.canvas.focus_set()

    def posicao_popup(self, W, H, ancora=None):
        l, t, r, b = self.mon_painel
        m = px(8)
        px0, py0, px1, py1 = self.painel_rect
        if px0 - m - W >= l:
            x = px0 - m - W
        elif px1 + m + W <= r:
            x = px1 + m
        else:
            x = max(l, px0 + (px1 - px0 - W) // 2)
        ay = ancora[1] if ancora else py0
        y = max(t, min(max(ay, t + m), b - H - m))
        return int(x), int(y)

    def _fundo_popup(self, x, y, W, H):
        self.ui.fundo(x, y, W, H, px(14), T["painel"], T["painel_borda"], "popup",
                      esp=max(1.0, self.s))
        self.ui.alvo((x, y, x + W, y + H), None, grupo="popup")

    def _popup_cores(self):
        ui, G = self.ui, "popup"
        ax0, ay0, ax1, ay1 = self.ancoras.get("cores", self.painel_rect)
        P, sz, gap = px(10), px(26), px(6)
        W = 2 * P + 4 * sz + 3 * gap
        H = 2 * P + 2 * sz + gap + px(8) + px(28)
        x, y = ax1 - W, ay1 + px(6)
        if y + H > self.mon_painel[3]:
            y = ay0 - px(6) - H
        self._fundo_popup(x, y, W, H)
        for i, cor in enumerate(CORES):
            cx = x + P + (i % 4) * (sz + gap)
            cy = y + P + (i // 4) * (sz + gap)
            escolhida = cor.lower() == self.cor.lower()
            ui.botao(cx, cy, sz, sz, lambda c_=cor: self.definir_cor(c_), G, r=px(6),
                     fundo=cor, hover=cor, borda="#ffffff" if escolhida else "#4a4e57",
                     borda_hover="#ffffff", esp=max(1.0, (2.2 if escolhida else 1.2) * self.s))
        yb = y + P + 2 * sz + gap + px(8)
        ui.botao(x + P, yb, W - 2 * P, px(28), self.cor_personalizada, G, r=px(7),
                 fundo=T["btn"], hover=T["btn_hover"])
        ui.tx(x + W // 2, yb + px(14), "Mais cores…", 12, T["texto"], G)

    def _popup_personalizada(self):
        ui, c, G = self.ui, self.canvas, "popup"
        P, W = px(14), px(236)
        H = 2 * P + px(188)
        x, y = self.posicao_popup(W, H, self.ancoras.get("personalizada"))
        self._fundo_popup(x, y, W, H)
        ui.tx(x + P, y + P + px(13), "Área personalizada", 14, T["texto"], G, peso="bold", anchor="w")
        if self.sel:
            sx0, sy0, sx1, sy1 = self.sel
        else:
            sx0, sy0, sx1, sy1 = self.mon_cursor
        valores = (sx1 - sx0, sy1 - sy0, sx0 + self.ox, sy0 + self.oy)
        rotulos = ("Largura (px)", "Altura (px)", "X", "Y")
        gap = px(10)
        colw = (W - 2 * P - gap) // 2
        self.campos = []
        for i, (rot, v) in enumerate(zip(rotulos, valores)):
            fx = x + P + (i % 2) * (colw + gap)
            fy = y + P + px(36) + (i // 2) * px(58)
            ui.tx(fx, fy, rot, 11, T["texto2"], G, anchor="nw")
            ent = tk.Entry(c, font=fonte(13), bg=T["btn"], fg=T["texto"],
                           insertbackground=T["texto"], relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=T["borda_btn"],
                           highlightcolor=T["azul"], justify="center")
            ent.insert(0, str(int(v)))
            ent.bind("<Return>", lambda e: (self.aplicar_personalizada(), "break")[1])
            ent.bind("<Escape>", lambda e: (self.fechar_popup(), "break")[1])
            c.create_window(fx, fy + px(18), window=ent, anchor="nw", width=colw,
                            height=px(30), tags=(G,))
            self.campos.append(ent)
            self.popup_widgets.append(ent)
        ui.botao_rotulo(x + P, y + P + px(154), W - 2 * P, px(34), "Aplicar", "check",
                        self.aplicar_personalizada, G, tam=13)
        self.campos[0].focus_set()
        self.campos[0].select_range(0, "end")

    def _popup_config(self):
        ui, G = self.ui, "popup"
        P, W = px(14), px(280)
        H = 2 * P + px(26 + 12 + 16 + 22 + 30 + 14 + 30 + 14 + 16 + 22 + 30) + (px(44) if WINDOWS else 0)
        x, y = self.posicao_popup(W, H, self.ancoras.get("config"))
        if y + H > self.ancoras.get("config", (0, 0, 0, y + H))[3]:
            y = max(self.mon_painel[1], self.ancoras.get("config", (0, 0, 0, y + H))[3] - H)
        self._fundo_popup(x, y, W, H)
        yy = y + P
        ui.tx(x + P, yy + px(13), "Configurações", 14, T["texto"], G, peso="bold", anchor="w")
        ui.botao(x + W - P - px(26), yy, px(26), px(26), self.fechar_popup, G, r=px(6),
                 fundo=None, hover=T["btn_hover"])
        ui.ic(x + W - P - px(13), yy + px(13), "fechar", px(15), T["texto2"], G)
        yy += px(26 + 12)

        ui.tx(x + P, yy, "Pasta do botão Salvar", 11, T["texto2"], G, anchor="nw")
        yy += px(16)
        pasta = CONFIG.get("pasta") or pasta_inicial()
        f = tkfont.Font(root=self, font=fonte(12))
        disp, texto = W - 2 * P, pasta
        while f.measure(texto) > disp and len(texto) > 4:
            texto = "…" + (texto[2:] if texto.startswith("…") else texto[1:])
        ui.tx(x + P, yy, texto, 12, T["texto"], G, anchor="nw")
        yy += px(22)
        bw = (W - 2 * P - px(8)) // 2
        ui.botao(x + P, yy, bw, px(30), self.escolher_pasta, G, r=px(7), fundo=T["btn"],
                 hover=T["btn_hover"])
        ui.tx(x + P + bw // 2, yy + px(15), "Alterar…", 12, T["texto"], G)
        ui.botao(x + P + bw + px(8), yy, bw, px(30), self.abrir_pasta, G, r=px(7),
                 fundo=T["btn"], hover=T["btn_hover"])
        ui.ic(x + P + bw + px(8) + px(22), yy + px(15), "pasta", px(16), T["texto"], G)
        ui.tx(x + P + bw + px(8) + px(36), yy + px(15), "Abrir pasta", 12, T["texto"], G, anchor="w")
        yy += px(30 + 14)

        ui.tx(x + P, yy + px(15), "Formato", 13, T["texto2"], G, anchor="w")
        fmt = CONFIG.get("formato", "png")
        ui.segmentos(x + W - P - px(116), yy, px(116), px(30),
                     [("PNG", fmt != "jpg", lambda: self.definir_formato("png")),
                      ("JPG", fmt == "jpg", lambda: self.definir_formato("jpg"))], G)
        yy += px(30 + 14)

        ui.tx(x + P, yy, "Chave da API do ImgBB (para links)", 11, T["texto2"], G, anchor="nw")
        yy += px(16)
        ch = CONFIG.get("imgbb_chave") or ""
        if ch:
            estado = "Definida (…" + ch[-4:] + ")"
        elif IMGBB_CHAVE_PADRAO:
            estado = "Usando a chave padrão"
        else:
            estado = "Não definida"
        ui.tx(x + P, yy, estado, 12, T["texto"], G, anchor="nw")
        yy += px(22)
        ui.botao(x + P, yy, bw, px(30), self.definir_chave, G, r=px(7), fundo=T["btn"],
                 hover=T["btn_hover"])
        ui.tx(x + P + bw // 2, yy + px(15), "Definir chave…", 12, T["texto"], G)
        ui.botao(x + P + bw + px(8), yy, bw, px(30),
                 lambda: webbrowser.open(IMGBB_SITE_CHAVE), G, r=px(7),
                 fundo=T["btn"], hover=T["btn_hover"])
        ui.tx(x + P + bw + px(8) + bw // 2, yy + px(15), "Obter chave", 12, T["texto"], G)
        yy += px(30)

        if WINDOWS:
            yy += px(14)
            ui.botao(x + P - px(6), yy - px(4), W - 2 * P + px(12), px(30), self.alternar_auto, G,
                     r=px(7), fundo=None, hover=T["btn"])
            ui.tx(x + P, yy + px(11), "Iniciar com o Windows", 13, T["texto2"], G, anchor="w")
            ui.interruptor(x + W - P - px(40), yy, auto_ativo(), G)

    def escolher_pasta(self):
        pasta = self.dialogo(filedialog.askdirectory, title="Pasta do botão Salvar",
                             initialdir=CONFIG.get("pasta") or pasta_inicial())
        if pasta:
            CONFIG["pasta"] = os.path.normpath(pasta)
            salvar_config()
        if not self.fechado:
            self.abrir_popup("config")

    def abrir_pasta(self):
        pasta = CONFIG.get("pasta") or pasta_inicial()
        try:
            os.makedirs(pasta, exist_ok=True)
            if WINDOWS:
                os.startfile(pasta)
            else:
                subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", pasta])
        except Exception as ex:
            self.aviso(f"Não foi possível abrir a pasta: {ex}")

    def pedir_chave(self):
        chave = self.dialogo(
            simpledialog.askstring, title="Chave da API do ImgBB",
            prompt="Cole a sua chave da API do ImgBB.\n"
                   f"Crie uma grátis em {IMGBB_SITE_CHAVE}\n"
                   "(deixe em branco para remover)",
            initialvalue=CONFIG.get("imgbb_chave") or "")
        if chave is None:
            return None
        CONFIG["imgbb_chave"] = chave.strip()
        salvar_config()
        return CONFIG["imgbb_chave"]

    def definir_chave(self):
        self.fechar_popup()
        self.pedir_chave()
        if not self.fechado:
            self.abrir_popup("config")

    def definir_formato(self, fmt):
        CONFIG["formato"] = fmt
        salvar_config()
        self.abrir_popup("config")

    def alternar_auto(self):
        try:
            definir_auto(not auto_ativo())
        except Exception as ex:
            self.aviso(f"Não foi possível alterar a inicialização: {ex}")
        self.abrir_popup("config")

    # --- ações finais -----------------------------------------------------------
    def renderizar(self):
        return compor(self.imagem, self.sel, self.anotacoes if self.anot_visiveis else [])

    def copiar(self):
        if not self.editando:
            return
        self.confirmar_texto()
        try:
            copiar_imagem_para_clipboard(self.renderizar())
        except Exception as ex:
            self.dialogo(messagebox.showerror, title="Erro ao copiar", message=str(ex))
            return
        self.aviso("Copiado para a área de transferência   •   Ctrl+V para colar")

    def copiar_e_fechar(self):
        if not self.editando:
            return
        self.confirmar_texto()
        try:
            copiar_imagem_para_clipboard(self.renderizar())
        except Exception as ex:
            self.dialogo(messagebox.showerror, title="Erro ao copiar", message=str(ex))
            return
        self.fechar("Copiado para a área de transferência — é só colar (Ctrl+V).")

    def enviar_link(self):
        """Envia ao ImgBB e copia o link público para a área de transferência."""
        if not self.editando or self.enviando:
            return
        self.confirmar_texto()
        self.fechar_popup()
        chave = chave_imgbb()
        if not chave:
            if self.dialogo(messagebox.askyesno, title="Chave do ImgBB",
                            message="Para gerar links é preciso uma chave (grátis) da API do "
                                    "ImgBB.\n\nAbrir o site para criar a chave agora?"):
                webbrowser.open(IMGBB_SITE_CHAVE)
            chave = (self.pedir_chave() or "").strip()
            if not chave:
                return
        jpg = CONFIG.get("formato") == "jpg"
        try:
            buf = io.BytesIO()
            img = self.renderizar()
            if jpg:
                img.convert("RGB").save(buf, "JPEG", quality=92)
            else:
                img.save(buf, "PNG")
        except Exception as ex:
            self.dialogo(messagebox.showerror, title="Erro ao enviar", message=str(ex))
            return
        nome = time.strftime("captura_%Y%m%d_%H%M%S")
        resultado = {}

        def trabalho():
            try:
                resultado["link"] = enviar_imgbb(buf.getvalue(), chave, nome)
            except Exception as ex:
                resultado["erro"] = str(ex)

        self.enviando = True
        self.atualizar_painel()
        self.aviso("Enviando imagem para o ImgBB…", ms=120000)
        threading.Thread(target=trabalho, daemon=True).start()
        self.after(150, self._aguardar_envio, resultado)

    def _aguardar_envio(self, resultado):
        if not resultado:
            if not self.fechado:
                self.after(150, self._aguardar_envio, resultado)
            return
        self.enviando = False
        if self.fechado:  # o usuário fechou a captura durante o envio
            return
        if "erro" in resultado:
            self._fim_aviso()
            self.atualizar_painel()
            self.dialogo(messagebox.showerror, title="Erro ao enviar", message=resultado["erro"])
            return
        link = resultado["link"]
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(link)
            self.master.update()
        except tk.TclError:
            pass
        self.fechar(f"Link copiado: {link}")

    @staticmethod
    def _gravar(img, caminho):
        if caminho.lower().endswith((".jpg", ".jpeg")):
            img.save(caminho, quality=95)
        else:
            img.save(caminho)

    def salvar_rapido(self):
        """Salva direto na pasta configurada, sem perguntar."""
        if not self.editando:
            return
        self.confirmar_texto()
        pasta = CONFIG.get("pasta") or pasta_inicial()
        ext = ".jpg" if CONFIG.get("formato") == "jpg" else ".png"
        base = time.strftime("captura_%Y%m%d_%H%M%S")
        try:
            os.makedirs(pasta, exist_ok=True)
            caminho, n = os.path.join(pasta, base + ext), 2
            while os.path.exists(caminho):
                caminho, n = os.path.join(pasta, f"{base}_{n}{ext}"), n + 1
            self._gravar(self.renderizar(), caminho)
        except Exception as ex:
            self.dialogo(messagebox.showerror, title="Erro ao salvar", message=str(ex))
            return
        self.fechar(f"Salvo em: {caminho}")

    def salvar_como(self):
        if not self.editando:
            return
        self.confirmar_texto()
        self.fechar_popup()
        img = self.renderizar()
        if not ULTIMA_PASTA["v"]:
            ULTIMA_PASTA["v"] = CONFIG.get("pasta") or pasta_inicial()
        jpg = CONFIG.get("formato") == "jpg"
        tipos = [("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg"), ("Bitmap", "*.bmp")]
        if jpg:
            tipos = [tipos[1], tipos[0], tipos[2]]
        nome = time.strftime("captura_%Y%m%d_%H%M%S") + (".jpg" if jpg else ".png")
        caminho = self.dialogo(
            filedialog.asksaveasfilename, defaultextension=".jpg" if jpg else ".png",
            initialfile=nome, initialdir=ULTIMA_PASTA["v"], title="Salvar captura",
            filetypes=tipos)
        if not caminho:
            return
        try:
            self._gravar(img, caminho)
        except Exception as ex:
            self.dialogo(messagebox.showerror, title="Erro ao salvar", message=str(ex))
            return
        ULTIMA_PASTA["v"] = os.path.dirname(caminho)
        self.fechar(f"Salvo em: {caminho}")

    # --- teclado -------------------------------------------------------------------
    def tecla_copiar(self):
        if self.digitando():
            return
        self.copiar_e_fechar()

    def tecla_z(self, e):
        if self.digitando() and not self.entry:
            return
        if e.state & 0x1:  # Shift
            self.refazer()
        else:
            self.desfazer()

    def tecla_refazer(self):
        if self.digitando():
            return
        self.refazer()

    def tecla_modo(self, modo):
        if self.digitando() or self.modo:
            return
        if modo == "tela":
            self.captura_tela_inteira()
        else:
            self.captura_janela()

    def tecla_esc(self):
        if self.popup:
            self.fechar_popup()
        elif self.entry:
            self.cancelar_texto()
        else:
            self.cancelar()

    def cancelar(self):
        self.fechar(None)

    def fechar(self, msg=None):
        if self.fechado:
            return
        self.fechado = True
        CONFIG.update(ferramenta=self.ferramenta, cor=self.cor, largura=self.largura,
                      recolhidos=sorted(self.recolhidos))
        salvar_config()
        try:
            self.destroy()
        except tk.TclError:
            pass
        self.ao_concluir(msg)


# ----------------------------------------------------------------------------
# Janela principal + atalho global (PrtSc)
# ----------------------------------------------------------------------------
if WINDOWS:
    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM)
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HICON), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                    ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                    ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                    ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                    ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                    ("dwInfoFlags", wintypes.DWORD), ("guidItem", ctypes.c_ubyte * 16),
                    ("hBalloonIcon", wintypes.HICON)]


CLASSE_BANDEJA = "PrintscCapturaBandeja"
WM_BANDEJA = 0x8001        # WM_APP + 1: eventos do ícone
WM_MOSTRAR = 0x8002        # WM_APP + 2: outra instância pediu para abrir a janela
WM_SAIR = 0x8003           # WM_APP + 3: instalador/desinstalador pediu para encerrar
NOME_AUTO = "PrintscCapturaTela"
CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"

# --- instalação (usado pelo instalador e pelo "--desinstalar") -----------------
NOME_APP = "PrintaAí"
EXE_APP = "PrintaAi.exe"
VERSAO_APP = "1.2.1"
AUTOR = "Marcos Barros"
CHAVE_DESINSTALAR = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PrintaAi"


def pasta_instalacao():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", "PrintaAi")


def pasta_especial(csidl):
    """Pastas do Windows (respeita Área de Trabalho redirecionada pelo OneDrive)."""
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return buf.value


def caminhos_atalhos():
    return {"menu": os.path.join(pasta_especial(0x02), NOME_APP + ".lnk"),        # CSIDL_PROGRAMS
            "desktop": os.path.join(pasta_especial(0x10), NOME_APP + ".lnk")}     # CSIDL_DESKTOPDIRECTORY


def fechar_instancia_aberta(espera=6.0):
    """Pede para a cópia em execução encerrar; retorna True se não sobrou nenhuma."""
    u = ctypes.windll.user32
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowW.restype = wintypes.HWND
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    hwnd = u.FindWindowW(CLASSE_BANDEJA, None)
    if not hwnd:
        return True
    u.PostMessageW(hwnd, WM_SAIR, 0, 0)
    limite = time.time() + espera
    while time.time() < limite:
        time.sleep(0.2)
        if not u.FindWindowW(CLASSE_BANDEJA, None):
            time.sleep(0.5)  # dá tempo do processo terminar e soltar o .exe
            return True
    return False


def desinstalar():
    import winreg
    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno(f"Desinstalar {NOME_APP}",
                               f"Deseja remover o {NOME_APP} deste computador?"):
        root.destroy()
        return
    fechar_instancia_aberta()
    try:
        definir_auto(False)
    except Exception:
        pass
    for caminho in caminhos_atalhos().values():
        try:
            os.remove(caminho)
        except OSError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, CHAVE_DESINSTALAR)
    except OSError:
        pass
    pasta = pasta_instalacao()
    if getattr(sys, "frozen", False) and \
            os.path.normcase(os.path.dirname(sys.executable)) == os.path.normcase(pasta):
        # apaga a pasta depois que este processo terminar
        subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 4 > nul & rmdir /s /q "{pasta}"',
                         creationflags=0x08000000, cwd=tempfile.gettempdir())
    messagebox.showinfo(NOME_APP, f"O {NOME_APP} foi removido deste computador.")
    root.destroy()


def criar_icone():
    """Desenha o ícone do programa e salva um .ico temporário."""
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, 247, 247], radius=58, fill=_rgba(T["azul"]))
    logo = icone_pil("logo", 176, "#ffffff")
    img.alpha_composite(logo, (40, 40))
    img = img.resize((64, 64), Image.LANCZOS)
    caminho = os.path.join(tempfile.gettempdir(), "printflex_icone.ico")
    try:
        img.save(caminho, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64)])
    except Exception:
        caminho = None
    return img, caminho


# --- iniciar com o Windows (registro HKCU\...\Run) ----------------------------
def comando_auto():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{os.path.abspath(__file__)}"'


def auto_ativo():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as k:
            winreg.QueryValueEx(k, NOME_AUTO)
        return True
    except OSError:
        return False


def definir_auto(ligar):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if ligar:
            winreg.SetValueEx(k, NOME_AUTO, 0, winreg.REG_SZ, comando_auto())
        else:
            try:
                winreg.DeleteValue(k, NOME_AUTO)
            except FileNotFoundError:
                pass


# --- ícone na bandeja (área de notificação) ------------------------------------
class Bandeja:
    """Ícone na bandeja do Windows, com thread e janela oculta próprias."""
    MENU_CAPTURAR, MENU_ABRIR, MENU_AUTO, MENU_SAIR, MENU_TELA = 1, 2, 3, 4, 5

    def __init__(self, fila, caminho_ico, dica="PrintaAí"):
        self.fila = fila
        self.caminho_ico = caminho_ico
        self.dica = dica
        self.hwnd = None
        self.hicon = None
        self.ok = False
        self._pronto = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()
        self._pronto.wait(5)

    def _api(self):
        u, s, k = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
        u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.DefWindowProcW.restype = ctypes.c_ssize_t
        u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                      wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                      wintypes.HINSTANCE, wintypes.LPVOID]
        u.CreateWindowExW.restype = wintypes.HWND
        u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.LoadImageW.restype = wintypes.HANDLE
        u.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
        u.LoadIconW.restype = wintypes.HICON
        u.CreatePopupMenu.restype = wintypes.HMENU
        u.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        u.SetMenuDefaultItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
        u.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
        u.DestroyMenu.argtypes = [wintypes.HMENU]
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.DestroyWindow.argtypes = [wintypes.HWND]
        u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                  wintypes.UINT, wintypes.UINT]
        s.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        k.GetModuleHandleW.restype = wintypes.HMODULE
        return u, s, k

    def _dados(self, flags):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = flags
        return nid

    def _adicionar(self):
        nid = self._dados(0x1 | 0x2 | 0x4)  # NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_BANDEJA
        nid.hIcon = self.hicon
        nid.szTip = self.dica[:127]
        return bool(self.s.Shell_NotifyIconW(0, ctypes.byref(nid)))  # NIM_ADD

    def _remover(self):
        if self.hwnd:
            self.s.Shell_NotifyIconW(2, ctypes.byref(self._dados(0)))  # NIM_DELETE

    def _loop(self):
        try:
            self.u, self.s, k = u, s, k = self._api()
            hinst = k.GetModuleHandleW(None)
            self._proc = WNDPROC(self._wndproc)
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._proc
            wc.hInstance = hinst
            wc.lpszClassName = CLASSE_BANDEJA
            u.RegisterClassW(ctypes.byref(wc))
            self.msg_taskbar = u.RegisterWindowMessageW("TaskbarCreated")
            self.hwnd = u.CreateWindowExW(0, CLASSE_BANDEJA, "PrintaAí", 0,
                                          0, 0, 0, 0, None, None, hinst, None)
            if self.caminho_ico:
                lado = u.GetSystemMetrics(49)  # SM_CXSMICON
                self.hicon = u.LoadImageW(None, self.caminho_ico, 1, lado, lado, 0x10)
            if not self.hicon:
                self.hicon = u.LoadIconW(None, ctypes.c_void_p(32512))  # IDI_APPLICATION
            self.ok = bool(self.hwnd) and self._adicionar()
        except Exception:
            self.ok = False
        self._pronto.set()
        if not self.ok:
            return
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_BANDEJA:
                evento = lp & 0xFFFF
                if evento == 0x202:                  # WM_LBUTTONUP: clique simples
                    self.fila.put(("capturar_bandeja", None))
                elif evento in (0x205, 0x7B):        # WM_RBUTTONUP / WM_CONTEXTMENU
                    self._menu()
                return 0
            if msg == WM_MOSTRAR:
                self.fila.put(("mostrar", None))
                return 0
            if msg == WM_SAIR:
                self.fila.put(("sair", None))
                return 0
            if msg == self.msg_taskbar:              # o Explorer reiniciou
                self._adicionar()
                return 0
            if msg == 0x0010:                        # WM_CLOSE
                self._remover()
                self.u.DestroyWindow(hwnd)
                return 0
            if msg == 0x0002:                        # WM_DESTROY
                self.u.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return self.u.DefWindowProcW(hwnd, msg, wp, lp)

    def _menu(self):
        u = self.u
        m = u.CreatePopupMenu()
        u.AppendMenuW(m, 0, self.MENU_CAPTURAR, "Selecionar área\tPrtSc")
        u.AppendMenuW(m, 0, self.MENU_TELA, "Tela inteira")
        u.AppendMenuW(m, 0, self.MENU_ABRIR, "Abrir janela")
        u.AppendMenuW(m, 0x800, 0, None)  # separador
        u.AppendMenuW(m, 0x8 if auto_ativo() else 0, self.MENU_AUTO, "Iniciar com o Windows")
        u.AppendMenuW(m, 0x800, 0, None)
        u.AppendMenuW(m, 0, self.MENU_SAIR, "Sair")
        u.SetMenuDefaultItem(m, self.MENU_CAPTURAR, 0)
        pt = wintypes.POINT()
        u.GetCursorPos(ctypes.byref(pt))
        u.SetForegroundWindow(self.hwnd)  # necessário para o menu fechar ao clicar fora
        cmd = u.TrackPopupMenu(m, 0x0002 | 0x0100 | 0x0080, pt.x, pt.y, 0, self.hwnd, None)
        u.PostMessageW(self.hwnd, 0, 0, 0)  # WM_NULL
        u.DestroyMenu(m)
        acoes = {self.MENU_CAPTURAR: "capturar_bandeja", self.MENU_TELA: "capturar_tela",
                 self.MENU_ABRIR: "mostrar", self.MENU_AUTO: "alternar_auto",
                 self.MENU_SAIR: "sair"}
        if cmd in acoes:
            self.fila.put((acoes[cmd], None))

    # --- chamados pela thread do Tk ---
    def notificar(self, titulo, texto):
        if not self.ok:
            return
        try:
            nid = self._dados(0x10)  # NIF_INFO
            nid.szInfoTitle = titulo[:63]
            nid.szInfo = texto[:255]
            nid.dwInfoFlags = 0x1 | 0x10  # NIIF_INFO | NIIF_NOSOUND
            self.s.Shell_NotifyIconW(1, ctypes.byref(nid))  # NIM_MODIFY
        except Exception:
            pass

    def encerrar(self):
        if self.ok:
            try:
                self._remover()
                self.u.PostMessageW(self.hwnd, 0x0010, 0, 0)
            except Exception:
                pass
            self.ok = False


class App:
    LARGURA = 320

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PrintaAí")
        self.root.resizable(False, False)
        UI["esc"] = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        carregar_config()
        self.fila = queue.Queue()
        self.capturando = False
        self.volta = "normal"
        self.tid = None
        self._cb = None
        self._hook = None
        self.bandeja = None
        self.avisou_bandeja = False
        self.atalho_ok = False
        self.txt_status = "Iniciando atalho…"
        self.txt_ultima = ""

        img_icone, caminho_ico = criar_icone()
        try:
            self._tk_icone = ImageTk.PhotoImage(img_icone)
            self.root.iconphoto(True, self._tk_icone)
        except Exception:
            pass

        self.root.configure(bg=T["painel"])
        self.cv = tk.Canvas(self.root, bg=T["painel"], highlightthickness=0, bd=0,
                            width=px(self.LARGURA), height=px(400))
        self.cv.pack()
        self.ui = Superficie(self.cv)
        self.cv.bind("<Motion>", self._mover_mouse)
        self.cv.bind("<Leave>", lambda e: self.ui.mover(-1, -1))
        self.cv.bind("<ButtonPress-1>", lambda e: self.ui.pressionar(e.x, e.y))
        self.cv.bind("<ButtonRelease-1>", lambda e: self.ui.soltar(e.x, e.y))

        self.root.protocol("WM_DELETE_WINDOW", self.fechar_janela)
        if WINDOWS:
            self.bandeja = Bandeja(self.fila, caminho_ico)
            if not self.bandeja.ok:
                self.bandeja = None
            threading.Thread(target=self._loop_teclado, daemon=True).start()
        else:
            self.txt_status = "O atalho global funciona só no Windows. Use os botões abaixo."
        self.desenhar_janela()

        if self.bandeja and "--janela" not in sys.argv:
            self.root.withdraw()  # inicia direto na bandeja
            self.bandeja.notificar("PrintaAí",
                                   "Ativo na bandeja. Aperte PrtSc ou clique no ícone.")
            self.avisou_bandeja = True
        elif not self.bandeja and "--minimizado" in sys.argv:
            self.root.iconify()
        self.root.after(50, self.barra_escura)
        self.root.after(80, self.processar_fila)

    # --- janela principal ---------------------------------------------------------
    def barra_escura(self):
        """Barra de título escura no Windows 10/11."""
        if not WINDOWS:
            return
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            valor = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20,
                                                       ctypes.byref(valor), 4)
        except Exception:
            pass

    def _mover_mouse(self, e):
        a = self.ui.mover(e.x, e.y)
        self.cv.config(cursor="hand2" if (a and a["acao"] and a["ok"]) else "")

    def desenhar_janela(self):
        ui, c, G = self.ui, self.cv, "j"
        ui.limpar(G)
        W, P = px(self.LARGURA), px(18)
        IW = W - 2 * P

        y = P
        ui.ic(P, y + px(17), "logo", px(34), T["azul"], G, anchor="w")
        t = ui.tx(P + px(44), y + px(17), "Printa", 21, T["texto"], G, peso="bold", anchor="w")
        ui.tx(c.bbox(t)[2] - 1, y + px(17), "Aí", 21, T["azul"], G, peso="bold", anchor="w")
        y += px(34 + 16)

        t = ui.tx(P + px(34), y + px(13), self.txt_status, 12, T["texto"], G, anchor="nw",
                  largura=IW - px(48))
        ch = max(px(46), c.bbox(t)[3] - y + px(13))
        cartao = ui.fundo(P, y, IW, ch, px(12), T["card"], T["card_borda"], G,
                          esp=max(1.0, UI["esc"]))
        c.tag_lower(cartao, t)
        ui.fundo(P + px(14), y + px(17), px(10), px(10), px(5),
                 "#34c759" if self.atalho_ok else "#ff9f0a", None, G)
        y += ch + px(14)

        ui.botao_rotulo(P, y, IW, px(44), "Selecionar área", "selecao",
                        lambda: self.capturar("normal"), G)
        y += px(44 + 8)
        ui.botao_rotulo(P, y, IW, px(40), "Tela inteira", "monitor",
                        lambda: self.capturar("normal", "tela"), G, estilo="secundario")
        y += px(40 + 14)

        dica = ("Atalho: PrtSc  •  ou clique no ícone da bandeja\n"
                "Fechar esta janela mantém o programa na bandeja."
                if self.bandeja else "PrtSc em qualquer janela para capturar.")
        t = ui.tx(W // 2, y, dica, 11, T["texto2"], G, anchor="n", largura=IW)
        y = c.bbox(t)[3] + px(14)

        if WINDOWS:
            ui.botao(P, y, IW, px(42), self.alternar_auto, G, r=px(10), fundo=T["card"],
                     hover=T["btn"], borda=T["card_borda"], esp=max(1.0, UI["esc"]))
            ui.tx(P + px(14), y + px(21), "Iniciar com o Windows", 13, T["texto"], G, anchor="w")
            ui.interruptor(P + IW - px(54), y + px(10), auto_ativo(), G)
            y += px(42 + 12)

        if self.txt_ultima:
            t = ui.tx(W // 2, y, self.txt_ultima, 11, T["verde"], G, anchor="n", largura=IW)
            y = c.bbox(t)[3] + px(12)

        if self.bandeja:
            ui.botao(P, y, IW, px(32), self.sair, G, r=px(8), fundo=None, hover=T["btn"])
            ui.tx(W // 2, y + px(16), "Sair do programa", 12, T["vermelho"], G)
            y += px(32 + 4)
        y += px(6)
        c.create_line(P, y, W - P, y, fill=T["card_borda"], tags=G)
        y += px(12)
        ui.tx(W // 2, y, f"Versão {VERSAO_APP}   •   Desenvolvido por {AUTOR}", 11,
              T["apagado"], G, anchor="n")
        y += px(16)
        c.config(width=W, height=y + P - px(4))

    # --- atalho global (Windows) ---------------------------------------------
    def _loop_teclado(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        ativos, usou_hook = [], False
        try:
            self.tid = kernel32.GetCurrentThreadId()
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                                 wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                              wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                           wintypes.UINT, wintypes.UINT]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            fila = self.fila

            def proc(n_code, w_param, l_param):
                try:
                    if n_code == 0:
                        info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        if info.vkCode == 0x2C:  # VK_SNAPSHOT (PrtSc)
                            alt = bool(info.flags & 0x20)
                            win = (user32.GetAsyncKeyState(0x5B) & 0x8000) or \
                                  (user32.GetAsyncKeyState(0x5C) & 0x8000)
                            if not alt and not win:
                                if w_param in (0x100, 0x104):  # tecla pressionada
                                    fila.put(("capturar", None))
                                return 1  # engole a tecla (impede o Windows de reagir)
                except Exception:
                    pass
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            self._cb = HOOKPROC(proc)
            self._hook = user32.SetWindowsHookExW(13, self._cb,
                                                  kernel32.GetModuleHandleW(None), 0)
            if self._hook:
                usou_hook, ativos = True, ["PrtSc"]
            else:
                # Plano B: atalhos registrados (podem conflitar com o Windows)
                for i, (nome, mod) in enumerate((("PrtSc", 0), ("Ctrl+Shift+PrtSc", 2 | 4)), 1):
                    if user32.RegisterHotKey(None, i, mod | 0x4000, 0x2C):
                        ativos.append(nome)
        except Exception:
            pass
        self.fila.put(("atalhos", (ativos, usou_hook)))

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                self.fila.put(("capturar", None))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)

    def mostrar_atalhos(self, ativos, usou_hook):
        if usou_hook:
            texto = "Pronto! Aperte PrtSc em qualquer janela para capturar."
        elif ativos:
            texto = ("Atalho(s) ativo(s): " + ", ".join(ativos) + ". "
                     "Se a PrtSc não responder, desative em Configurações > Acessibilidade > "
                     "Teclado > \"Usar o botão Print Screen para abrir a captura de tela\".")
        else:
            texto = "Não consegui registrar o atalho global. Use os botões abaixo."
        self.atalho_ok = bool(ativos)
        self.txt_status = texto
        self.desenhar_janela()

    def processar_fila(self):
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "capturar":  # PrtSc: volta ao estado em que a janela estava
                    self.capturar("normal" if self.root.state() == "normal" else "minimizar")
                elif tipo == "capturar_bandeja":
                    self.capturar("minimizar")
                elif tipo == "capturar_tela":
                    self.capturar("minimizar", "tela")
                elif tipo == "mostrar":
                    self.mostrar_janela()
                elif tipo == "alternar_auto":
                    self.alternar_auto()
                elif tipo == "sair":
                    self.sair()
                    return
                elif tipo == "atalhos":
                    self.mostrar_atalhos(*valor)
        except queue.Empty:
            pass
        self.root.after(80, self.processar_fila)

    # --- captura ---------------------------------------------------------------
    def capturar(self, volta="minimizar", inicial=None):
        if self.capturando:
            return
        self.capturando = True
        self.volta = volta
        janela = rect_janela_ativa()
        estado = self.root.state()
        if estado != "withdrawn":
            self.root.withdraw()
            self.root.update()
            if estado == "normal":
                time.sleep(0.2)  # tempo para a janela sumir antes de capturar
        try:
            imagem, origem = capturar_tela()
        except Exception as ex:
            self.capturando = False
            self.restaurar()
            messagebox.showerror("Erro", f"Não foi possível capturar a tela:\n{ex}")
            return
        try:
            Overlay(self.root, imagem, origem, self.fim_captura, janela, inicial)
        except Exception as ex:
            self.capturando = False
            self.restaurar()
            messagebox.showerror("Erro", f"Falha ao abrir a seleção:\n{ex}")

    def fim_captura(self, msg):
        self.capturando = False
        if msg:
            self.txt_ultima = f"{time.strftime('%H:%M:%S')} — {msg}"
            self.desenhar_janela()
            if self.bandeja and self.volta != "normal" and msg.startswith(("Salvo", "Link")):
                self.bandeja.notificar("PrintaAí", msg)
        self.restaurar()

    def restaurar(self):
        if self.volta == "normal":
            self.root.deiconify()
        elif self.bandeja:
            self.root.withdraw()  # continua só na bandeja
        else:
            self.root.iconify()

    # --- janela / bandeja --------------------------------------------------------
    def mostrar_janela(self):
        if self.capturando:
            return
        self.desenhar_janela()
        self.root.deiconify()
        self.barra_escura()
        forcar_foco(self.root)

    def fechar_janela(self):
        if not self.bandeja:
            self.sair()
            return
        self.root.withdraw()
        if not self.avisou_bandeja:
            self.bandeja.notificar("PrintaAí",
                                   "Continuo ativo na bandeja. Para encerrar: botão direito > Sair.")
            self.avisou_bandeja = True

    def alternar_auto(self):
        try:
            ligar = not auto_ativo()
            definir_auto(ligar)
        except Exception as ex:
            messagebox.showerror("Erro", f"Não foi possível alterar a inicialização:\n{ex}")
            return
        self.desenhar_janela()
        if self.bandeja:
            self.bandeja.notificar("PrintaAí",
                                   "Vai iniciar junto com o Windows." if ligar else
                                   "Não vai mais iniciar com o Windows.")

    def sair(self):
        if self.bandeja:
            self.bandeja.encerrar()
        if WINDOWS and self.tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(self.tid, 0x12, 0, 0)  # WM_QUIT
            except Exception:
                pass
        self.root.destroy()

    def executar(self):
        self.root.mainloop()


def ja_esta_rodando():
    """Garante uma única instância; se já houver uma, pede para ela abrir a janela."""
    if not WINDOWS:
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype = wintypes.HANDLE
    globals()["_MUTEX"] = k32.CreateMutexW(None, False, "Local\\PrintscCapturaTelaUnica")
    if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
        return False
    u = ctypes.windll.user32
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowW.restype = wintypes.HWND
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    hwnd = u.FindWindowW(CLASSE_BANDEJA, None)
    if hwnd:
        u.PostMessageW(hwnd, WM_MOSTRAR, 0, 0)
    return True


if __name__ == "__main__":
    if "--desinstalar" in sys.argv:
        desinstalar()
    elif not ja_esta_rodando():
        App().executar()
