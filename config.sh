SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

export PATH=${PATH}:${SCRIPT_DIR}/node_modules/.bin
. src/main/cdk/.venv/bin/activate