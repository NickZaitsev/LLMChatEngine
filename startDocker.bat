@echo off
echo.
echo =========================================
echo   AI Girlfriend Bot - Docker Startup
echo =========================================
echo.

REM Function to check if Docker is running
:check_docker
echo 🔍 Checking Docker status...
docker version > docker_temp.txt 2>&1
if %errorlevel% equ 0 (
    del docker_temp.txt 2>nul
    echo ✅ Docker is running
    goto docker_ready
)
del docker_temp.txt 2>nul

echo 🔍 Docker is not running, attempting to start Docker Desktop...

REM Try to find and start Docker Desktop
set DOCKER_FOUND=0
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    echo 🚀 Found Docker Desktop in Program Files, starting quietly...
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" --quiet
    set DOCKER_FOUND=1
    goto wait_for_docker
)

if exist "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe" (
    echo 🚀 Found Docker Desktop in Program Files (x86), starting quietly...
    start "" "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe" --quiet
    set DOCKER_FOUND=1
    goto wait_for_docker
)

REM Check user's AppData for Docker Desktop
if exist "%LOCALAPPDATA%\Programs\Docker\Docker Desktop.exe" (
    echo 🚀 Found Docker Desktop in user's AppData, starting quietly...
    start "" "%LOCALAPPDATA%\Programs\Docker\Docker Desktop.exe" --quiet
    set DOCKER_FOUND=1
    goto wait_for_docker
)

REM Try to start Docker Desktop using PowerShell
echo 🔍 Trying to start Docker Desktop from Start Menu quietly...
powershell -Command "try { Start-Process 'Docker Desktop' -ArgumentList '--quiet' -ErrorAction Stop; exit 0 } catch { exit 1 }" > ps_temp.txt 2>&1
if %errorlevel% equ 0 (
    del ps_temp.txt 2>nul
    set DOCKER_FOUND=1
    goto wait_for_docker
)
del ps_temp.txt 2>nul

REM If all methods failed
if %DOCKER_FOUND% equ 0 (
    echo ❌ Error: Could not find or start Docker Desktop!
    echo.
    echo Please ensure Docker Desktop is installed and try one of these:
    echo   1. Start Docker Desktop manually
    echo   2. Install Docker Desktop from https://www.docker.com/products/docker-desktop
    echo   3. Add Docker Desktop to your system PATH
    echo.
    pause
    exit /b 1
)

:wait_for_docker
echo ⏳ Waiting for Docker Desktop to start up...
set /a WAIT_COUNT=0
set /a MAX_WAIT=60

:wait_loop
timeout /t 2 /nobreak >nul
set /a WAIT_COUNT+=2
docker version > docker_temp.txt 2>&1
if %errorlevel% equ 0 (
    del docker_temp.txt 2>nul
    echo ✅ Docker is now running!
    goto docker_ready
)
del docker_temp.txt 2>nul

if %WAIT_COUNT% geq %MAX_WAIT% (
    echo ❌ Timeout: Docker Desktop took too long to start
    echo Please check if Docker Desktop is starting properly
    echo.
    pause
    exit /b 1
)

echo ⏳ Still waiting... (%WAIT_COUNT%/%MAX_WAIT%s)
goto wait_loop

:docker_ready

REM Check if .env file exists
if not exist ".env" (
    echo ❌ Error: .env file not found!
    echo Please copy env_example.txt to .env and configure it.
    echo.
    pause
    exit /b 1
)

echo ✅ Docker is running
echo ✅ Environment file found
echo.

echo 🔍 Checking current containers...
docker-compose ps

echo.
echo 🚀 Starting AI Girlfriend Bot with PostgreSQL...
echo.

REM Stop existing containers first
echo 📦 Stopping any existing containers...
docker-compose down

echo.
echo 📦 Building and starting services...
docker-compose up -d --build

REM Wait a moment for services to start
timeout /t 5 /nobreak >nul

echo.
echo 📊 Container Status:
docker-compose ps

echo.
echo 🔍 Checking PostgreSQL health...
timeout /t 3 /nobreak >nul
docker-compose exec -T postgres pg_isready -U ai_bot -d ai_bot > pg_temp.txt 2>&1
if %errorlevel% equ 0 (
    del pg_temp.txt 2>nul
    echo ✅ PostgreSQL is ready
) else (
    del pg_temp.txt 2>nul
    echo ⚠️ PostgreSQL may still be starting up...
)

echo.
echo 📋 Useful Commands:
echo   View logs:           docker-compose logs -f
echo   View bot logs:       docker-compose logs -f ai-girlfriend-bot
echo   View postgres logs:  docker-compose logs -f postgres
echo   Stop services:       docker-compose down
echo   Restart bot:         docker-compose restart ai-girlfriend-bot
echo   Run tests:           docker-compose exec ai-girlfriend-bot python tests/test_postgres_storage.py
echo.

echo 🎉 AI Girlfriend Bot is starting with PostgreSQL!
echo.
echo 📝 Check logs with: docker-compose logs -f
echo 🛑 Stop with: docker-compose down
echo.

REM Ask if user wants to see logs
set /p "choice=Would you like to view the logs now? (y/n): "
if /i "%choice%"=="y" (
    echo.
    echo 📋 Showing live logs (Press Ctrl+C to exit logs view)...
    echo.
    start cmd /k "docker-compose logs -f"
)

echo.
echo ✨ Docker startup complete!
pause