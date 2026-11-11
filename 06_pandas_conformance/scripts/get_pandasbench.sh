#!/usr/bin/env bash
# Fetch PandasBench (code + notebooks) at a pinned commit and its data archive.
#
# Sources (both named in PandasBench's README, which plan.md Section 5 names):
#   code : https://github.com/ADAPT-uiuc/PandasBench  (Apache-2.0), pinned commit below
#   data : Google Drive file 1WUX-gUycsXVngCaaoDecLdjAv7hjSoeR ("data.zip", ~11 GB), via gdown
#          (the README's Box mirror returned HTTP 404 on 2026-10-02).
# Fallback (plan.md Section 5, only if Drive fails by the day-3 gate): the PandasBench Docker
# image used ONLY as a data source (docker pull/create/cp/rm/rmi) -- not automated here.
#
# Everything lands under 06_pandas_conformance/data/ ; provenance is written to
# data/provenance.json by scripts/provenance.py. The script is idempotent: finished steps
# are skipped (marker files), a partially downloaded zip is resumed by gdown --continue.
#
# Memory: git clone, gdown and unzip stay far below 1 GB RSS, so this runs without the
# memory guard (and without holding the cross-project experiment lock for ~30 minutes).
set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.venv/bin/python}"
COMMIT="ae70611671b0200c325581cb717e84249763fce6"
REPO_URL="https://github.com/ADAPT-uiuc/PandasBench"
DRIVE_ID="1WUX-gUycsXVngCaaoDecLdjAv7hjSoeR"
DATA="$PROJ/data"
RAW="$DATA/raw"
mkdir -p "$RAW"

step() { echo "[get_pandasbench $(date -u +%H:%M:%S)] $*"; }

# 1. repository at the pinned commit
if [ ! -d "$DATA/PandasBench/.git" ] && [ ! -f "$DATA/PandasBench/.artifact_commit" ]; then
  step "cloning $REPO_URL"
  git clone --quiet "$REPO_URL" "$DATA/PandasBench.tmp"
  git -C "$DATA/PandasBench.tmp" checkout --quiet "$COMMIT"
  mv "$DATA/PandasBench.tmp" "$DATA/PandasBench"
fi
HEAD_COMMIT="$(if [ -f "$DATA/PandasBench/.artifact_commit" ]; then cat "$DATA/PandasBench/.artifact_commit"; else git -C "$DATA/PandasBench" rev-parse HEAD; fi)"
if [ "$HEAD_COMMIT" != "$COMMIT" ]; then
  step "checking out pinned commit $COMMIT"
  git -C "$DATA/PandasBench" fetch --quiet origin
  git -C "$DATA/PandasBench" checkout --quiet "$COMMIT"
fi
step "repo at $HEAD_COMMIT"

# 2. data archive (resumable)
ZIP="$RAW/PandasBench_data.zip"
if [ ! -f "$RAW/.download_done" ]; then
  step "downloading data archive from Google Drive id $DRIVE_ID (about 11 GB)"
  "$PY" -m gdown --continue "$DRIVE_ID" -O "$ZIP"
  touch "$RAW/.download_done"
fi

# 3. checksum (cached)
if [ ! -f "$RAW/PandasBench_data.zip.sha256" ]; then
  step "sha256 of archive"
  shasum -a 256 "$ZIP" | awk '{print $1}' > "$RAW/PandasBench_data.zip.sha256"
fi

# 4. unzip into data/raw/PandasBench_data (the archive's own top-level directory)
if [ ! -f "$RAW/.unzip_done" ]; then
  step "unzipping"
  rm -rf "$RAW/unzip.tmp"
  mkdir -p "$RAW/unzip.tmp"
  unzip -q "$ZIP" -d "$RAW/unzip.tmp"
  # the archive contains one top-level directory (data/ or PandasBench_data/)
  TOP="$(ls "$RAW/unzip.tmp" | head -1)"
  rm -rf "$RAW/PandasBench_data"
  mv "$RAW/unzip.tmp/$TOP" "$RAW/PandasBench_data"
  rmdir "$RAW/unzip.tmp" 2>/dev/null || true
  touch "$RAW/.unzip_done"
fi

# 5. provenance (url, sha256, license, retrieval date, per-file manifest)
step "writing provenance"
"$PY" "$PROJ/scripts/provenance.py" --data "$DATA" --commit "$COMMIT" --repo "$REPO_URL" --drive-id "$DRIVE_ID"
step "done"

if [ -f "$ZIP" ]; then
  EXPECTED="$(cat "$RAW/PandasBench_data.zip.sha256" | awk '{print $1}')"
  ACTUAL="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
  [ "$EXPECTED" = "$ACTUAL" ] || { echo "Input archive checksum mismatch" >&2; exit 3; }
fi
