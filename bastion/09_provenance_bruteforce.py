# -*- coding: utf-8 -*-
# 09_provenance_bruteforce.py : 暴力溯源 0920 表（只读，C盘+D盘）
#  A) 所有表格：只读 vin + 时间列，统计含多少 0920 事件(vin+秒)、自己共有多少事件 -> 找上游/同源/下游
#  B) 所有代码/文档：搜 0920 特有列名和文件名，列出读/写了哪些文件 -> 串起处理链
# 依赖 01 的 file_index.csv、04 的 table_catalog.csv；需要 pandas、openpyxl
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "09_provenance_bruteforce", "v1"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\09_provenance"
MAX_TABLE_MB = 600
MAX_CODE_MB = 30
CODE_EXT = {".py", ".ipynb", ".sql", ".m", ".r", ".txt", ".md", ".bat", ".sh", ".json", ".yaml", ".yml"}
ANCHORS = ["acc_long_min", "acc_lat_abs_max", "cross_name1", "cross_name", "是否紧急接管", "主车行为", "目标物行为",
           "与目标物相对关系", "有效视频", "道路类型", "脱离事件汇总", "0401-0409", "请复制后", "0920", "disengage_time"]
STRONG = set(ANCHORS[:12])
RW = re.compile(r"(read_excel|read_csv|load_workbook|open\(|to_excel|to_csv|ExcelWriter|\.save\(|copy|glob)\s*\(?[^\n]{0,160}")


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


def to_sec(s):
    s = s.dropna()
    if not len(s):
        return pd.Series(dtype="float")
    smp = s.astype(str).head(2000)
    if s.dtype.kind in "iuf" or smp.str.fullmatch(r"\d{10,13}(\.\d+)?").mean() > 0.9:
        x = pd.to_numeric(s, errors="coerce")
        return ((x / 1000.0 if x.median() > 1e12 else x) + 8 * 3600).round()
    if s.dtype.kind == "M":
        t = s
    else:
        try:
            t = pd.to_datetime(s.astype(str), errors="coerce", infer_datetime_format=True)
        except TypeError:
            t = pd.to_datetime(s.astype(str), errors="coerce", format="mixed")
    return ((t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("float")


def read_text(p):
    b = open(p, "rb").read()
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def is_time_col(c):
    c = str(c).strip().lower()
    return ("time" in c or "时间" in c or c in ("timestamp", "date", "datetime")) and not any(
        k in c for k in ("duration", "时长", "耗时", "index"))


def is_vin_col(c):
    c = str(c).strip().lower()
    return c in ("vin", "vin_x", "vin_y", "t2.vin", "车辆vin", "vin码", "车架号")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))
    fi = pd.read_csv(BASE + r"\01_scan\file_index.csv", dtype=str, keep_default_na=False)
    fi["path"] = fi.dir + "\\" + fi.name
    fi["size_bytes"] = pd.to_numeric(fi.size_bytes, errors="coerce").fillna(0)
    fi = fi[~fi.dir.str.lower().str.contains("takeover_audit")]

    # 0920 事件键
    src = fi[fi.name.str.contains("脱离事件汇总") & fi.name.str.lower().str.endswith(".xlsx")].sort_values("mtime").path.iloc[0]
    ev = pd.read_excel(src, sheet_name=0)
    vcol = next(c for c in ev.columns if is_vin_col(c))
    ev_sec = to_sec(ev["disengage_time"]).astype("Int64")
    keys = set(zip(ev[vcol].astype(str).str.upper().str.strip(), ev_sec))
    keys = {k for k in keys if pd.notna(k[1])}
    kv = pd.DataFrame(list(keys), columns=["vin", "sec"])
    out("[0920] %s  事件键=%d" % (src[-55:], len(keys)))

    # ---------------- A) 表格 ----------------
    cat = pd.read_csv(BASE + r"\04_tables\table_catalog.csv", dtype=str, keep_default_na=False)
    cat = cat[~cat.path.str.lower().str.contains("takeover_audit")]
    cat["cl"] = cat.cols.str.split(",")
    cat["has_vin"] = cat.cl.apply(lambda l: any(is_vin_col(c) for c in l))
    cat["has_t"] = cat.cl.apply(lambda l: any(is_time_col(c) for c in l))
    cand = cat[cat.has_vin & cat.has_t].copy()
    cand["size_mb"] = pd.to_numeric(cand.size_mb, errors="coerce").fillna(0)
    cand = cand[cand.size_mb <= MAX_TABLE_MB]
    out("[A] 带vin+时间列的表(sheet)=%d  文件=%d  %.1fGB" % (len(cand), cand.path.nunique(),
                                                          cand.drop_duplicates("path").size_mb.sum() / 1024))
    res, t0 = [], time.time()
    for i, r in enumerate(cand.itertuples(), 1):
        try:
            want = lambda c: is_vin_col(c) or is_time_col(c)
            if r.path.lower().endswith(".csv"):
                df = None
                for enc in ("utf-8-sig", "gbk"):
                    try:
                        df = pd.read_csv(r.path, usecols=want, dtype=str, encoding=enc, on_bad_lines="skip"); break
                    except UnicodeDecodeError:
                        continue
            else:
                df = pd.read_excel(r.path, sheet_name=r.sheet or 0, usecols=want)
            vc = next(c for c in df.columns if is_vin_col(c))
            vin = df[vc].astype(str).str.upper().str.strip()
            best = None
            for tc in [c for c in df.columns if is_time_col(c)]:
                sec = to_sec(df[tc])
                d = pd.DataFrame({"vin": vin.reindex(sec.index), "sec": sec}).dropna().drop_duplicates()
                d["sec"] = d.sec.astype("int64")
                for sh, lab in ((0, "0"), (8 * 3600, "+8h"), (-8 * 3600, "-8h")):
                    hit = d.assign(sec=d.sec + sh).merge(kv, on=["vin", "sec"]).drop_duplicates().shape[0]
                    if best is None or hit > best[0]:
                        best = (hit, tc, lab, len(d), d.vin.nunique())
            if best:
                res.append(dict(path=r.path, sheet=r.sheet, rows=len(df), hit=best[0], tcol=best[1], shift=best[2],
                                uniq_keys=best[3], vins=best[4], cols=r.cols))
        except Exception as e:
            res.append(dict(path=r.path, sheet=r.sheet, err=repr(e)[:150]))
        if i % 200 == 0:
            print("  ... tables %d/%d  %.0fs" % (i, len(cand), time.time() - t0))
    R = pd.DataFrame(res)
    R = R.merge(fi[["path", "mtime", "size_bytes"]], on="path", how="left")
    R.to_csv(OUT_DIR + r"\tables_vs_0920.csv", index=False, encoding="utf-8-sig")
    ok = R[R.get("hit", pd.Series(dtype=float)).fillna(0) > 0].copy()
    n = len(keys)
    ok["cover"] = ok.hit / n
    ok["extra"] = ok.uniq_keys - ok.hit
    def role(r):
        if r.cover >= 0.9 and r.extra > 0.1 * n:
            return "上游(超集)"
        if r.cover >= 0.9:
            return "同源"
        return "下游/部分"
    ok["role"] = ok.apply(role, axis=1)
    out("    读失败=%d  含0920事件的表=%d  (上游%d / 同源%d / 部分%d)  用时%.0fs" % (
        R.get("err", pd.Series(dtype=str)).notna().sum(), len(ok), (ok.role == "上游(超集)").sum(),
        (ok.role == "同源").sum(), (ok.role == "下游/部分").sum(), time.time() - t0))
    tv = set(c.lower() for c in ev.columns)
    for role_name in ("上游(超集)", "同源"):
        s = ok[ok.role == role_name].sort_values("mtime")
        s = s.drop_duplicates(["uniq_keys", "hit", "cols"])
        out("")
        out("  %s 按修改时间 (去掉同结构同内容的拷贝): 修改时间 | 覆盖0920 | 自身事件 | VIN | 时间列/偏移 | 路径" % role_name)
        for _, x in s.head(14).iterrows():
            out("   %s | %4d(%3.0f%%) | %7d | %4d | %s %s | %s" % (x.mtime[:10], x.hit, 100 * x.cover, x.uniq_keys, x.vins,
                                                               str(x.tcol)[:16], x["shift"], x.path[-58:]))
            extra_cols = [c for c in str(x.cols).split(",") if c.strip().lower() not in tv][:8]
            out("        多出列: %s" % ",".join(extra_cols)[:120])
    part = ok[ok.role == "下游/部分"]
    out("")
    out("  部分包含(<90%%)的表: %d 个, 覆盖率分布: <10%%:%d 10-50%%:%d 50-90%%:%d" % (
        len(part), (part.cover < .1).sum(), ((part.cover >= .1) & (part.cover < .5)).sum(), (part.cover >= .5).sum()))

    # ---------------- B) 代码 ----------------
    low = fi.dir.str.lower()
    code = fi[fi.ext.isin(CODE_EXT) & (fi.size_bytes <= MAX_CODE_MB * 2**20)
              & ~low.str.contains(r"site-packages|\\.vscode|node_modules|appdata|miniconda|pycharm|\\.git|anaconda|matlab\\toolbox")]
    code = code[~code.name.str.contains(r"^(?:participant|vehicle_track|traffic_flow|signal|camera_url|event)_\d")]
    out("")
    out("[B] 代码/文档文件=%d" % len(code))
    rows, io_rows = [], []
    for p, mt in zip(code.path, code.mtime):
        try:
            t = read_text(p)
        except Exception:
            continue
        hits = [a for a in ANCHORS if a in t]
        if not hits:
            continue
        sc = 10 * len([h for h in hits if h in STRONG]) + len(hits)
        rows.append(dict(path=p, mtime=mt, score=sc, hits=",".join(hits)))
        for m in RW.finditer(t):
            seg = m.group(0)
            if any(k in seg for k in ("脱离", "汇总", "0920", "0401", "all9", "dis_joined", "all_1021", "xlsx", "csv")):
                io_rows.append(dict(path=p, mtime=mt, io=seg.strip()[:200]))
    C = pd.DataFrame(rows)
    IO = pd.DataFrame(io_rows).drop_duplicates() if io_rows else pd.DataFrame(columns=["path", "mtime", "io"])
    if len(C):
        C = C.sort_values(["score", "mtime"], ascending=[False, True])
        C.to_csv(OUT_DIR + r"\code_hits.csv", index=False, encoding="utf-8-sig")
        IO.to_csv(OUT_DIR + r"\code_io.csv", index=False, encoding="utf-8-sig")
        out("    命中=%d 个文件.  得分最高15个(按时间): 修改时间 | 命中关键词 | 路径" % len(C))
        top = C.head(15).sort_values("mtime")
        for _, x in top.iterrows():
            out("   %s | %s | %s" % (x.mtime[:10], x.hits[:60], x.path[-60:]))
        out("")
        out("    这些文件里的读/写语句(每个文件最多3条):")
        for p in top.path:
            s = IO[IO.path == p].head(3)
            if len(s):
                out("   # " + p[-60:])
                for io in s.io:
                    out("       " + io[:140])
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
