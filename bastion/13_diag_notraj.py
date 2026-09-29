# -*- coding: utf-8 -*-
# 13_diag_notraj.py v1 : 诊断"有视频但无轨迹"的事件（只读，读 12 的事件资产表.csv）
#   12 v4 结果: 有视频无轨迹=324，其中当天该车有表格轨迹=322，±30s 内有不足20s的片段=319
#   这里判断原因是 (a)轨迹采样稀疏(非逐秒)  (b)时间没对齐(轨迹在更远处)  (c)轨迹确实只覆盖一小段
#   做法：重新读这些事件涉及的原始轨迹文件(只取相关VIN)，在 ±30/±120/±600s 和视频片段时段内统计点数、采样间隔、最大空档、最近接管跳变
# 用法: python 13_diag_notraj.py
import os, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "13_diag_notraj", "v1"
BASE = r"D:\takeover_audit"
SRC = BASE + r"\12_verify\事件资产表.csv"
OUT_DIR = BASE + r"\13_diag"
SHIFTS = (0, 8 * 3600, -8 * 3600)
VC = {"vin": ["vin", "vin_x", "t2.vin"], "t": ["position_time", "positiontime", "dis_engage_time", "time", "timestamp",
      "position_time_sql", "gps_time"], "dm": ["drive_mode", "drivemode", "drive_mode_switch"],
      "lat": ["latitude", "lat"], "lon": ["longitude", "lon", "lng"]}


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
    s = pd.Series(s)
    if s.dtype.kind == "M":
        return ((s - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("float")
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.9:
        med = num.median()
        x = num / 1e9 if med > 1e17 else num / 1e6 if med > 1e14 else num / 1e3 if med > 1e11 else num
        return x + 8 * 3600
    try:
        t = pd.to_datetime(s.astype(str), errors="coerce", infer_datetime_format=True)
    except TypeError:
        t = pd.to_datetime(s.astype(str), errors="coerce", format="mixed")
    return ((t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("float")


pick = lambda cols, keys: next((c for k in keys for c in cols if str(c).strip().lower() == k), None)


def load(p, vins):
    """读一个原始轨迹文件中指定 VIN 的 (vin, sec, dm)"""
    parts = []
    if p.lower().endswith(".csv"):
        hdr = enc = None
        for enc in ("utf-8-sig", "gbk"):
            try:
                hdr = pd.read_csv(p, nrows=0, encoding=enc).columns; break
            except UnicodeDecodeError:
                continue
        cv, ct, cd = (pick(hdr, VC[x]) for x in ("vin", "t", "dm"))
        it = pd.read_csv(p, usecols=[c for c in (cv, ct, cd) if c], dtype=str, chunksize=1_000_000, encoding=enc, on_bad_lines="skip")
    else:
        df = pd.read_excel(p, dtype=str)
        cv, ct, cd = (pick(df.columns, VC[x]) for x in ("vin", "t", "dm"))
        it = [df]
    for ch in it:
        v = ch[cv].astype(str).str.upper().str.strip()
        ch = ch[v.isin(vins)]
        if len(ch):
            parts.append(pd.DataFrame({"vin": ch[cv].astype(str).str.upper().str.strip(), "sec": to_sec(ch[ct]),
                                       "dm": pd.to_numeric(ch[cd], errors="coerce") if cd else np.nan}).dropna(subset=["sec"]))
    return pd.concat(parts) if parts else pd.DataFrame(columns=["vin", "sec", "dm"]), cd


def main():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  self=%s ===" % (NAME, VERSION, selfcheck()))
    U = pd.read_csv(SRC, dtype={"vin": str}, encoding="utf-8-sig")
    U["sec"] = to_sec(pd.to_datetime(U["事件时间"]))
    for c in ("v_start", "v_end"):
        U[c + "_s"] = to_sec(pd.to_datetime(U[c], errors="coerce")) if c in U.columns else np.nan
    has_v = U["veid"].fillna(-1) >= 0
    nt = U[has_v & ~U["有轨迹"].astype(bool)].copy()
    ok = U[has_v & U["有轨迹"].astype(bool)].copy()
    out("资产表事件=%d  有视频=%d  有视频无轨迹=%d  有视频有轨迹=%d" % (len(U), has_v.sum(), len(nt), len(ok)))
    out("  无轨迹事件 类别: " + "  ".join("%s:%d" % (a[:1], b) for a, b in nt["类别"].value_counts().items()))
    out("  无轨迹事件 ±30s覆盖秒: " + "  ".join("%s:%d" % (a, b) for a, b in pd.cut(nt["轨迹_秒"], [-1, 0, 5, 10, 15, 19]).value_counts().sort_index().items()))
    out("  无轨迹事件 采样(中位数间隔s): " + "  ".join("%s:%d" % (a, b) for a, b in nt["轨迹_采样s"].round().value_counts(dropna=False).head(8).items()))
    out("  视频片段时长(s): " + "  ".join("%s:%d" % (a, b) for a, b in ((nt.v_end_s - nt.v_start_s).round(-1)).value_counts().head(6).items()))

    # 涉及的原始文件(全部源)
    rx = re.compile(r"(.+?)\((\d+)\)(?:; |$)")
    files = {}
    for s in nt["轨迹_全部源"].fillna(""):
        for f, n in rx.findall(s):
            files[f.strip()] = files.get(f.strip(), 0) + 1
    out("  涉及原始轨迹文件=%d (按事件数):" % len(files))
    for f, n in sorted(files.items(), key=lambda x: -x[1])[:10]:
        out("     %4d  %s" % (n, f))

    vins = set(nt.vin)
    rows = []
    for k, (f, _) in enumerate(sorted(files.items(), key=lambda x: -x[1]), 1):
        if not os.path.exists(f):
            out("  [缺失] " + f); continue
        try:
            T, cd = load(f, vins)
        except Exception as e:
            out("  [读失败] %s %r" % (f, e)); continue
        print("  ... %d/%d %s 点=%d  %.0fs" % (k, len(files), os.path.basename(f), len(T), time.time() - t0))
        if not len(T):
            continue
        Tg = {v: g.drop_duplicates("sec").sort_values("sec") for v, g in T.groupby("vin")}
        # 该文件的时区偏移：让 ±600s 内点最多的那个
        best, bn = 0, -1
        for sh in SHIFTS:
            n = sum(int(((Tg[r.vin].sec.values + sh - r.sec) ** 2 <= 600 ** 2).sum()) for r in nt.itertuples() if r.vin in Tg)
            if n > bn:
                best, bn = sh, n
        for r in nt.itertuples():
            g = Tg.get(r.vin)
            if g is None:
                continue
            s = g.sec.values + best
            d = s - r.sec
            w600 = np.abs(d) <= 600
            if not w600.any():
                continue
            s6 = s[w600]
            dm6 = g.dm.values[w600]
            gap = np.diff(np.concatenate([[r.sec - 120], s[np.abs(d) <= 120], [r.sec + 120]]))
            sw = np.where((dm6[:-1] == 1) & (dm6[1:] == 0))[0] if cd else np.array([], int)
            vs, ve = r.v_start_s, r.v_end_s
            rows.append(dict(event_key=r.event_key, 类别=r.类别[:1], file=f, shift_h=best // 3600,
                             n30=int((np.abs(d) <= 30).sum()), n120=int((np.abs(d) <= 120).sum()), n600=int(w600.sum()),
                             n_clip=int(((s >= vs - 30) & (s <= ve + 30)).sum()) if pd.notna(vs) else -1,
                             dt_med=float(np.median(np.diff(s6))) if len(s6) > 1 else np.nan,
                             gap120_max=float(gap.max()), 最近点s=float(d[np.argmin(np.abs(d))]),
                             span600=float(s6.max() - s6.min()),
                             跳变数600=len(sw), 最近跳变s=float((s6[sw + 1] - r.sec)[np.argmin(np.abs(s6[sw + 1] - r.sec))]) if len(sw) else np.nan))
    R = pd.DataFrame(rows)
    R.to_csv(OUT_DIR + r"\notraj_diag.csv", index=False, encoding="utf-8-sig")
    if not len(R):
        out("无可诊断记录"); return
    # 每个事件取 ±600s 内点最多的文件
    B = R.sort_values(["n600", "n30"], ascending=False).drop_duplicates("event_key")
    out("")
    out("[诊断] 可诊断事件=%d (±600s 内有轨迹点)" % len(B))
    out("  采样间隔(±600s 中位数,s): " + "  ".join("%s:%d" % (a, b) for a, b in pd.cut(B.dt_med, [0, 1.5, 3, 5, 10, 30, 1e9]).value_counts().sort_index().items()))
    out("  ±600s 内轨迹跨度(s): " + "  ".join("%s:%d" % (a, b) for a, b in pd.cut(B.span600, [-1, 30, 60, 120, 300, 600, 1200]).value_counts().sort_index().items()))
    out("  ±120s 最大空档(s): " + "  ".join("%s:%d" % (a, b) for a, b in pd.cut(B.gap120_max, [0, 5, 10, 30, 60, 120, 240]).value_counts().sort_index().items()))
    out("  点数: ±30s 中位=%d  ±120s 中位=%d  视频片段±30s 中位=%d" % (B.n30.median(), B.n120.median(), B[B.n_clip >= 0].n_clip.median()))
    out("  视频片段时段(±30s)内点>=20 的事件=%d  ±120s 内点>=20=%d" % ((B.n_clip >= 20).sum(), (B.n120 >= 20).sum()))
    out("  ±600s 内有 drive_mode 1->0 跳变的事件=%d ; 最近跳变距事件(s): %s" % (B.最近跳变s.notna().sum(),
        "  ".join("%s:%d" % (a, b) for a, b in pd.cut(B.最近跳变s.abs(), [-1, 30, 60, 120, 300, 600]).value_counts().sort_index().items())))
    out("  按文件(事件数 / 采样中位s / ±30s点中位):")
    for f, g in B.groupby("file"):
        out("     %4d  %5.1f  %4d  %s" % (len(g), g.dt_med.median(), g.n30.median(), f))
    out("  样例(前15):  类别 | ±30s点 | ±120s点 | 片段内点 | 采样s | 最大空档 | 最近点s | 最近跳变s | 文件")
    for r in B.head(15).itertuples():
        out("    %s | %d | %d | %d | %.1f | %.0f | %+.0f | %s | %s" % (r.类别, r.n30, r.n120, r.n_clip, r.dt_med, r.gap120_max, r.最近点s,
            "" if pd.isna(r.最近跳变s) else "%+.0f" % r.最近跳变s, os.path.basename(r.file)))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))
    out("=== END %s %s  用时%.0fs ===" % (NAME, VERSION, time.time() - t0))


if __name__ == "__main__":
    main()
