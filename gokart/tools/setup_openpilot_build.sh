#!/bin/bash
# Build openpilot cereal + modeld on Jetson Orin NX (Python 3.8)
set -e

OP_V3="/home/jetson/openpilotV3_gokart"
OP_BUILD="/home/jetson/openpilot-build"
# use v0.9.4 which is the last version supporting python 3.8
OP_TAG="v0.9.4"

echo "=== Openpilot Build ($OP_TAG) for Jetson Orin NX ==="

# Step 1: System deps
echo "[1/6] Installing dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq git git-lfs build-essential clang llvm \
  python3-dev python3-pip python3-venv libcapnp-dev capnproto \
  libzmq3-dev libssl-dev libffi-dev opencl-headers ocl-icd-opencl-dev \
  libavformat-dev libavcodec-dev libavutil-dev libswscale-dev cmake scons 2>&1 | tail -3
git lfs install

# Step 2: Clone
echo "[2/6] Cloning openpilot $OP_TAG..."
if [ -d "$OP_BUILD" ]; then
  echo "  Already exists, checking out $OP_TAG..."
  cd "$OP_BUILD"
  git fetch --tags 2>/dev/null || true
  git checkout "$OP_TAG" 2>/dev/null || true
  git submodule update --init --recursive 2>/dev/null || true
else
  git clone --recurse-submodules --branch "$OP_TAG" --depth 1 https://github.com/commaai/openpilot.git "$OP_BUILD"
  cd "$OP_BUILD"
fi

# Step 3: LFS
echo "[3/6] Pulling model files..."
git lfs pull

# Step 4: Python env
echo "[4/6] Python environment..."
if [ ! -d "$OP_BUILD/.venv" ]; then
  python3 -m venv "$OP_BUILD/.venv"
fi
source "$OP_BUILD/.venv/bin/activate"
pip install --upgrade pip setuptools wheel -q
pip install scons cython numpy pycapnp pyzmq onnx cffi -q

if [ -d "$OP_BUILD/tinygrad_repo" ] && [ "$(ls -A $OP_BUILD/tinygrad_repo)" ]; then
  pip install -e "$OP_BUILD/tinygrad_repo" -q
fi

# Step 5: Build
echo "[5/6] Building cereal + msgq + modeld..."
cd "$OP_BUILD"
export ARCH=aarch64

scons -j4 cereal/ msgq/ selfdrive/modeld/ 2>&1 | tail -20 || {
  echo "scons failed, trying cereal only..."
  scons -j4 cereal/ msgq/ 2>&1 | tail -20
}

echo "[5/6] Build done."

# Step 6: Copy artifacts
echo "[6/6] Copying to $OP_V3..."
mkdir -p "$OP_V3/selfdrive/modeld/models" "$OP_V3/cereal/gen"

for f in "$OP_BUILD"/selfdrive/modeld/models/*.onnx; do
  [ -f "$f" ] && [ $(stat -c%s "$f") -gt 1000 ] && cp "$f" "$OP_V3/selfdrive/modeld/models/" && echo "  Copied: $(basename $f)"
done

for f in "$OP_BUILD"/selfdrive/modeld/models/*.pkl; do
  [ -f "$f" ] && cp "$f" "$OP_V3/selfdrive/modeld/models/" && echo "  Copied: $(basename $f)"
done

[ -d "$OP_BUILD/cereal/gen" ] && cp -r "$OP_BUILD/cereal/gen" "$OP_V3/cereal/" && echo "  Copied: cereal/gen/"

# Copy cereal python module
if [ -d "$OP_BUILD/cereal" ]; then
  cp -r "$OP_BUILD/cereal"/*.py "$OP_V3/cereal/" 2>/dev/null || true
  cp -r "$OP_BUILD/cereal"/*.capnp "$OP_V3/cereal/" 2>/dev/null || true
fi
if [ -d "$OP_BUILD/msgq" ]; then
  cp -r "$OP_BUILD/msgq"/*.py "$OP_V3/msgq/" 2>/dev/null || true
  cp -r "$OP_BUILD/msgq"/*.so "$OP_V3/msgq/" 2>/dev/null || true
fi

echo ""
echo "=== BUILD COMPLETE ==="
echo "Artifacts copied to $OP_V3"
