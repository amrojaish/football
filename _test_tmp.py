import atexit, os, shutil, tempfile
from pathlib import Path
def make_tmp(prefix="ftest_"):
    p = Path(tempfile.mkdtemp(prefix=prefix))
    if os.environ.get("KEEP_TEST_TMP") != "1":
        atexit.register(shutil.rmtree, p, True)
    return p
