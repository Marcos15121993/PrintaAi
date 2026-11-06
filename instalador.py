#!/usr/bin/env python3
"""
Instalador do PrintaAí
======================
Copia o PrintaAi.exe para %LOCALAPPDATA%\\Programs\\PrintaAi (não precisa de administrador),
cria atalhos (Menu Iniciar e, se quiser, Área de Trabalho), liga o "iniciar com o Windows"
e registra o programa em Configurações > Aplicativos (para desinstalar).

Gerado como Instalar_PrintaAi.exe com o PrintaAi.exe embutido (veja gerar_exe.bat).
"""

import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
import winreg

import Printsc as app
from Printsc import T, px, Superficie, NOME_APP, EXE_APP

SEM_JANELA = 0x08000000      # CREATE_NO_WINDOW
DESANEXADO = 0x00000008      # DETACHED_PROCESS


def recurso(nome):
    """Arquivo embutido no instalador (ou, rodando como .py, o da pasta dist)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    caminho = os.path.join(base, nome)
    if not os.path.exists(caminho):
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", nome)
    return caminho


def env_limpo():
    """Ambiente sem as variáveis do PyInstaller (para abrir outro .exe do PyInstaller)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def criar_atalho(lnk, alvo, pasta):
    os.makedirs(os.path.dirname(lnk), exist_ok=True)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:PA_LNK);"
          "$s.TargetPath=$env:PA_ALVO;$s.WorkingDirectory=$env:PA_DIR;"
          "$s.IconLocation=$env:PA_ALVO+',0';$s.Description='Captura de tela';$s.Save()")
    env = env_limpo()
    env.update(PA_LNK=lnk, PA_ALVO=alvo, PA_DIR=pasta)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-Command", ps], env=env, check=True, capture_output=True,
                   creationflags=SEM_JANELA)


def instalar(desktop, iniciar_com_windows):
    origem = recurso(EXE_APP)
    if not os.path.exists(origem):
        raise RuntimeError("O arquivo do programa não foi encontrado dentro do instalador.")
    pasta = app.pasta_instalacao()
    destino = os.path.join(pasta, EXE_APP)
    os.makedirs(pasta, exist_ok=True)

    # Se já estiver rodando (atualização), pede para fechar antes de substituir
    app.fechar_instancia_aberta()
    for tentativa in range(25):
        try:
            shutil.copy2(origem, destino)
            break
        except PermissionError:
            if tentativa == 5:
                subprocess.run(["taskkill", "/f", "/im", EXE_APP], capture_output=True,
                               creationflags=SEM_JANELA)
            time.sleep(0.4)
    else:
        raise RuntimeError(f"O {NOME_APP} está em uso. Feche-o pela bandeja e tente de novo.")

    atalhos = app.caminhos_atalhos()
    criar_atalho(atalhos["menu"], destino, pasta)
    if desktop:
        criar_atalho(atalhos["desktop"], destino, pasta)
    elif os.path.exists(atalhos["desktop"]):
        os.remove(atalhos["desktop"])

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, app.CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if iniciar_com_windows:
            winreg.SetValueEx(k, app.NOME_AUTO, 0, winreg.REG_SZ, f'"{destino}"')
        else:
            try:
                winreg.DeleteValue(k, app.NOME_AUTO)
            except FileNotFoundError:
                pass

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, app.CHAVE_DESINSTALAR) as k:
        valores = {"DisplayName": NOME_APP, "DisplayVersion": app.VERSAO_APP,
                   "Publisher": app.AUTOR, "DisplayIcon": destino, "InstallLocation": pasta,
                   "UninstallString": f'"{destino}" --desinstalar',
                   "QuietUninstallString": f'"{destino}" --desinstalar'}
        for nome, valor in valores.items():
            winreg.SetValueEx(k, nome, 0, winreg.REG_SZ, valor)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD,
                          os.path.getsize(destino) // 1024)
    return destino


class Instalador:
    LARGURA = 380

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Instalar {NOME_APP}")
        self.root.resizable(False, False)
        app.UI["esc"] = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        try:
            img, _ = app.criar_icone()
            from PIL import ImageTk
            self._icone = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self._icone)
        except Exception:
            pass
        self.root.configure(bg=T["painel"])
        self.cv = tk.Canvas(self.root, bg=T["painel"], highlightthickness=0, bd=0,
                            width=px(self.LARGURA), height=px(400))
        self.cv.pack()
        self.ui = Superficie(self.cv)
        self.cv.bind("<Motion>", self._mover)
        self.cv.bind("<Leave>", lambda e: self.ui.mover(-1, -1))
        self.cv.bind("<ButtonPress-1>", lambda e: self.ui.pressionar(e.x, e.y))
        self.cv.bind("<ButtonRelease-1>", lambda e: self.ui.soltar(e.x, e.y))

        self.estado = "inicio"     # inicio | instalando | ok
        self.erro = ""
        self.desktop = True
        self.auto = True
        self.destino = None
        self.ja_instalado = os.path.exists(os.path.join(app.pasta_instalacao(), EXE_APP))
        self.desenhar()
        self.centralizar()
        self.root.after(50, self.barra_escura)

    def barra_escura(self):
        try:
            import ctypes
            from ctypes import wintypes
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            valor = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20,
                                                       ctypes.byref(valor), 4)
        except Exception:
            pass

    def centralizar(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 3
        self.root.geometry(f"+{x}+{y}")

    def _mover(self, e):
        a = self.ui.mover(e.x, e.y)
        self.cv.config(cursor="hand2" if (a and a["acao"] and a["ok"]) else "")

    def _linha_opcao(self, x, y, w, texto, ligado, acao, G):
        self.ui.botao(x, y, w, px(42), acao, G, r=px(10), fundo=T["card"], hover=T["btn"],
                      borda=T["card_borda"], esp=max(1.0, app.UI["esc"]))
        self.ui.tx(x + px(14), y + px(21), texto, 13, T["texto"], G, anchor="w")
        self.ui.interruptor(x + w - px(54), y + px(10), ligado, G)

    def desenhar(self):
        ui, c, G = self.ui, self.cv, "j"
        ui.limpar(G)
        W, P = px(self.LARGURA), px(22)
        IW = W - 2 * P

        y = P
        ui.ic(P, y + px(17), "logo", px(34), T["azul"], G, anchor="w")
        t = ui.tx(P + px(44), y + px(17), "Printa", 21, T["texto"], G, peso="bold", anchor="w")
        ui.tx(c.bbox(t)[2] - 1, y + px(17), "Aí", 21, T["azul"], G, peso="bold", anchor="w")
        y += px(34 + 18)

        if self.estado == "ok":
            ui.fundo(W // 2 - px(28), y, px(56), px(56), px(28), "#16351f", None, G)
            ui.ic(W // 2, y + px(28), "check", px(30), T["verde"], G)
            y += px(56 + 16)
            ui.tx(W // 2, y, "Instalação concluída!", 16, T["texto"], G, peso="bold", anchor="n")
            y += px(30)
            t = ui.tx(W // 2, y, f"O {NOME_APP} fica na bandeja do Windows (perto do relógio). "
                                 "Aperte PrtSc em qualquer janela para capturar.",
                      12, T["texto2"], G, anchor="n", largura=IW)
            y = c.bbox(t)[3] + px(20)
            ui.botao_rotulo(P, y, IW, px(44), f"Abrir o {NOME_APP}", "selecao", self.abrir_e_sair, G)
            y += px(44 + 8)
            ui.botao_rotulo(P, y, IW, px(40), "Fechar", None, self.root.destroy, G,
                            estilo="secundario")
            y += px(40)
        else:
            t = ui.tx(P, y, "Captura de tela com anotações. Fica na bandeja do Windows e abre "
                            "com a tecla PrtSc.", 12, T["texto2"], G, anchor="nw", largura=IW)
            y = c.bbox(t)[3] + px(16)
            ui.tx(P, y, "Local da instalação", 11, T["texto2"], G, anchor="nw")
            y += px(17)
            t = ui.tx(P, y, app.pasta_instalacao(), 11, T["texto"], G, anchor="nw", largura=IW)
            y = c.bbox(t)[3] + px(16)

            self._linha_opcao(P, y, IW, "Iniciar com o Windows", self.auto, self.alternar_auto, G)
            y += px(42 + 8)
            self._linha_opcao(P, y, IW, "Atalho na Área de Trabalho", self.desktop,
                              self.alternar_desktop, G)
            y += px(42 + 18)

            if self.ja_instalado:
                ui.tx(W // 2, y, "Já existe uma versão instalada — ela será atualizada.", 11,
                      T["texto2"], G, anchor="n", largura=IW)
                y += px(24)
            if self.estado == "instalando":
                ui.fundo(P, y, IW, px(46), px(9), T["btn"], None, G)
                ui.tx(W // 2, y + px(23), "Instalando…", 14, T["texto2"], G, peso="bold")
            else:
                ui.botao_rotulo(P, y, IW, px(46), "Atualizar" if self.ja_instalado else "Instalar",
                                "download", self.instalar, G)
            y += px(46)
            if self.erro:
                t = ui.tx(W // 2, y + px(12), self.erro, 11, T["vermelho"], G, anchor="n",
                          largura=IW)
                y = c.bbox(t)[3]
        y += px(18)
        c.create_line(P, y, W - P, y, fill=T["card_borda"], tags=G)
        y += px(12)
        ui.tx(W // 2, y, f"Versão {app.VERSAO_APP}   •   Desenvolvido por {app.AUTOR}", 11,
              T["apagado"], G, anchor="n")
        y += px(16)
        c.config(width=W, height=y + P)

    def alternar_auto(self):
        self.auto = not self.auto
        self.desenhar()

    def alternar_desktop(self):
        self.desktop = not self.desktop
        self.desenhar()

    def instalar(self):
        self.estado, self.erro = "instalando", ""
        self.desenhar()
        self.root.update()
        try:
            self.destino = instalar(self.desktop, self.auto)
            self.estado = "ok"
        except Exception as ex:
            self.estado, self.erro = "inicio", f"Não foi possível instalar: {ex}"
        self.desenhar()

    def abrir_e_sair(self):
        try:
            subprocess.Popen([self.destino], cwd=os.path.dirname(self.destino), env=env_limpo(),
                             creationflags=DESANEXADO, close_fds=True)
        except Exception:
            pass
        self.root.destroy()

    def executar(self):
        self.root.mainloop()


if __name__ == "__main__":
    Instalador().executar()
