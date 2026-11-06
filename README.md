# Captura de Tela

Programa em Python para capturar a tela no Windows, no estilo Lightshot: ao apertar **PrtSc**, a tela congela, você seleciona a área e uma barra de ferramentas aparece ao lado da seleção para marcar, salvar ou copiar a imagem para colar em chats.

**Principais recursos**

- Atalho global **PrtSc**: funciona em qualquer janela, com o programa minimizado.
- Seleção de área com alças para ajustar o tamanho, mostrando as dimensões em pixels.
- Marcações: **caneta (mão livre)**, **linha**, **seta**, **retângulo**, **círculo** e **texto**.
- Escolha de cor (paleta pronta ou cor personalizada) e 3 espessuras.
- **Desfazer** de qualquer marcação.
- **Salvar** em PNG, JPG ou BMP, ou **copiar** para a área de transferência e colar (Ctrl+V) em WhatsApp, Discord, Teams, e-mail etc.
- Suporte a vários monitores e a telas com escala de DPI (125%, 150%...).

![Pré-visualização da interface](preview.png)

## Requisitos

- Python 3.8 ou superior (com tkinter, que já vem na instalação padrão do Windows)
- [Pillow](https://pypi.org/project/pillow/)

```
python -m pip install pillow
```

## Como usar

```
python Printsc.py
```

1. Deixe a janelinha do programa aberta e pode minimizá-la.
2. Aperte **PrtSc**: a tela congela e escurece.
3. Arraste para escolher a área. Dá para ajustar pelas alças nas bordas.
4. Use a barra de ferramentas ao lado para marcar a imagem.
5. Copie (**Enter** ou **Ctrl+C**) ou salve (**Ctrl+S**).

Para rodar sem a janela do terminal e já iniciar minimizado:

```
pythonw.exe Printsc.py --minimizado
```

Para iniciar junto com o Windows, coloque um atalho desse comando na pasta `shell:startup`.

## Atalhos

| Atalho | Ação |
| --- | --- |
| `PrtSc` | Iniciar uma captura |
| `Enter` / `Ctrl+C` | Copiar a imagem e fechar |
| `Ctrl+S` | Salvar em arquivo |
| `Ctrl+Z` | Desfazer a última marcação |
| `Esc` | Cancelar |

## Observações

- O programa intercepta a tecla PrtSc antes do Windows, então a Ferramenta de Captura não abre junto. Se a tecla não responder, desative em *Configurações > Acessibilidade > Teclado > "Usar o botão Print Screen para abrir a captura de tela"*.
- O atalho global funciona somente no Windows. Em Linux e macOS, use o botão **Capturar agora** da janela principal (no Linux, copiar para a área de transferência exige `xclip` ou `wl-clipboard`).
- Alt+PrtSc e Win+PrtSc continuam com o comportamento normal do Windows.
