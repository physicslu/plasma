#!/usr/bin/env bash
#
# Plasma FPGA development environment setup
#
# Usage:
#   cd /storage/projects/plasma
#   source pl/env.sh
#
# This script must be sourced so that venv activation and PATH changes affect
# the current shell.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: This script must be sourced."
    echo "Use:"
    echo "  source pl/env.sh"
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

FPGA_VENV="${REPO_ROOT}/pl/.venv"
VERILATOR_ROOT="/storage/tools/verilator/5.050"

if [[ ! -f "${FPGA_VENV}/bin/activate" ]]; then
    echo "ERROR: FPGA Python venv not found:"
    echo "  ${FPGA_VENV}"
    return 1
fi

if [[ ! -x "${VERILATOR_ROOT}/bin/verilator" ]]; then
    echo "ERROR: Verilator not found:"
    echo "  ${VERILATOR_ROOT}/bin/verilator"
    return 1
fi

cd "${REPO_ROOT}" || return 1

source "${FPGA_VENV}/bin/activate"
export PATH="${VERILATOR_ROOT}/bin:${PATH}"

echo
echo "=== Plasma FPGA Development Environment ==="
echo "Repository : ${REPO_ROOT}"
echo

echo "=== Python ==="
which python
python --version
echo

echo "=== Verilator ==="
which verilator
verilator --version
echo

echo "=== Git Status ==="
git status -sb
echo

echo "Environment ready."
