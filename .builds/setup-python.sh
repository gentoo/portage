#!/usr/bin/env bash
# Maintainer: Oskari Pirhonen <xxc3ncoredxx@gmail.com>

set -ex

install_versions=( "${@/#/python}" )
# Fix any pypy versions
install_versions=( "${install_versions[@]/#pythonpypy/pypy}" )

sudo apt-get install -y --no-install-recommends \
        python-is-python3 \
        python3-dev \
        python3-venv \
        "${install_versions[@]}" \
        "${install_versions[@]/%/-dev}" \
        "${install_versions[@]/%/-venv}"

for py in "$@"; do
    if [[ "$py" != pypy* ]]; then
        "python$py" -m venv ".venv-$py"
    else
        "$py" -m venv ".venv-$py"
    fi
    source ".venv-$py/bin/activate"
    pip install --upgrade pip
    deactivate
done

python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
deactivate
