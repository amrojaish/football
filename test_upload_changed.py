"""Unit test for upload_changed.sync (deferred one-run deletes) with a fake S3 client (no network, temp folder only)."""
import io, json, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upload_changed as U


class FakeS3:
    def __init__(self, fail_keys=()):
        self.objs, self.fail = {}, set(fail_keys)
        self.puts = 0

    def put_object(self, Bucket, Key, Body, ContentType):
        if Key in self.fail:
            raise RuntimeError("boom " + Key)
        self.puts += 1
        self.objs[Key] = (bytes(Body), ContentType)

    def get_object(self, Bucket, Key):
        if Key not in self.objs:
            raise RuntimeError("NoSuchKey")
        return {"Body": io.BytesIO(self.objs[Key][0])}

    def delete_objects(self, Bucket, Delete):
        for o in Delete["Objects"]:
            self.objs.pop(o["Key"], None)


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    return cond


def main():
    U.time.sleep = lambda s: None
    ok = True
    with tempfile.TemporaryDirectory() as td:
        site = Path(td)
        U.PROGRESS = site.parent / (site.name + ".progress.jsonl")
        for k, v in {"matches/1.html": "a", "en/matches/1.html": "b", "players/x.html": "c",
                     "index.html": "hot", "assets/a.css": "css"}.items():
            (site / k).parent.mkdir(parents=True, exist_ok=True)
            (site / k).write_text(v)
        s3 = FakeS3()
        want = U.scan(site)
        ok &= check("scan skips hot html + non-html", sorted(want) == ["en/matches/1.html", "matches/1.html", "players/x.html"])
        r = U.sync(site, s3, "b", {}, want, log=lambda *a: None)
        ok &= check("first sync uploads 3", r["uploaded"] == 3 and r["failed"] == 0)
        ok &= check("content-type text/html", s3.objs["matches/1.html"][1] == "text/html")
        m = U.read_manifest(s3, "b")
        ok &= check("manifest in bucket", m == want)
        # no-op rerun
        s3.puts = 0
        r = U.sync(site, s3, "b", U.read_manifest(s3, "b"), U.scan(site), log=lambda *a: None)
        ok &= check("rerun uploads nothing (only manifest + pending list)", r["uploaded"] == 0 and s3.puts == 2)
        rd = lambda c: (U.read_manifest(c, "b"), U.read_pending(c, "b"))
        quiet = lambda *a: None
        # change + removal: removed key is DEFERRED (still in bucket + manifest), deleted on the next run
        (site / "matches/1.html").write_text("a2")
        (site / "players/x.html").unlink()
        m, pend = rd(s3)
        r = U.sync(site, s3, "b", m, U.scan(site), pend, log=quiet)
        ok &= check("changed 1, removal deferred (key still served)", r["uploaded"] == 1 and r["deleted"] == 0
                    and r["deferred"] == 1 and "players/x.html" in s3.objs and "players/x.html" in U.read_manifest(s3, "b"))
        ok &= check("pending list written", U.read_pending(s3, "b") == ["players/x.html"])
        m, pend = rd(s3)
        r = U.sync(site, s3, "b", m, U.scan(site), pend, log=quiet)
        ok &= check("next run deletes it", r["deleted"] == 1 and "players/x.html" not in s3.objs
                    and "players/x.html" not in U.read_manifest(s3, "b") and U.read_pending(s3, "b") == [])
        # a removed key that comes back before the next run is NOT deleted
        (site / "players/y.html").write_text("y")
        m, pend = rd(s3)
        U.sync(site, s3, "b", m, U.scan(site), pend, log=quiet)
        (site / "players/y.html").unlink()
        m, pend = rd(s3)
        U.sync(site, s3, "b", m, U.scan(site), pend, log=quiet)          # y deferred
        (site / "players/y.html").write_text("y")
        m, pend = rd(s3)
        r = U.sync(site, s3, "b", m, U.scan(site), pend, log=quiet)      # y back
        ok &= check("returning key survives + leaves pending", r["deleted"] == 0 and "players/y.html" in s3.objs
                    and U.read_pending(s3, "b") == [])
        # failure: no deletes (due keys stay pending), progress kept, resume
        (site / "players/y.html").unlink()
        m, pend = rd(s3)
        U.sync(site, s3, "b", m, U.scan(site), pend, log=quiet)          # y deferred again
        (site / "clubs").mkdir()
        (site / "clubs/9.html").write_text("n")
        bad = FakeS3(fail_keys={"clubs/9.html"})
        bad.objs = dict(s3.objs)
        m, pend = rd(bad)
        r = U.sync(site, bad, "b", m, U.scan(site), pend, log=quiet)
        ok &= check("failed upload blocks deletes, due key stays pending", r["failed"] == 1 and r["deleted"] == 0
                    and "players/y.html" in bad.objs and U.read_pending(bad, "b") == ["players/y.html"])
        bad.fail.clear()
        man, pend = rd(bad)
        U.load_progress(man)
        new, changed, delete, defer = U.plan(U.scan(site), man, pend)
        ok &= check("resume plans only the failed key + the due delete",
                    new == ["clubs/9.html"] and delete == ["players/y.html"] and defer == [])
        r = U.sync(site, bad, "b", man, U.scan(site), pend, log=quiet)
        ok &= check("resume finishes, progress cleared", r["failed"] == 0 and r["deleted"] == 1
                    and "players/y.html" not in bad.objs and not U.PROGRESS.exists())
        # hot set shared with build_site.py --split-hot
        import build_site as B
        ok &= check("is_hot: non-.html + 12 shell pages", B.is_hot("sw.js") and B.is_hot("en/search.html")
                    and not B.is_hot("matches/1.html") and len(B.HOT_HTML) == 12)
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
