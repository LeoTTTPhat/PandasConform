#!/bin/bash
# conf_1x and drift campaigns (plan Section 6) as a sequence of driver steps. Each driver step is a
# series of memory-guarded invocations of at most ~88 min (--deadline 4500 --hard-budget 5300);
# rerunning this script resumes (completed fingerprints are skipped; pilot records with identical
# fingerprints are adopted via --reuse-from). Not itself guarded: it only launches guarded steps.
#   bash 06_pandas_conformance/scripts/conf1x_drift_chain.sh   (from $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd))
set -u
cd $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
D="python3 06_pandas_conformance/scripts/campaign_driver.py"
B="--deadline 4500 --hard-budget 5300"
$D --name experiment_conf1x_single --max-iters 12 -- run --campaign conf_1x --set all --engines 'ref,ref#2,pyarrow_backend' --reuse-from pilot $B
$D --name experiment_drift_run --max-iters 12 -- run --campaign drift --set all --engines 'ref,ref#2,p15,p30' --reuse-from conf_1x,pilot $B
$D --name experiment_drift_compare --max-iters 4 -- compare --campaign drift --set all --engines 'ref#2,p15,p30' --ref2 'ref#2'
$D --name experiment_conf1x_parallel --max-iters 24 -- run --campaign conf_1x --set all --engines 'fireducks,bodo,bodo_dw,dask,modin' --reuse-from pilot $B
$D --name experiment_conf1x_compare --max-iters 6 -- compare --campaign conf_1x --set all --engines 'ref#2,pyarrow_backend,fireducks,bodo,bodo_dw,dask,modin' --ref2 'ref#2'
echo "chain done $(date)"
