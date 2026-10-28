@echo off
REM 深圳海岸小世界 —— 本地启动脚本
REM 双击本文件即可：启动本地静态服务器并打开浏览器。
cd /d "%~dp0"
echo 服务地址: http://127.0.0.1:8099/
echo 关闭本窗口即可停止服务。
start "" "http://127.0.0.1:8099/index.html"
python -m http.server 8099 --bind 127.0.0.1
