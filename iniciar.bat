@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Baixador de Videos - Preparando ambiente

set "VENV=.venv"
set "PY="

where python >nul 2>&1 && set "PY=python"
if not defined PY (
    where py >nul 2>&1 && set "PY=py"
)
if not defined PY (
    echo [ERRO] Python nao encontrado. Instale em https://www.python.org/downloads/
    echo        e marque a opcao "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

REM 1) Cria a maquina virtual (venv) se nao existir
if not exist "%VENV%\Scripts\python.exe" (
    echo Criando ambiente virtual...
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

REM 2) Instala as dependencias (apenas na primeira vez)
if not exist "%VENV%\.deps_ok" (
    echo Instalando dependencias, aguarde...
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar as dependencias.
        pause
        exit /b 1
    )
    echo ok> "%VENV%\.deps_ok"
)

REM 3) Abre o programa (pythonw = sem janela de console)
start "" "%VENV%\Scripts\pythonw.exe" app.py
exit /b 0
