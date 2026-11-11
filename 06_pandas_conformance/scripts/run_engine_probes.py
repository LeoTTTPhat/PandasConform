#!/usr/bin/env python3
"""Run the engine root-cause probes listed in results/rootcause/probes_todo.json (F4, 2026-10-04).

Run ONLY under the memory guard (Modin/Ray, Bodo/MPI and Dask start worker pools):
  cd .. && python3 tools/memory_guard.py --limit-gb 120 --wait-lock 14400 \
      --state runs/06_pandas_conformance_rootcause_probes.json -- .venv/bin/python 06_pandas_conformance/scripts/run_engine_probes.py
Probes run one at a time in list order, each with a timeout. Every probe's output is appended to
results/rootcause/engine_probe_runs.log. Results are checkpointed atomically to
results/rootcause/engine_probe_results.json, keyed by the sha256 of the command plus the sha256 of the
repro script, so a rerun skips completed probes. Failures are recorded and the run continues.
MEMGUARD_DELAY_SECONDS (set by the guard on a restart) adds a pause between probes.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

PROJ = Path(__file__).resolve().parents[1]
RC = PROJ / 'results' / 'rootcause'
TODO = RC / 'probes_todo.json'
OUT = RC / 'engine_probe_results.json'
LOG = RC / 'engine_probe_runs.log'
TIMEOUT_S = int(os.environ.get('PCONF_PROBE_TIMEOUT', '900'))


def key(probe):
    h = hashlib.sha256(probe['command'].encode())
    script = PROJ / probe.get('script', '')
    if script.is_file():
        h.update(script.read_bytes())
    return h.hexdigest()[:16]


def kill_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def save(results):
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(results, indent=2, sort_keys=True) + '\n')
    tmp.replace(OUT)


def main():
    probes = json.loads(TODO.read_text())['probes']
    results = json.loads(OUT.read_text()) if OUT.exists() else {}
    delay = float(os.environ.get('MEMGUARD_DELAY_SECONDS', '0') or 0)
    done = 0
    for i, probe in enumerate(probes):
        k = key(probe)
        if k in results:
            continue
        t0 = time.time()
        with open(LOG, 'a') as log:
            log.write('\n===== [%d/%d] %s %s %s\n$ %s\n' % (i + 1, len(probes), time.strftime('%Y-%m-%d %H:%M:%S'),
                                                        probe['cause'], probe['engine'], probe['command']))
            log.flush()
            # Own process group per probe, so a timeout or leftover workers (Ray, MPI, Dask) can be killed as a
            # group; the processes stay descendants of this runner, so the guard still counts their RSS.
            p = subprocess.Popen(['bash', '-c', probe['command']], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, errors='replace', start_new_session=True)
            try:
                out, _ = p.communicate(timeout=TIMEOUT_S)
                rc, status = p.returncode, ('ok' if p.returncode == 0 else 'error')
            except subprocess.TimeoutExpired:
                rc, status = None, 'timeout'
                kill_group(p.pid, signal.SIGTERM)
                try:
                    out, _ = p.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    kill_group(p.pid, signal.SIGKILL)
                    out, _ = p.communicate()
            kill_group(p.pid, signal.SIGKILL)  # stragglers left in the probe's group
            log.write(out or '')
            log.write('\n----- rc=%s status=%s %.1fs\n' % (rc, status, time.time() - t0))
        results[k] = {'index': i, 'cause': probe['cause'], 'engine': probe['engine'], 'command': probe['command'],
                      'status': status, 'returncode': rc, 'seconds': round(time.time() - t0, 2),
                      'output_tail': (out or '')[-4000:], 'finished': time.strftime('%Y-%m-%d %H:%M:%S')}
        save(results)
        done += 1
        if delay:
            time.sleep(delay * 50)
    print(json.dumps({'probes': len(probes), 'recorded': len(results), 'ran_now': done}))


if __name__ == '__main__':
    main()
