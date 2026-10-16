#!/usr/bin/env bash
# Abre o site localmente em http://localhost:8000 (Ctrl+C para parar)
cd "$(dirname "$0")/public"
echo "Abrindo http://localhost:8000"
( sleep 1; open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null ) &
python3 -m http.server 8000
