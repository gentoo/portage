#!/usr/bin/env bash
# Maintainer: Oskari Pirhonen <xxc3ncoredxx@gmail.com>

set -ex

install_versions=( "${@/#/python}" )

sudo apt-get install -y --no-install-recommends \
    python-is-python3 \
    "${install_versions[@]}" \
    "${install_versions[@]/%/-venv}"

for py in "${@}"; do
  "python$py" -m venv ".venv-$py"
  source ".venv-$py/bin/activate"
  pip install --upgrade pip
  deactivate
done

python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
deactivate
