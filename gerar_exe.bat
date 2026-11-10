@echo off
rem Gera o programa (dist\PrintaAi.exe) e o instalador (Instalar_PrintaAi.exe) nesta pasta.
rem Requer: py -m pip install pillow pyinstaller
rem A versão e o autor vêm de VERSAO_APP e AUTOR no Printsc.py.
cd /d "%~dp0"

echo [0/2] Gerando dados de versao...
py "%~dp0gerar_versao.py" "%~dp0build" || goto erro

echo [1/2] Gerando o programa...
py -m PyInstaller --noconfirm --onefile --windowed --noupx --name PrintaAi --icon "%~dp0build\printaai.ico" ^
  --version-file "%~dp0build\versao_app.txt" ^
  --distpath "%~dp0dist" --workpath "%~dp0build\work" --specpath "%~dp0build" "%~dp0Printsc.py" || goto erro

echo [2/2] Gerando o instalador...
py -m PyInstaller --noconfirm --onefile --windowed --noupx --name Instalar_PrintaAi --icon "%~dp0build\printaai.ico" ^
  --version-file "%~dp0build\versao_instalador.txt" ^
  --add-data "%~dp0dist\PrintaAi.exe;." ^
  --distpath "%~dp0." --workpath "%~dp0build\work_inst" --specpath "%~dp0build" "%~dp0instalador.py" || goto erro

echo.
echo Pronto! Envie o arquivo: %~dp0Instalar_PrintaAi.exe
goto :eof

:erro
echo.
echo ERRO ao gerar. Veja as mensagens acima.
exit /b 1
