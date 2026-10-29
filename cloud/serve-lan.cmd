@echo off
REM 局域网试玩：双击启动云端多人版（Windows）
REM 用法：双击本文件 → 记下窗口里打印的端口 → 手机在同一 Wi-Fi 下访问 http://<本机IP>:8090/
setlocal

set PORT=8090
set REGISTER_CODE=lobby-2026
set DATA_DIR=%~dp0data
set RATE_LIMIT_PER_MIN=30

cd /d "%~dp0"
if not exist "node_modules\ws" (
  echo [1/2] 首次运行，安装依赖 ws ...
  call npm install --no-audit --no-fund
)
echo.
echo 本机可用地址：
echo   单机版：   http://127.0.0.1:%PORT%/
echo   多人版：   http://127.0.0.1:%PORT%/play?t=^<token^>
echo 手机请把 127.0.0.1 换成本机局域网 IP（用 ipconfig 查）。
echo 注册口令：%REGISTER_CODE%
echo.
echo [2/2] 启动服务（Ctrl+C 停止）...
node server\index.js

endlocal
