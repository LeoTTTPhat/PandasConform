#!/bin/bash
# Read-only post-processing of one campaign step (light; reads JSON records and a sample of blobs):
#   bash 06_pandas_conformance/scripts/post_campaign.sh <campaign> <set> '<engines incl. ref,ref#2>' [scale]
set -u
cd $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
export PYTHONPATH=06_pandas_conformance/src
PY=.venv/bin/python
C="$1"; S="$2"; E="$3"; SC="${4:-1.0}"
$PY -m pconf.orchestrate summarize --campaign "$C"
$PY 06_pandas_conformance/scripts/check_campaign.py --campaign "$C" --set "$S" --engines "$E" --ref2 'ref#2' --scale "$SC"
$PY 06_pandas_conformance/scripts/analyze_campaign.py --campaign "$C"
$PY 06_pandas_conformance/scripts/campaign_metrics.py --campaign "$C"
$PY 06_pandas_conformance/scripts/write_environment.py --campaign "$C"
