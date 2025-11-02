@echo off
set PORT=%1
if "%PORT%"=="" set PORT=8001

set TEMPLATE_MATCH_TIMEOUT=300

echo Starting server on port %PORT%...
uvicorn server.main_inference:app --host 0.0.0.0 --port %PORT%
