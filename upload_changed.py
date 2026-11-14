"""
upload_changed.py — sync _site/**/*.html (minus build_site.HOT_HTML) to the R2 bucket that saffara-site reads
(R3, 14 Nov 2026; prototype: r2_proto/). The hot set (every non-.html file + HOT_HTML) goes to static assets via
`build_site.py --split-hot _hot`; everything this script uploads is served by site_worker.js from R2 (binding PAGES).

DRY-RUN BY DEFAULT: nothing is uploaded or deleted unless --apply is given.

    python upload_changed.py [--site _site] [--bucket saffara-pages] [--manifest-file F] [--list] [--apply]

- Files: build_site.walk_publishable(site) → .html only, minus HOT_HTML (those stay in static assets).
- Hash: sha256 of the raw bytes (what R2 serves; no CRLF normalisation).
- Manifest: R2 object "_manifest.json" = {key: sha256}. Dry run without credentials (or with --manifest-file) uses a
  local JSON file instead; missing = empty bucket.
- Upload: S3-compatible API via boto3 (imported only for real runs), endpoint https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com,
  creds R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY (env or .env). 16 threads, botocore adaptive retries + 3 own attempts per file.
- Resumable: every finished upload is appended to .upload_progress.jsonl (repo root, never published); a rerun folds it into the manifest
  first, so already-uploaded keys are skipped. The R2 manifest is written every CHECKPOINT uploads and at the end;
  the progress file is cleared only after the final manifest write succeeds.
- Deletes are DEFERRED ONE RUN: a key that left _site is recorded in R2 "_pending_delete.json" and deleted only on
  the next run if it is still absent (delete_objects, 1000 per call, after all uploads). The worker version still
  live during this run's upload (and pages/caches pointing at the key) keep getting 200, never a mid-deploy 404.
  A key that comes back before then is simply dropped from the pending list.
"""
import hashlib, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
# same publish filter as _site, and the single definition of the hot set (shared with --split-hot)
from build_site import walk_publishable, is_hot  # noqa: E402

MANIFEST_KEY = "_manifest.json"
PENDING_KEY = "_pending_delete.json"
PROGRESS = BASE / ".upload_progress.jsonl"
THREADS = 16
CHECKPOINT = 2000


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def scan(site):
    out = {}
    for rel in walk_publishable(site):
        if not is_hot(rel) and rel not in (MANIFEST_KEY, PENDING_KEY):
            out[rel] = hashlib.sha256((site / rel).read_bytes()).hexdigest()
    return out


def plan(want, manifest, pending=()):
    """-> new, changed, delete_now, defer. delete_now = gone keys already pending from the previous run;
    defer = gone keys seen for the first time (kept one more run)."""
    new = sorted(k for k in want if k not in manifest)
    changed = sorted(k for k in want if k in manifest and manifest[k] != want[k])
    gone = [k for k in manifest if k not in want]
    pending = set(pending)
    delete = sorted(k for k in gone if k in pending)
    defer = sorted(k for k in gone if k not in pending)
    return new, changed, delete, defer


def load_progress(manifest):
    """Fold an interrupted run's finished uploads into the manifest (resume)."""
    if not PROGRESS.exists():
        return 0
    n = 0
    for line in PROGRESS.read_text(encoding="utf-8").splitlines():
        try:
            k, h = json.loads(line)
            manifest[k] = h
            n += 1
        except ValueError:
            pass   # half-written last line from a crash
    return n


def read_manifest(client, bucket):
    try:
        return json.loads(client.get_object(Bucket=bucket, Key=MANIFEST_KEY)["Body"].read())
    except Exception as e:  # NoSuchKey on first run
        if "NoSuchKey" in repr(e) or "404" in repr(e):
            return {}
        raise


def read_pending(client, bucket):
    try:
        return json.loads(client.get_object(Bucket=bucket, Key=PENDING_KEY)["Body"].read())
    except Exception as e:
        if "NoSuchKey" in repr(e) or "404" in repr(e):
            return []
        raise


def write_pending(client, bucket, keys):
    client.put_object(Bucket=bucket, Key=PENDING_KEY, Body=json.dumps(sorted(keys)).encode(),
                      ContentType="application/json")


def write_manifest(client, bucket, manifest):
    client.put_object(Bucket=bucket, Key=MANIFEST_KEY, Body=json.dumps(manifest, sort_keys=True).encode(),
                      ContentType="application/json")


def sync(site, client, bucket, manifest, want, pending=(), log=print):
    """Real upload/delete. client = boto3 S3 client (or a fake with put_object/get_object/delete_objects).
    pending = keys deferred by the previous run (R2 _pending_delete.json)."""
    new, changed, delete, defer = plan(want, manifest, pending)
    todo = new + changed
    lock = threading.Lock()
    done = failed = 0
    errors = []
    prog = open(PROGRESS, "a", encoding="utf-8")

    def put(k):
        body = (site / k).read_bytes()
        for attempt in range(3):
            try:
                client.put_object(Bucket=bucket, Key=k, Body=body, ContentType="text/html")
                return k
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1 + attempt * 2)

    try:
        with ThreadPoolExecutor(THREADS) as ex:
            futs = {ex.submit(put, k): k for k in todo}
            for f in as_completed(futs):
                k = futs[f]
                try:
                    f.result()
                except Exception as e:
                    failed += 1
                    errors.append((k, repr(e)[:200]))
                    continue
                with lock:
                    manifest[k] = want[k]
                    prog.write(json.dumps([k, want[k]]) + "\n")
                    prog.flush()
                    done += 1
                    if done % CHECKPOINT == 0:
                        write_manifest(client, bucket, manifest)
                        log(f"  checkpoint: {done}/{len(todo)} uploaded")
    finally:
        prog.close()
    deleted = 0
    if not failed:   # only delete once every upload landed, so the bucket never loses a live page mid-sync
        for i in range(0, len(delete), 1000):
            chunk = delete[i:i + 1000]
            client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True})
            for k in chunk:
                manifest.pop(k, None)
            deleted += len(chunk)
    # next run's deletes: this run's newly gone keys (+ the due ones again if this run could not delete them)
    write_pending(client, bucket, defer + (delete if failed else []))
    write_manifest(client, bucket, manifest)
    if not failed:
        PROGRESS.unlink(missing_ok=True)
    return {"uploaded": done, "failed": failed, "deleted": deleted, "deferred": len(defer), "errors": errors}


def make_client():
    import boto3
    from botocore.config import Config
    env = dict(os.environ)
    envf = BASE / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    acct = env.get("R2_ACCOUNT_ID")
    if not (acct and env.get("R2_ACCESS_KEY_ID") and env.get("R2_SECRET_ACCESS_KEY")):
        return None
    # R2_ACCOUNT_ID may be the bare account id or the full endpoint URL (as in our .env)
    endpoint = acct.rstrip("/") if acct.startswith("http") else f"https://{acct}.r2.cloudflarestorage.com"
    return boto3.client("s3", endpoint_url=endpoint,
                        aws_access_key_id=env["R2_ACCESS_KEY_ID"], aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
                        region_name="auto",
                        config=Config(retries={"max_attempts": 10, "mode": "adaptive"}, max_pool_connections=THREADS * 2))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    apply = "--apply" in sys.argv
    site = Path(arg("--site", str(BASE / "_site")))
    if not site.is_absolute():
        site = (Path.cwd() / site).resolve()
    bucket = arg("--bucket", "saffara-pages")
    if not site.is_dir():
        sys.exit(f"no site folder: {site}")
    want = scan(site)

    client = None
    if apply or not arg("--manifest-file"):
        try:
            client = make_client()
        except ImportError:
            if apply:
                sys.exit("--apply needs boto3 (pip install boto3)")
    if apply and client is None:
        sys.exit("--apply needs R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY")
    if client is not None and not arg("--manifest-file"):
        manifest, src = read_manifest(client, bucket), f"r2://{bucket}/{MANIFEST_KEY}"
        pending = read_pending(client, bucket)
    else:
        mf = Path(arg("--manifest-file", str(BASE / "r2_proto" / "r2_manifest.json")))
        manifest, src = (json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}), str(mf)
        pending = []
    resumed = load_progress(manifest)

    new, changed, delete, defer = plan(want, manifest, pending)
    size = sum((site / k).stat().st_size for k in new + changed)
    print(f"site: {site} | html keys: {len(want)} | manifest: {src} ({len(manifest)} keys"
          + (f", {resumed} resumed from progress file" if resumed else "") + ")")
    print(f"{'APPLY' if apply else 'DRY-RUN'}: upload {len(new)} new + {len(changed)} changed = {len(new) + len(changed)} "
          f"({size / 1e6:.1f} MB); delete {len(delete)} (pending from last run); defer {len(defer)} to next run; unchanged {len(want) - len(new) - len(changed)}")
    if "--list" in sys.argv:
        for t, ks in (("NEW", new), ("CHANGED", changed), ("DELETE", delete), ("DEFER", defer)):
            for k in ks:
                print(t, k)
    if not apply:
        return
    r = sync(site, client, bucket, manifest, want, pending)
    print(f"uploaded {r['uploaded']}, failed {r['failed']}, deleted {r['deleted']}, deferred {r['deferred']}")
    for k, e in r["errors"][:10]:
        print("  ERR", k, e)
    sys.exit(1 if r["failed"] else 0)


if __name__ == "__main__":
    main()
