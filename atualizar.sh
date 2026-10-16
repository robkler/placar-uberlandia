#!/usr/bin/env bash
# Atualiza os dados do Placar de Uberlândia.
#
#   ./atualizar.sh              coleta Câmara + Tesouro e gera public/data.json
#   ./atualizar.sh --publicar   faz o mesmo e publica na Vercel (produção)
#   ./atualizar.sh --tse        também recoleta dados do TSE (só após eleições / troca de vereador)
#   ./atualizar.sh --forcar     grava o data.json mesmo se a checagem de segurança reclamar
#
# Para ver o site no seu computador:  ./ver.sh
set -euo pipefail
cd "$(dirname "$0")"

PUBLICAR=0; TSE=0; FORCAR=""
for a in "$@"; do
  case "$a" in
    --publicar) PUBLICAR=1 ;;
    --tse) TSE=1 ;;
    --forcar) FORCAR="--forcar" ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $a (use --help)"; exit 2 ;;
  esac
done

command -v python3 >/dev/null || { echo "Precisa do python3 instalado."; exit 1; }

inicio=$(date +%s)
python3 scripts/coletar_camara.py
python3 scripts/coletar_tesouro.py
if [ "$TSE" = 1 ]; then python3 scripts/coletar_tse.py; fi
python3 scripts/gerar_dados.py $FORCAR
echo "Dados prontos em $(( $(date +%s) - inicio ))s."

if [ "$PUBLICAR" = 1 ]; then
  if command -v vercel >/dev/null; then vercel deploy --prod --yes
  else npx --yes vercel@latest deploy --prod --yes; fi
fi
