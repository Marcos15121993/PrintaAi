"""Gera os arquivos de versão do Windows (Propriedades › Detalhes) usados pelo PyInstaller.

Lê VERSAO_APP e AUTOR do Printsc.py, para que a versão fique sempre sincronizada.
Uso: py gerar_versao.py <pasta_destino>
"""
import ast
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def ler_constantes():
    with open(os.path.join(AQUI, "Printsc.py"), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    valores = {}
    for no in arvore.body:
        if isinstance(no, ast.Assign) and len(no.targets) == 1:
            alvo = no.targets[0]
            if isinstance(alvo, ast.Name) and alvo.id in ("VERSAO_APP", "AUTOR", "NOME_APP"):
                valores[alvo.id] = ast.literal_eval(no.value)
    return valores


MODELO = """# Gerado por gerar_versao.py — não edite à mão.
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tupla}, prodvers={tupla}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', {autor!r}),
      StringStruct('FileDescription', {descricao!r}),
      StringStruct('FileVersion', {versao!r}),
      StringStruct('InternalName', {interno!r}),
      StringStruct('LegalCopyright', {copyright!r}),
      StringStruct('OriginalFilename', {arquivo!r}),
      StringStruct('ProductName', {produto!r}),
      StringStruct('ProductVersion', {versao!r})])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])
  ]
)
"""


def main():
    destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, "build")
    os.makedirs(destino, exist_ok=True)
    c = ler_constantes()
    versao = c["VERSAO_APP"]
    partes = [int(p) for p in versao.split(".")[:4] if p.isdigit()]
    tupla = tuple((partes + [0, 0, 0, 0])[:4])
    produto = c.get("NOME_APP", "PrintaAí")
    autor = c["AUTOR"]
    arquivos = {
        "versao_app.txt": ("PrintaAi", "PrintaAi.exe", f"{produto} — captura de tela com anotações"),
        "versao_instalador.txt": ("Instalar_PrintaAi", "Instalar_PrintaAi.exe", f"Instalador do {produto}"),
    }
    for nome, (interno, arquivo, descricao) in arquivos.items():
        texto = MODELO.format(tupla=tupla, autor=autor, descricao=descricao, versao=versao,
                              interno=interno, copyright=f"© {autor}", arquivo=arquivo,
                              produto=produto)
        with open(os.path.join(destino, nome), "w", encoding="utf-8") as f:
            f.write(texto)
    print(f"Versão {versao} ({autor}) gravada em {destino}")


if __name__ == "__main__":
    main()
