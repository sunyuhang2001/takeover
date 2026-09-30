# -*- coding: utf-8 -*-
# 16_gantry_locate.py v1 : 用经纬度判断“接管时有路口在录像”的事件是否就在那个路口（只读）
#   路口坐标: (a) 同车对上龙门架案例的事件, 接管时刻位置的中位数; (b) 0920 cross_name1 与路口同名的事件位置
#   [2] 对“接管时有路口在录像”的事件: 算车到该路口的距离 -> 很可能拍到(<=150m) / 附近(<=500m) / 不在该路口
#   [3] 目录名无 VIN 的龙门架案例: 用录像时段 + 路口位置反找附近事件(<=150m, 时间重叠)
# 输入: 12 的 事件资产表.csv / 事件资产表_2025.csv, 14 的 gantry_videos.csv
# 用法: python 16_gantry_locate.py
import os, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "16_gantry_locate", "v1"
BASE = r"D:\takeover_audit"
IN12 = BASE + r"\12_verify"
IN14 = BASE + r"\14_fields"
OUT_DIR = BASE + r"\16_gantry"
NEAR, MID, PAD = 150, 500, 30


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
    t = pd.to_datetime(pd.Series(s), errors="coerce")
    return ((t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("float")


def dist(la1, lo1, la2, lo2):
    return np.hypot((np.asarray(la1, float) - la2) * 111320, (np.asarray(lo1, float) - lo2) * 111320 * np.cos(np.radians(31.3)))


def norm(x):
    """路口名归一: 去空格, 两条路名排序后拼接, 便于 A-B 与 B-A 对上"""
    x = re.sub(r"\s+", "", str(x))
    m = re.match(r"^(.+?路)-(.+?路)", x)
    return "-".join(sorted(m.groups())) if m else x


def main():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))
    U = pd.read_csv(IN12 + r"\事件资产表.csv", dtype={"vin": str}, encoding="utf-8-sig"); U["表"] = "主表"
    U25 = pd.read_csv(IN12 + r"\事件资产表_2025.csv", dtype={"vin": str}, encoding="utf-8-sig"); U25["表"] = "2025"
    E = pd.concat([U, U25], ignore_index=True)
    E["等级"] = np.where(E["表"] == "2025", "2025-" + E["类别"].str[0], E["类别"].str[0])
    E["sec"] = to_sec(E["事件时间"])
    for c in ("路侧_龙门架路口(同VIN)", "路侧_同时段龙门架路口", "cross_name1"):
        E[c] = E[c].fillna("").astype(str).replace("nan", "") if c in E.columns else ""
    G = pd.read_csv(IN14 + r"\gantry_videos.csv", dtype={"case_vin": str}, encoding="utf-8-sig")
    G["key"] = G["inter"].map(norm)
    G["dir"] = G["path"].map(os.path.dirname)
    out("事件=%d (有经纬度=%d)  龙门架 mp4=%d  路口=%d" % (len(E), E["lat"].notna().sum(), len(G), G["key"].nunique()))

    # ---------------- 1. 路口坐标 ----------------
    pts = []
    a = E[(E["路侧_龙门架路口(同VIN)"] != "") & E["lat"].notna()]
    for _, r in a.iterrows():
        for it in r["路侧_龙门架路口(同VIN)"].split("/"):
            pts.append((norm(it), r["lat"], r["lon"], "同车案例"))
    b = E[(E["cross_name1"] != "") & E["lat"].notna()]
    keys = set(G["key"])
    for _, r in b.iterrows():
        k = norm(r["cross_name1"])
        if k in keys:
            pts.append((k, r["lat"], r["lon"], "0920路口名"))
    P = pd.DataFrame(pts, columns=["key", "lat", "lon", "src"])
    C = P.groupby("key").agg(lat=("lat", "median"), lon=("lon", "median"), n=("lat", "size"),
                             n同车=("src", lambda s: (s == "同车案例").sum())).reset_index()
    C["离散m"] = [float(np.median(dist(g.lat, g.lon, c.lat, c.lon))) for c in C.itertuples() for g in [P[P.key == c.key]]]
    C.to_csv(OUT_DIR + r"\intersections.csv", index=False, encoding="utf-8-sig")
    out("")
    out("[1] 路口坐标: 龙门架路口=%d  定出坐标=%d" % (G["key"].nunique(), len(C)))
    for c in C.sort_values("n", ascending=False).itertuples():
        out("    %-20s 点=%3d(同车%2d)  位置离散中位=%5.0fm  (%.5f, %.5f)" % (c.key[:20], c.n, c.n同车, c.离散m, c.lat, c.lon))
    miss = sorted(keys - set(C.key))
    if miss:
        out("    未定出坐标的路口: " + "  ".join(miss))
    cd = {r.key: (r.lat, r.lon) for r in C.itertuples()}

    # ---------------- 2. 接管时有路口在录像的事件 ----------------
    gs0, gs1 = G["s0"].values, G["s1"].values
    rows = []
    for _, r in E[E["路侧_同时段龙门架路口"] != ""].iterrows():
        on = G[(gs0 <= r["sec"] + PAD) & (gs1 >= r["sec"] - PAD)]
        for k, g in on.groupby("key"):
            same = bool(r["路侧_龙门架路口(同VIN)"]) and k in {norm(x) for x in r["路侧_龙门架路口(同VIN)"].split("/")}
            d = float(dist(r["lat"], r["lon"], *cd[k])) if (k in cd and pd.notna(r["lat"])) else np.nan
            lab = "无坐标" if np.isnan(d) else ("很可能拍到" if d <= NEAR else ("在附近" if d <= MID else "不在该路口"))
            rows.append(dict(event_key=r["event_key"], 等级=r["等级"], 路口=k, 距离m=round(d) if not np.isnan(d) else None,
                             判断=lab, 同车案例=same, 录像段数=len(g)))
    R = pd.DataFrame(rows)
    R.to_csv(OUT_DIR + r"\overlap_events.csv", index=False, encoding="utf-8-sig")
    out("")
    out("[2] 接管时有路口在录像的事件=%d (事件-路口对=%d)" % (R.event_key.nunique() if len(R) else 0, len(R)))
    if len(R):
        best = R.sort_values("距离m").drop_duplicates("event_key")
        out("    按事件取最近路口: " + "  ".join("%s:%d" % (a_, b_) for a_, b_ in best["判断"].value_counts().items()))
        out("    其中本来就是同车案例的: %d ; 新增“很可能拍到”(非同车案例): %d" % (
            best["同车案例"].sum(), ((best["判断"] == "很可能拍到") & ~best["同车案例"]).sum()))
        out("    按等级(很可能拍到/事件): " + "  ".join("%s:%d/%d" % (lv, (g["判断"] == "很可能拍到").sum(), len(g)) for lv, g in best.groupby("等级")))
        out("    距离分布(m): " + "  ".join("%s:%d" % (a_, b_) for a_, b_ in pd.cut(best["距离m"], [-1, 50, 150, 500, 2000, 1e7]).value_counts().sort_index().items()))

    # ---------------- 3. 目录名无 VIN 的案例反找事件 ----------------
    cases = G.groupby("dir").agg(key=("key", "first"), vin=("case_vin", "first"), s0=("s0", "min"), s1=("s1", "max"), n=("path", "size")).reset_index()
    nov = cases[cases["vin"].fillna("").astype(str).str.len() < 17]
    hits = []
    Ep = E[E["lat"].notna()]
    for c in nov.itertuples():
        if c.key not in cd:
            continue
        m = Ep[(Ep["sec"] >= c.s0 - PAD) & (Ep["sec"] <= c.s1 + PAD)]
        if len(m):
            d = dist(m["lat"], m["lon"], *cd[c.key])
            for (_, r), dd in zip(m.iterrows(), d):
                if dd <= NEAR:
                    hits.append(dict(案例=os.path.basename(c.dir), 路口=c.key, event_key=r["event_key"], 等级=r["等级"], 距离m=round(float(dd))))
    Hh = pd.DataFrame(hits)
    Hh.to_csv(OUT_DIR + r"\novin_cases_match.csv", index=False, encoding="utf-8-sig")
    out("")
    out("[3] 目录名无 VIN 的案例=%d (其中路口有坐标=%d) ; 反找到 <=%dm 的事件: 案例=%d 事件=%d" % (
        len(nov), nov["key"].isin(cd.keys()).sum(), NEAR, Hh["案例"].nunique() if len(Hh) else 0, Hh["event_key"].nunique() if len(Hh) else 0))
    if len(Hh):
        out("    按等级: " + "  ".join("%s:%d" % (a_, b_) for a_, b_ in Hh.drop_duplicates("event_key")["等级"].value_counts().items()))
    out("")
    out("  输出: %s\\intersections.csv ; overlap_events.csv ; novin_cases_match.csv" % OUT_DIR)
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))
    out("=== END %s %s  用时%.0fs ===" % (NAME, VERSION, time.time() - t0))


if __name__ == "__main__":
    main()
