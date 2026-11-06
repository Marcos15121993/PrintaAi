@echo off
rem Gera o programa (dist\PrintaAi.exe) e o instalador (Instalar_PrintaAi.exe) nesta pasta.
rem Requer: py -m pip install pillow pyinstaller
cd /d "%~dp0"

echo [1/2] Gerando o programa...
py -m PyInstaller --noconfirm --onefile --windowed --name PrintaAi --icon "%~dp0build\printaai.ico" ^
  --distpath "%~dp0dist" --workpath "%~dp0build\work" --specpath "%~dp0build" "%~dp0Printsc.py" || goto erro

echo [2/2] Gerando o instalador...
py -m PyInstaller --noconfirm --onefile --windowed --name Instalar_PrintaAi --icon "%~dp0build\printaai.ico" ^
  --add-data "%~dp0dist\PrintaAi.exe;." ^
  --distpath "%~dp0." --workpath "%~dp0build\work_inst" --specpath "%~dp0build" "%~dp0instalador.py" || goto erro

echo.
echo Pronto! Envie o arquivo: %~dp0Instalar_PrintaAi.exe
goto :eof

:erro
echo.
echo ERRO ao gerar. Veja as mensagens acima.
exit /b 1
