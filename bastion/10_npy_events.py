# -*- coding: utf-8 -*-
# 10_npy_events.py : 盘点全盘 .npy/.npz（脱离事件样本 takeover_periods / labels），
#                    还原"全部脱离事件"清单，并与 0920 台账、自车视频事件比对（只读）
# 依赖 01 的 file_index.csv、02 的 video_events.csv；需要 numpy、pandas、openpyxl
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "10_npy_events", "v1"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\10_npy"
RE_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
MATCH_0920_S = 2      # labels 时间与 0920 disengage_time 相差 <=2s 算同一事件
MATCH_VIDEO_S = 60    # 与视频片段中点相差 <=60s 算有视频


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
    """任意时间列 -> 秒(北京时间视角)。数字按 epoch(UTC)+8h；返回 float Series"""
    s = pd.Series(s)
    if s.dtype.kind == "M":                      # 已经是日期时间(如 Excel 日期)，按北京时间原样用
        return ((s - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("float")
    if s.dtype == object and len(s.dropna()) and isinstance(s.dropna().iloc[0], (pd.Timestamp, np.datetime64)):
        s = pd.to_datetime(s, errors="coerce")
        return ((s - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("float")
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.9:
        med = num.median()
        if med > 1e17: x = num / 1e9
        elif med > 1e14: x = num / 1e6
        elif med > 1e11: x = num / 1e3
        elif med > 1e8: x = num
        else: return pd.Series(np.nan, index=s.index)
        return x + 8 * 3600
    try:
        t = pd.to_datetime(s.astype(str), errors="coerce", infer_datetime_format=True)
    except TypeError:
        t = pd.to_datetime(s.astype(str), errors="coerce", format="mixed")
    return ((t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("float")


def detect_labels(arr):
    """2维数组 -> 若含 vin+时间列，返回 DataFrame(vin, sec, lat, lon)，否则 None"""
    if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] > 50:
        return None, ""
    df = pd.DataFrame(arr)
    head = df.head(5000)
    vc = tc = la = lo = None
    for c in df.columns:
        col = head[c]
        s = col.astype(str).str.strip().str.upper()
        if vc is None and s.str.match(RE_VIN).mean() > 0.8:
            vc = c; continue
        num = pd.to_numeric(col, errors="coerce")
        if num.notna().mean() > 0.9:
            med = num.median()
            if la is None and 20 < med < 50: la = c; continue
            if lo is None and 100 < med < 140: lo = c; continue
        if tc is None:
            sec = to_sec(col)
            ok = sec.between(1.5e9, 1.9e9)
            if ok.mean() > 0.8:
                tc = c
    if vc is None or tc is None:
        return None, "cols vin=%s time=%s" % (vc, tc)
    res = pd.DataFrame({"vin": df[vc].astype(str).str.strip().str.upper(), "sec": to_sec(df[tc])})
    res["lat"] = pd.to_numeric(df[la], errors="coerce") if la is not None else np.nan
    res["lon"] = pd.to_numeric(df[lo], errors="coerce") if lo is not None else np.nan
    return res, "vin=col%s time=col%s lat=col%s lon=col%s" % (vc, tc, la, lo)


def load_any(p):
    """返回 [(name, array)]"""
    if p.lower().endswith(".npz"):
        z = np.load(p, allow_pickle=True)
        return [(k, z[k]) for k in z.files]
    try:
        return [("", np.load(p, mmap_mode="r"))]
    except ValueError:
        return [("", np.load(p, allow_pickle=True))]


def match_count(ev, ref, tol):
    """ev, ref: DataFrame(vin, sec)；返回 ev 中在 ref 里(同vin, |dt|<=tol)能找到的条数，并试 ±8h"""
    best = (0, "0")
    if not len(ev) or not len(ref):
        return best
    r = ref.dropna().sort_values("sec")
    for sh, lab in ((0, "0"), (8 * 3600, "+8h"), (-8 * 3600, "-8h")):
        e = ev.dropna().assign(sec=lambda d: d.sec + sh).sort_values("sec")
        m = pd.merge_asof(e, r[["vin", "sec"]].rename(columns={"sec": "rsec"}), left_on="sec", right_on="rsec",
                          by="vin", direction="nearest")
        n = ((m.sec - m.rsec).abs() <= tol).sum()
        if n > best[0]:
            best = (int(n), lab)
    return best


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
    low = fi.dir.str.lower()
    fi = fi[~low.str.contains(r"takeover_audit|site-packages|miniconda|anaconda|\\.vscode|appdata")]

    # ---------- processing_data 目录结构 ----------
    pdd = fi[fi.dir.str.lower().str.contains("processing_data")]
    out("[processing_data] 文件=%d  %.1fGB" % (len(pdd), pdd.size_bytes.sum() / 2**30))
    g = pdd.groupby(pdd.dir.str.extract(r"(.*processing_data[^\\]*(?:\\[^\\]+)?)", expand=False).fillna(pdd.dir))
    for d, x in sorted(g, key=lambda kv: -kv[1].size_bytes.sum())[:10]:
        out("   %-60s 文件=%5d %6.2fGB  %s  %s~%s" % (d[-60:], len(x), x.size_bytes.sum() / 2**30,
            " ".join("%s:%d" % (k, v) for k, v in x.ext.value_counts().head(4).items()), x.mtime.min()[:10], x.mtime.max()[:10]))

    # ---------- 参照：0920 与视频事件 ----------
    src = fi[fi.name.str.contains("脱离事件汇总") & fi.name.str.lower().str.endswith(".xlsx")].sort_values("mtime").path.iloc[0]
    e9 = pd.read_excel(src, sheet_name=0)
    e9 = pd.DataFrame({"vin": e9["vin"].astype(str).str.upper().str.strip(), "sec": to_sec(e9["disengage_time"])})
    ve = pd.read_csv(BASE + r"\02_ego_video\video_events.csv", dtype={"vin": str, "chans": str})
    ve = ve[ve.vin.notna()]
    vref = pd.DataFrame({"vin": ve.vin, "sec": to_sec(ve.mid)})
    vref1 = vref[ve.chans.fillna("").astype(str).str.contains("1").values]
    out("")
    out("[参照] 0920=%d  视频事件=%d (有ch1的=%d)" % (len(e9), len(vref), len(vref1)))

    # ---------- npy / npz ----------
    npf = fi[fi.ext.isin([".npy", ".npz"])].sort_values("mtime")
    out("")
    out("[npy] 文件=%d  %.1fGB" % (len(npf), npf.size_bytes.sum() / 2**30))
    rows, events = [], []
    for p, mt, sz in zip(npf.path, npf.mtime, npf.size_bytes):
        try:
            for key, arr in load_any(p):
                rec = dict(path=p, key=key, mtime=mt, mb=sz / 2**20, shape=str(tuple(arr.shape)), dtype=str(arr.dtype))
                if arr.ndim == 2 and arr.shape[1] <= 50:
                    lab, how = detect_labels(np.asarray(arr))
                    rec["how"] = how
                    if lab is not None:
                        rec.update(n=len(lab), vins=lab.vin.nunique(),
                                   tmin=pd.to_datetime(lab.sec.min(), unit="s"), tmax=pd.to_datetime(lab.sec.max(), unit="s"))
                        rec["in0920"], rec["sh0920"] = match_count(e9, lab[["vin", "sec"]], MATCH_0920_S)
                        rec["hasvid"], rec["shvid"] = match_count(lab[["vin", "sec"]], vref, MATCH_VIDEO_S)
                        rec["hasvid_ch1"], _ = match_count(lab[["vin", "sec"]], vref1, MATCH_VIDEO_S)
                        rec["vid_found"], _ = match_count(vref, lab[["vin", "sec"]], MATCH_VIDEO_S)
                        rec["sample"] = " | ".join(str(v)[:24] for v in np.asarray(arr)[0][:6])
                        events.append(lab.assign(src=p))
                rows.append(rec)
        except Exception as e:
            rows.append(dict(path=p, mtime=mt, mb=sz / 2**20, err=repr(e)[:150]))
    R = pd.DataFrame(rows)
    R.to_csv(OUT_DIR + r"\npy_files.csv", index=False, encoding="utf-8-sig")
    if len(R):
        out("   形状分布(前10): " + "  ".join("%s:%d" % (k, v) for k, v in R["shape"].value_counts().head(10).items()))
        seq = R[R["shape"].str.count(",") == 2]
        out("   3维(样本,时间步,特征)数组=%d个  样本数合计=%s" % (len(seq), seq["shape"].str.extract(r"\((\d+)", expand=False).astype(float).sum()))
        lab = R[R.get("n", pd.Series(dtype=float)).notna()] if "n" in R else R.iloc[0:0]
        out("")
        out("[labels] 识别出 vin+时间 的数组=%d 个。按修改时间:" % len(lab))
        out("   修改时间 | 事件数 VIN | 时间范围 | 含0920(偏移) | 其中有视频/有ch1 | 视频事件被覆盖 | 路径")
        for _, x in lab.drop_duplicates(["n", "vins", "tmin"]).head(20).iterrows():
            out("   %s | %6d %4d | %s~%s | %4d(%s) | %4d/%4d | %4d | %s" % (
                x.mtime[:10], x.n, x.vins, str(x.tmin)[:10], str(x.tmax)[:10], x.in0920, x.sh0920,
                x.hasvid, x.hasvid_ch1, x.vid_found, (x.path[-50:] + (":" + x.key if x.key else ""))))
            out("        首行: %s" % x.get("sample", "")[:130])
        err = R[R.get("err", pd.Series(dtype=str)).notna()] if "err" in R else R.iloc[0:0]
        out("   读取失败=%d" % len(err))
    if events:
        A = pd.concat(events).dropna(subset=["sec"]).drop_duplicates(["vin", "sec"])
        A.to_csv(OUT_DIR + r"\all_npy_events.csv", index=False, encoding="utf-8-sig")
        out("")
        out("[合并去重] 全部npy事件=%d  VIN=%d  时间 %s ~ %s" % (len(A), A.vin.nunique(),
            pd.to_datetime(A.sec.min(), unit="s"), pd.to_datetime(A.sec.max(), unit="s")))
        out("   按月: " + "  ".join("%s:%d" % (k, v) for k, v in pd.to_datetime(A.sec, unit="s").dt.strftime("%y%m").value_counts().sort_index().items()))
        n9, s9 = match_count(e9, A[["vin", "sec"]], MATCH_0920_S)
        nv, sv = match_count(vref, A[["vin", "sec"]], MATCH_VIDEO_S)
        out("   0920 在其中=%d/%d(%s)   视频事件在其中=%d/%d(%s)" % (n9, len(e9), s9, nv, len(vref), sv))
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
