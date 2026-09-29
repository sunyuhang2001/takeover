# -*- coding: utf-8 -*-
# 11_event_lists.py : 三份事件清单补全（只读）
#  A) dis_joined3_30s/60s 比 0920 多出来的事件是什么（有没有人工标签/原因）
#  B) 从 switch 导出数据（含 drive_mode_switch）按 VIN 找状态切换 = 全部脱离（补 NPY 缺的 2024 年）
#     用 0920 确定哪个方向是"自动->人工"，再与视频事件、关键脱离(critical_label*.npy)比对
# 依赖 01/02/04/10 的输出；需要 pandas、numpy、openpyxl
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "11_event_lists", "v2"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\11_lists"
TOL = 2          # 与 0920 的时间容差(s)
VTOL = 60        # 与视频片段中点的容差(s)


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


def near(a, b, tol, shifts=(0,)):
    """a,b: DataFrame(vin,sec)。返回 (a 中能在 b 找到的布尔Series, 用的偏移)"""
    best = (pd.Series(False, index=a.index), 0)
    if not len(a) or not len(b):
        return best
    bb = b.dropna().sort_values("sec")[["vin", "sec"]].rename(columns={"sec": "bsec"})
    for sh in shifts:
        aa = a.dropna(subset=["sec"]).assign(sec=lambda d: d.sec + sh).reset_index().sort_values("sec")
        m = pd.merge_asof(aa, bb, left_on="sec", right_on="bsec", by="vin", direction="nearest")
        ok = pd.Series(((m.sec - m.bsec).abs() <= tol).values, index=m["index"]).reindex(a.index).fillna(False)
        if ok.sum() > best[0].sum():
            best = (ok, sh)
    return best


def months(sec):
    return "  ".join("%s:%d" % (k, v) for k, v in pd.to_datetime(sec, unit="s").dt.strftime("%y%m").value_counts().sort_index().items())


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

    src = fi[fi.name.str.contains("脱离事件汇总") & fi.name.str.lower().str.endswith(".xlsx")].sort_values("mtime").path.iloc[0]
    e9raw = pd.read_excel(src, sheet_name=0)
    e9 = pd.DataFrame({"vin": e9raw["vin"].astype(str).str.upper().str.strip(), "sec": to_sec(e9raw["disengage_time"])})
    ve = pd.read_csv(BASE + r"\02_ego_video\video_events.csv", dtype={"vin": str, "chans": str})
    ve = ve[ve.vin.notna()].reset_index(drop=True)
    V = pd.DataFrame({"vin": ve.vin, "sec": to_sec(ve.mid)})
    ch1 = ve.chans.fillna("").astype(str).str.contains("1")

    # ---------------- A) dis_joined3 多出的事件 ----------------
    out("[A] dis_joined3 系列 vs 0920(%d)" % len(e9))
    dj = fi[fi.name.str.lower().str.match(r"dis_joined3.*\.(xlsx|csv)$")].sort_values("size_bytes", ascending=False)
    dj = dj.drop_duplicates("name")
    for p in dj.path.head(3):
        try:
            d = pd.read_csv(p, low_memory=False) if p.lower().endswith(".csv") else pd.read_excel(p)
            vc = next(c for c in d.columns if str(c).lower() in ("vin", "vin_x"))
            if "dis_id" in d.columns:
                g = d.groupby("dis_id")
                nt = g["disengage_time"].nunique()
                span = g["disengage_time"].apply(lambda s: (to_sec(s).max() - to_sec(s).min()))
                out("  %s  dis_id=%d  其中含多个disengage_time的=%d  (同一dis_id内最大时间差: <=1s:%d  <=60s:%d  >60s:%d)" % (
                    p[-50:], len(nt), (nt > 1).sum(), (span[nt > 1] <= 1).sum(), ((span > 1) & (span <= 60)).sum(), (span > 60).sum()))
                smp = d[d.dis_id.isin(nt[nt > 1].index[:1])].drop_duplicates("disengage_time")
                if len(smp):
                    out("    例: dis_id=%s  disengage_time 取值: %s" % (smp.dis_id.iloc[0], " / ".join(map(str, smp.disengage_time.head(4)))))
            ev = d.drop_duplicates([vc, "disengage_time"]).copy()
            ev["vin"] = ev[vc].astype(str).str.upper().str.strip()
            ev["sec"] = to_sec(ev.disengage_time)
            ev = ev.reset_index(drop=True)
            in9, _ = near(ev[["vin", "sec"]], e9, TOL)
            ex = ev[~in9.values]
            out("  %s  事件=%d  在0920=%d  多出=%d  VIN=%d" % (p[-55:], len(ev), in9.sum(), len(ex), ev.vin.nunique()))
            if len(ex):
                out("    多出事件按月: " + months(ex.sec))
                lab = [c for c in ("critical_engage", "video_avaliable", "road_type", "signal", "weather", "light",
                                   "ego_manuever", "target_type", "target_manuever", "relevant_position") if c in ex.columns]
                out("    多出事件各标签非空率: " + "  ".join("%s:%.0f%%" % (c, 100 * ex[c].notna().mean()) for c in lab))
                for c in lab[:3]:
                    out("      %s 取值: %s" % (c, " ".join("%s:%d" % (k, v) for k, v in ex[c].astype(str).value_counts().head(6).items())))
                # 多出的事件是不是 0920 事件的时间变体（同VIN、时间差<=60s）
                v60, _ = near(ex[["vin", "sec"]], e9, 60)
                out("    其中与0920同VIN且<=60s(疑似同一事件不同时间)=%d ; 有自车视频=%d" % (
                    v60.sum(), near(ex[["vin", "sec"]], V, VTOL)[0].sum()))
                ex.to_csv(OUT_DIR + "\\extra_" + os.path.basename(p) + ".csv", index=False, encoding="utf-8-sig")
        except Exception as e:
            out("  ERR %s %r" % (p[-50:], e))

    # ---------------- B) switch 导出 -> 全部脱离 ----------------
    cat = pd.read_csv(BASE + r"\04_tables\table_catalog.csv", dtype=str, keep_default_na=False)
    sw = cat[cat.cols.str.contains("drive_mode_switch") & cat.cols.str.contains(r"(?:^|,)vin(?:,|$)") &
             cat.cols.str.contains(r"(?:^|,)time(?:,|$)") & ~cat.path.str.lower().str.contains("takeover_audit")]
    sw = sw.drop_duplicates("path")
    sw = sw.assign(fname=sw.path.str.split("\\").str[-1]).drop_duplicates(["fname", "size_mb"])
    out("")
    out("[B] switch 导出文件=%d  %.1fGB" % (len(sw), pd.to_numeric(sw.size_mb, errors="coerce").sum() / 1024))
    parts, t0 = [], time.time()
    for i, p in enumerate(sw.path, 1):
        try:
            if p.lower().endswith(".csv"):
                d = pd.read_csv(p, usecols=lambda c: str(c).lower() in ("vin", "time", "drive_mode_switch", "latitude", "longitude"),
                                dtype=str, on_bad_lines="skip")
            else:
                d = pd.read_excel(p, usecols=lambda c: str(c).lower() in ("vin", "time", "drive_mode_switch", "latitude", "longitude"), dtype=str)
            d.columns = [str(c).lower() for c in d.columns]
            d["sec"] = to_sec(d["time"])
            d["vin"] = d.vin.str.upper().str.strip()
            parts.append(d[["vin", "sec", "drive_mode_switch", "latitude", "longitude"]].dropna(subset=["sec"]))
        except Exception as e:
            pass
        if i % 100 == 0:
            print("  ... %d/%d  %.0fs" % (i, len(sw), time.time() - t0))
    S = pd.concat(parts).drop_duplicates(["vin", "sec"]).sort_values(["vin", "sec"]).reset_index(drop=True)
    S["m"] = pd.to_numeric(S.drive_mode_switch, errors="coerce")
    out("    去重后点=%d  VIN=%d  时间 %s ~ %s  drive_mode_switch: %s" % (
        len(S), S.vin.nunique(), pd.to_datetime(S.sec.min(), unit="s"), pd.to_datetime(S.sec.max(), unit="s"),
        " ".join("%s:%d" % (k, v) for k, v in S.m.value_counts().head(5).items())))
    same = S.vin.eq(S.vin.shift(1))
    gap = S.sec - S.sec.shift(1)
    trans = S[same & S.m.ne(S.m.shift(1)) & S.m.notna() & S.m.shift(1).notna()].copy()
    trans["from"] = S.m.shift(1)[trans.index].values
    trans["gap_s"] = gap[trans.index].values
    trans["dir"] = trans["from"].astype(int).astype(str) + "->" + trans.m.astype(int).astype(str)
    out("    状态切换: " + "  ".join("%s:%d" % (k, v) for k, v in trans.dir.value_counts().items()) +
        "   (前后两点间隔中位 %.0fs)" % trans.gap_s.median())
    # 哪个方向对得上 0920
    best_dir, best_n, best_sh = None, -1, 0
    for dname, g in trans.groupby("dir"):
        ok, sh = near(e9, g[["vin", "sec"]], TOL, shifts=(0, 8 * 3600, -8 * 3600))
        out("    0920 与 %s 切换对得上=%d/%d (偏移%+dh)" % (dname, ok.sum(), len(e9), sh // 3600))
        if ok.sum() > best_n:
            best_dir, best_n, best_sh = dname, ok.sum(), sh
    D = trans[trans.dir == best_dir][["vin", "sec", "latitude", "longitude", "gap_s"]].copy()
    D["sec"] = D.sec - best_sh           # 统一成与 0920 相同的时间基准
    D = D.reset_index(drop=True)
    out("    => 取 %s 为'自动->人工'脱离。全部脱离=%d  VIN=%d  时间 %s ~ %s" % (
        best_dir, len(D), D.vin.nunique(), pd.to_datetime(D.sec.min(), unit="s"), pd.to_datetime(D.sec.max(), unit="s")))
    out("       按月: " + months(D.sec))
    D.to_csv(OUT_DIR + r"\all_disengagements_switch.csv", index=False, encoding="utf-8-sig")

    # 与视频、关键脱离、NPY全部脱离 比对
    okv, shv = near(V, D, VTOL, shifts=(0, 8 * 3600, -8 * 3600))
    out("")
    out("[C] 视频事件(%d, 有ch1=%d) 能在 switch 全部脱离里找到=%d (有ch1=%d)  偏移%+dh" % (
        len(V), ch1.sum(), okv.sum(), (okv & ch1).sum(), shv // 3600))
    npy = os.path.join(BASE, r"10_npy\all_npy_events.csv")
    crit_paths = fi[fi.name.str.lower().str.startswith("critical_label") & fi.ext.eq(".npy")].path.tolist()
    C = []
    for p in crit_paths:
        try:
            a = np.load(p, allow_pickle=True)
            df = pd.DataFrame(a)
            vc = next(c for c in df.columns if df[c].astype(str).str.match(r"^[A-HJ-NPR-Z0-9]{17}$").mean() > .8)
            tc = next(c for c in df.columns if c != vc and to_sec(df[c]).between(1.5e9, 1.9e9).mean() > .8)
            C.append(pd.DataFrame({"vin": df[vc].astype(str).str.upper(), "sec": to_sec(df[tc]), "src": os.path.basename(p)}))
        except Exception:
            pass
    if C:
        C = pd.concat(C).drop_duplicates(["vin", "sec"]).reset_index(drop=True)
        okc, _ = near(V, C[["vin", "sec"]], VTOL)
        out("    关键脱离(critical_label*.npy 合并)=%d  VIN=%d  时间 %s ~ %s ; 视频事件在其中=%d" % (
            len(C), C.vin.nunique(), pd.to_datetime(C.sec.min(), unit="s").date(), pd.to_datetime(C.sec.max(), unit="s").date(), okc.sum()))
    else:
        okc = pd.Series(False, index=V.index)
    # 视频事件归属
    vm = pd.to_datetime(V.sec, unit="s").dt.strftime("%y%m")
    tab = pd.DataFrame({"月": vm, "在switch全部脱离": okv, "在关键脱离": okc.values if len(okc) == len(V) else False})
    out("    视频事件按月: 总数 / 在switch全部脱离 / 在关键脱离")
    for mth, g in tab.groupby("月"):
        out("      %s  %4d / %4d / %4d" % (mth, len(g), g["在switch全部脱离"].sum(), g["在关键脱离"].sum()))
    ve.assign(in_switch=okv.values, in_critical=okc.values if len(okc) == len(V) else False).to_csv(
        OUT_DIR + r"\video_events_membership.csv", index=False, encoding="utf-8-sig")
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
