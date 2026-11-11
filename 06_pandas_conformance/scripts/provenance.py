"""Write data/provenance.json for the PandasBench code + data archive.

Records url, sha256, license, retrieval date and a per-file manifest (path, size, sha256)
of the extracted inputs, so any later change of the data is detectable.
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess


def sha256_file(path, bufsize=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--drive-id", required=True)
    ap.add_argument("--no-manifest", action="store_true")
    a = ap.parse_args()
    raw = os.path.join(a.data, "raw")
    zsha_path = os.path.join(raw, "PandasBench_data.zip.sha256")
    zip_path = os.path.join(raw, "PandasBench_data.zip")
    prov_path = os.path.join(a.data, "provenance.json")
    old = {}
    if os.path.exists(prov_path):
        with open(prov_path) as f:
            old = json.load(f)
    repo_dir = os.path.join(a.data, "PandasBench")
    marker = os.path.join(repo_dir, ".artifact_commit")
    head = open(marker).read().strip() if os.path.exists(marker) else subprocess.run(["git", "-C", repo_dir, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    lic_sha = sha256_file(os.path.join(repo_dir, "LICENSE")) if os.path.exists(os.path.join(repo_dir, "LICENSE")) else None
    manifest = old.get("data_manifest", {})
    data_root = os.path.join(raw, "PandasBench_data")
    if not a.no_manifest and os.path.isdir(data_root) and not manifest:
        for dp, dn, fn in os.walk(data_root):
            dn.sort()
            for n in sorted(fn):
                p = os.path.join(dp, n)
                rel = os.path.relpath(p, data_root)
                manifest[rel] = {"bytes": os.path.getsize(p), "sha256": sha256_file(p)}
    today = datetime.date.today().isoformat()
    prov = {
        "dataset": "PandasBench (Broihier, Baziotis, Kang, Mendis; arXiv:2506.02345)",
        "code": {
            "url": a.repo,
            "commit": a.commit,
            "checked_out_head": head,
            "license": "Apache-2.0 (repository LICENSE file); notebooks are Kaggle kernels, check licenses per notebook",
            "license_file_sha256": lic_sha,
            "retrieved": old.get("code", {}).get("retrieved", today),
        },
        "data_archive": {
            "url": "https://drive.google.com/file/d/%s/view?usp=sharing" % a.drive_id,
            "tool": "gdown",
            "mirror_tried": "https://uofi.box.com/shared/static/tipejtwr4khhyzl207uhcwjh2i7k9u8l (HTTP 404 on 2026-10-02)",
            "path": os.path.relpath(zip_path, a.data),
            "bytes": os.path.getsize(zip_path) if os.path.exists(zip_path) else None,
            "sha256": open(zsha_path).read().strip() if os.path.exists(zsha_path) else None,
            "license": "datasets are the original Kaggle inputs of each notebook; per-dataset Kaggle licenses apply",
            "retrieved": old.get("data_archive", {}).get("retrieved", today),
        },
        "data_extracted_root": os.path.relpath(data_root, a.data),
        "data_manifest_files": len(manifest),
        "data_manifest_bytes": sum(v["bytes"] for v in manifest.values()),
        "data_manifest": manifest,
    }
    tmp = prov_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(prov, f, indent=1, sort_keys=True)
    os.replace(tmp, prov_path)
    print("provenance: %d files, %.2f GB" % (prov["data_manifest_files"], prov["data_manifest_bytes"] / 1e9))


if __name__ == "__main__":
    main()
