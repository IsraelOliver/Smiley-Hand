#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi

# Não compila dependências localmente e não altera pacotes globais.
# O dry-run verifica a resolução completa para o Python/arquitetura em uso.
.venv/bin/python -m pip install --dry-run --only-binary=:all: --no-cache-dir --retries 0 --timeout 20 -r requirements.txt
.venv/bin/python -m pip install --only-binary=:all: --no-cache-dir --retries 0 --timeout 20 -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m hand_control --download-model
printf '%s\n' 'Pronto. Execute: .venv/bin/python -m hand_control'
