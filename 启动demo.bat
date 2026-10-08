@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title 股析 Demo - 启动器
echo ============================================================
echo      股析 · AI 投研委员会   Demo 启动器
echo ============================================================
echo.
echo [1/3] 安装/检查依赖（首次约 1-2 分钟，之后很快）...
python -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo.
echo [2/3] 准备行情数据（自动选择可用数据源）...
python build_data.py
echo.
echo [3/3] 启动本地网页，浏览器会自动打开...
echo.
python app.py
echo.
echo 服务已停止。
pause
exit /b 0

:fail
echo.
echo [X] 依赖安装失败。请确认：电脑能上网、已安装 Python。
echo     可在命令行执行  python --version  检查。
pause
exit /b 1
