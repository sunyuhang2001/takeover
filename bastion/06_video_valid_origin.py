# -*- coding: utf-8 -*-
# 06_video_valid_origin.py : 找"有效视频 / video_avaliable"是怎么判定的（只读）
#  1) 在全盘代码/文档里搜关键词，列出命中的文件和代码行
#  2) 统计所有带 video_avaliable / 有效视频 列的表：取值分布、对应事件数、时间范围
# 依赖 01 的 file_index.csv、04 的 table_catalog.csv；需要 pandas、openpyxl
import os, sys, re, hashlib, time
import pandas as pd

NAME, VERSION = "06_video_valid_origin", "v2"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\06_video_valid"
CODE_EXT = {".py", ".ipynb", ".m", ".sql", ".md", ".txt", ".r", ".sh", ".bat", ".json", ".yaml", ".yml", ".ini", ".cfg"}
MAX_MB = 5
# 权重高的：直接和"视频是否有效"相关
STRONG = ["有效视频", "video_avaliable", "video_available", "video_valid", "valid_video", "视频有效", "无效视频", "视频可用"]
# 权重低的：和 0920 表 / 脱离事件生成相关
WEAK = ["脱离事件汇总", "0920", "0401-0409", "critical_engage", "是否紧急接管", "all927", "dis_joined", "all_1021"]
VALID_COLS = ["video_avaliable", "video_available", "有效视频", "video_valid"]


def selfcheck():
    try:
        t = open(__file__, "rb").read().decode("utf-8", "replace")
    except Exception:
        return "n/a"
    lines = [l.rstrip() for l in t.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return hashlib.md5("\n".join(lines).encode("utf-8")).hexdigest()[:8]


L = []
def out(s=""):
    print(s); L.append(s)


def read_text(path):
    b = open(path, "rb").read()
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))

    fi = pd.read_csv(BASE + r"\01_scan\file_index.csv", dtype=str, keep_default_na=False)
    fi["size_bytes"] = pd.to_numeric(fi.size_bytes, errors="coerce").fillna(0)

    # ---------------- 0) 0920 表的来历 ----------------
    import zipfile
    src = fi[fi.name.str.contains("脱离事件汇总") & ~fi.dir.str.lower().str.contains("takeover_audit")].sort_values("mtime")
    out("[0920 文件] 共%d份 (按修改时间; xlsx内部元数据: 作者/最后修改人/创建/修改)" % len(src))
    for d, n, sz, mt in zip(src.dir, src.name, src.size_bytes, src.mtime):
        p = d + "\\" + n
        meta = ""
        if n.lower().endswith((".xlsx", ".xlsm")):
            try:
                x = zipfile.ZipFile(p).read("docProps/core.xml").decode("utf-8", "replace")
                g = lambda tag: (re.search(r"<%s[^>]*>([^<]*)</%s>" % (tag, tag), x) or [None, ""])[1]
                meta = "作者=%s 修改人=%s 创建=%s 修改=%s" % (g("dc:creator"), g("cp:lastModifiedBy"),
                                                       g("dcterms:created")[:16], g("dcterms:modified")[:16])
            except Exception as e:
                meta = "meta err %s" % repr(e)[:40]
        out("   %s  %6.2fMB  %s" % (mt, sz / 2**20, p[-70:]))
        if meta:
            out("        " + meta)
    prev = fi[fi.dir.str.contains("堡垒机数据筛选") & fi.ext.isin({".py", ".md"})]
    out("")
    out("[前人脚本] %d个 .py/.md，提到 0920/脱离事件汇总/有效视频/读写excel 的行:" % len(prev))
    KEY = ("0920", "脱离事件汇总", "有效视频", "video_ava", "read_excel", "to_excel", "read_csv", "to_csv")
    shown = 0
    for d, n in zip(prev.dir, prev.name):
        try:
            t = read_text(d + "\\" + n)
        except Exception:
            continue
        ls = [(i + 1, l.strip()) for i, l in enumerate(t.splitlines()) if any(k in l for k in KEY)]
        if not ls:
            continue
        out("   # " + n)
        for i, l in ls[:5]:
            out("     L%-4d %s" % (i, l[:140])); shown += 1
        if shown > 30:
            break
    out("")

    # ---------------- 1) 搜代码 ----------------
    low_dir = fi.dir.str.lower()
    code = fi[fi.ext.isin(CODE_EXT) & (fi.size_bytes <= MAX_MB * 2**20)
              & ~low_dir.str.contains(r"takeover_audit|site-packages|\\.vscode|node_modules|appdata|miniconda|pycharm|\\.git")]
    code = code[~code.name.str.contains(r"participant_|vehicle_track_|traffic_flow_|signal_|camera_url_|event_\d")]
    out("[code] 待搜文件=%d  (%s)" % (len(code), "  ".join("%s:%d" % (k, v) for k, v in code.ext.value_counts().head(8).items())))
    rows, lines_out = [], []
    for d, n, mt in zip(code.dir, code.name, code.mtime):
        p = d + "\\" + n
        try:
            t = read_text(p)
        except Exception:
            continue
        s_hit = [k for k in STRONG if k in t]
        w_hit = [k for k in WEAK if k in t]
        if not s_hit and not w_hit:
            continue
        rows.append(dict(path=p, mtime=mt, strong=",".join(s_hit), weak=",".join(w_hit),
                         score=10 * len(s_hit) + len(w_hit)))
        if s_hit:
            for i, line in enumerate(t.splitlines()):
                if any(k in line for k in s_hit):
                    lines_out.append(dict(path=p, line=i + 1, text=line.strip()[:300]))
    hits = pd.DataFrame(rows)
    ln = pd.DataFrame(lines_out)
    if len(hits):
        hits = hits.sort_values(["score", "mtime"], ascending=False)
        hits.to_csv(OUT_DIR + r"\code_hits.csv", index=False, encoding="utf-8-sig")
    if len(ln):
        ln.to_csv(OUT_DIR + r"\code_lines.csv", index=False, encoding="utf-8-sig")
    out("       命中文件=%d  其中含'有效视频/video_avaliable'类关键词=%d" % (len(hits), (hits.strong != "").sum() if len(hits) else 0))
    out("       得分最高的文件 (修改时间 | 强关键词 | 弱关键词 | 路径):")
    for _, r in hits.head(15).iterrows():
        out("   %s | %s | %s | %s" % (r.mtime[:10], r.strong[:30], r.weak[:30], r.path[-80:]))
    out("")
    out("       含强关键词的代码行 (每个文件最多3行, 前12个文件):")
    if len(ln):
        for p in hits[hits.strong != ""].path.head(12):
            out("   # " + p[-90:])
            for _, r in ln[ln.path == p].head(3).iterrows():
                out("     L%-5d %s" % (r.line, r.text[:150]))

    # ---------------- 2) 带 video_avaliable 列的表 ----------------
    cat = pd.read_csv(BASE + r"\04_tables\table_catalog.csv", dtype=str, keep_default_na=False)
    lc = cat.cols.str.lower()
    vt = cat[lc.apply(lambda c: any(k in c.split(",") for k in VALID_COLS))].drop_duplicates("path")
    out("")
    out("[tables] 含有效视频列的表=%d (列出前12个, 按大小)" % len(vt))
    vt = vt.assign(size_mb=pd.to_numeric(vt.size_mb, errors="coerce")).sort_values("size_mb", ascending=False)
    res = []
    for _, r in vt.head(40).iterrows():
        try:
            if r.path.lower().endswith(".csv"):
                df = None
                for enc in ("utf-8-sig", "gbk"):
                    try:
                        df = pd.read_csv(r.path, dtype=str, encoding=enc); break
                    except UnicodeDecodeError:
                        continue
            else:
                df = pd.read_excel(r.path, sheet_name=r.sheet or 0, dtype=str)
            cols = {c.strip().lower(): c for c in df.columns}
            cvalid = next(cols[k] for k in VALID_COLS if k in cols)
            cvin = next((cols[k] for k in ("vin", "vin_x", "t2.vin") if k in cols), None)
            ct = next((cols[k] for k in ("disengage_time", "dis_engage_time") if k in cols), None)
            key = [c for c in (cvin, ct) if c]
            ev = df.drop_duplicates(key) if key else df
            vc = ev[cvalid].fillna("<空>").astype(str).str.strip().value_counts()
            t = pd.to_datetime(ev[ct], errors="coerce") if ct else pd.Series(dtype="datetime64[ns]")
            res.append(dict(path=r.path, rows=len(df), events=len(ev), col=cvalid,
                            values=" ".join("%s:%d" % (k, v) for k, v in vc.head(5).items()),
                            tmin=t.min(), tmax=t.max()))
        except Exception as e:
            res.append(dict(path=r.path, err=repr(e)[:120]))
    rt = pd.DataFrame(res)
    rt.to_csv(OUT_DIR + r"\valid_tables.csv", index=False, encoding="utf-8-sig")
    for _, r in rt.head(12).iterrows():
        if isinstance(r.get("err"), str):
            out("   ERR %s  %s" % (r.path[-60:], r.err[:60])); continue
        out("   %s" % r.path[-85:])
        out("       行=%d 事件=%d  %s: %s   时间 %s ~ %s" % (r.rows, r.events, r.col, r["values"], str(r.tmin)[:10], str(r.tmax)[:10]))
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
