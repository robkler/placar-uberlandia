#!/usr/bin/env bash
# Atualiza os dados do Placar (Uberlândia + Câmara dos Deputados).
#
#   ./atualizar.sh                  coleta tudo e gera public/data.json e public/federal.json
#   ./atualizar.sh --publicar       faz o mesmo e publica na Vercel (produção)
#   ./atualizar.sh --so-uberlandia  só a parte de Uberlândia (~1 min)
#   ./atualizar.sh --so-federal     só a Câmara dos Deputados (~5 a 10 min)
#   ./atualizar.sh --tse            também recoleta dados do TSE (só após eleições / troca de parlamentar)
#   ./atualizar.sh --forcar         grava os arquivos mesmo se a checagem de segurança reclamar
#
# Para ver o site no seu computador:  ./ver.sh
set -euo pipefail
cd "$(dirname "$0")"

PUBLICAR=0; TSE=0; FORCAR=""; UDI=1; FED=1
for a in "$@"; do
  case "$a" in
    --publicar) PUBLICAR=1 ;;
    --tse) TSE=1 ;;
    --forcar) FORCAR="--forcar" ;;
    --so-uberlandia) FED=0 ;;
    --so-federal) UDI=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $a (use --help)"; exit 2 ;;
  esac
done

command -v python3 >/dev/null || { echo "Precisa do python3 instalado."; exit 1; }

inicio=$(date +%s)
falhou=0
if [ "$UDI" = 1 ]; then
  python3 scripts/coletar_camara.py
  python3 scripts/coletar_tesouro.py
  if [ "$TSE" = 1 ]; then python3 scripts/coletar_tse.py; fi
  python3 scripts/gerar_dados.py $FORCAR || falhou=1
fi
if [ "$FED" = 1 ]; then
  python3 scripts/coletar_federal.py
  if [ "$TSE" = 1 ]; then python3 scripts/coletar_tse_federal.py; fi
  python3 scripts/gerar_federal.py $FORCAR || falhou=1
fi
echo "Concluído em $(( $(date +%s) - inicio ))s."

if [ "$falhou" = 1 ]; then
  echo "Alguma checagem de segurança falhou (veja acima). O site não foi publicado."
  exit 1
fi
if [ "$PUBLICAR" = 1 ]; then
  if command -v vercel >/dev/null; then vercel deploy --prod --yes
  else npx --yes vercel@latest deploy --prod --yes; fi
fi
