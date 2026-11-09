"""残留哨兵 验证(sqlite,离线、零业务):命中前缀且不在白名单→报泄漏;白名单内→放过。"""
import os, sys, tempfile
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine, text
from db.client import DbClient
from core.residue import scan_residue
def main():
    print("残留哨兵 验证:\n")
    d=tempfile.mkdtemp(); p=os.path.join(d,"r.db").replace("\\","/")
    eng=create_engine(f"sqlite:///{p}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, title TEXT)"))
        for v in ("AUTOTEST_KEEP_1","AUTOTEST_LEAK_9","正常业务数据"):
            c.execute(text("INSERT INTO t (title) VALUES (:v)"),{"v":v})
    eng.dispose()
    db=DbClient(dsn_readonly=f"sqlite:///{p}")
    leaked=scan_residue(db,[("t","title")],prefix="AUTOTEST",keep=["AUTOTEST_KEEP_1"])
    db.close()
    vals=[x["value"] for x in leaked]
    assert vals==["AUTOTEST_LEAK_9"], vals
    print(f"    ✓ 只揪泄漏项:{vals}(白名单 KEEP_1 放过、业务数据不误报)")
    print("\n全部通过 ✅  —— 残留哨兵精准揪未清造数,白名单与业务数据都不误伤")
if __name__=="__main__": main()
