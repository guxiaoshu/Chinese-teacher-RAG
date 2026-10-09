@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
set PYTHONUTF8=1
cd /d "%~dp0"
title 语文教学 RAG 助手 - 一键安装启动

echo.
echo  ==========================================================
echo     语文教学 RAG 助手 · 一键安装启动
echo     双击这个文件就行，不需要懂任何命令
echo     第一次要装依赖 + 下模型（约 400MB），可能 10~20 分钟
echo  ==========================================================
echo.

REM ============ 1/5 找 Python ============
set "PY=python"
%PY% --version >nul 2>nul
if not errorlevel 1 goto :pyok
set "PY=py -3"
%PY% --version >nul 2>nul
if not errorlevel 1 goto :pyok
set "PY=py"
%PY% --version >nul 2>nul
if not errorlevel 1 goto :pyok
goto :nopython

:pyok
echo [1/5] 找到 Python：
%PY% --version
echo.

REM ============ 2/5 装依赖（带完成标记，装过就跳过）============
if exist "_setup_ok.txt" (
    echo [2/5] 依赖之前已装好，跳过（要重装就删掉 _setup_ok.txt 再双击）
) else (
    echo [2/5] 准备虚拟环境 + 安装依赖（torch 比较大，耐心等，别关）...
    if exist ".venv" rmdir /s /q ".venv"
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :fail
    type nul > "_setup_ok.txt"
)
echo.

REM ============ 3/5 下模型（已有就秒跳过）============
echo [3/5] 检查向量模型（约 400MB，只下这一次）...
".venv\Scripts\python.exe" "scripts\download_model.py"
echo.

REM ============ 4/5 配 key ============
set "NEEDKEY="
if not exist ".env" set "NEEDKEY=1"
if exist ".env" findstr /c:"DEEPSEEK_API_KEY=sk-" ".env" >nul 2>nul || set "NEEDKEY=1"
if defined NEEDKEY (
    echo [4/5] 没检测到有效的 DeepSeek API key。
    set "APIKEY="
    set /p "APIKEY=       请粘贴你的 key（sk- 开头，别带引号）然后回车： "
    (
        echo # DeepSeek API key
        echo DEEPSEEK_API_KEY=!APIKEY!
    ) > ".env"
    echo        [OK] 已写入 .env
) else (
    echo [4/5] API key 已就绪
)
echo.

REM ============ 5/5 启动 ============
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    (
        echo [general]
        echo email = "user@example.com"
    ) > "%USERPROFILE%\.streamlit\credentials.toml"
)

echo [5/5] 启动中，浏览器会自动打开 http://localhost:8501
echo        第一次启动要加载本地模型 + 预热，约 1 分钟，别关窗口
echo        看到网页左侧绿色「DeepSeek API 已就绪」就成功了
echo.
".venv\Scripts\python.exe" -m streamlit run "app\streamlit_app.py"
echo.
echo  Streamlit 已退出。如果上面有红字报错，截图发给我。
pause
goto :eof

:nopython
echo.
echo  ==========================================================
echo   [×] 没找到 Python，请按下面装一下，再重新双击本文件：
echo.
echo      1) 浏览器打开 https://www.python.org/downloads/
echo      2) 下载 Python 3.11 或 3.12 的 Windows 版
echo      3) 双击安装，第一屏最下面务必勾选「Add Python to PATH」
echo      4) 一路 Install Now / Next 装到底
echo      5) 回到这里，重新双击 setup.bat
echo  ==========================================================
echo.
pause
exit /b 1

:fail
echo.
echo  ==========================================================
echo   [×] 中途出错了，请把上面这段红字截图发给我。
echo      常见原因：网络断了 / 杀毒软件拦截 / 磁盘空间不足
echo  ==========================================================
echo.
pause
exit /b 1
