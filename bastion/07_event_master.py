# -*- coding: utf-8 -*-
# 07_event_master.py : 事件主表 + V/T/R/D 组合计数（只读 02/03/05 的输出，不再读原始数据）
#   V=有ch1(前视)的自车视频  Vgrade=三通道/有ch1/无ch1/无视频  T=自车轨迹  Rv=龙门架视频  Rj=participant json  D=原因描述(0920)
#   可复现 U = (T 且 R) 或 V 或 Rv
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "07_event_master", "v2"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\07_master"
RADIUS_M = 200      # 事件位置离路口多近算"在路侧覆盖内"
PJ_INTER = "曹安公路-墨玉路"   # participant json 设备所在路口（03 输出里的路名）
HALF = 30
MERGE_S = 60


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


def ts(x):
    return (pd.to_datetime(x) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)


def norm_inter(s):
    if not isinstance(s, str) or "-" not in s:
        return ""
    parts = [p.strip() for p in re.split(r"[-－—]", s) if p.strip()]
    return "-".join(sorted(parts[:2]))


def dist_m(lat1, lon1, lat2, lon2):
    k = 111320.0
    return np.hypot((np.asarray(lat1) - lat2) * k, (np.asarray(lon1) - lon2) * k * np.cos(np.radians(31.28)))


def locate(ev, H):
    """给每个事件找事件时刻最近的轨迹点(±30s)，返回 lat, lon"""
    h = H[["vin", "sec", "lat", "lon", "shift"]]
    m = ev[["eid", "vin", "t_sec", "T_shift"]].merge(h, left_on=["vin", "T_shift"], right_on=["vin", "shift"])
    m = m[(m.sec - m.t_sec).abs() <= HALF]
    m["ad"] = (m.sec - m.t_sec).abs()
    best = m.sort_values("ad").drop_duplicates("eid").set_index("eid")
    return best.lat.reindex(ev.eid).values, best.lon.reindex(ev.eid).values


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))

    ve = pd.read_csv(BASE + r"\05_traj\video_events_T.csv", dtype={"vin": str, "T_shift": str, "chans": str})
    e9 = pd.read_csv(BASE + r"\05_traj\events0920_T.csv", dtype={"vin": str, "T_shift": str}, low_memory=False)
    H = pd.read_csv(BASE + r"\05_traj\event_hits.csv", dtype={"vin": str, "shift": str, "dm": str})
    RS = pd.read_csv(BASE + r"\05_traj\roadside_switches_0.csv", dtype={"vin": str, "dm": str})
    tf = pd.read_csv(BASE + r"\05_traj\traj_files.csv", dtype=str)
    gv = pd.read_csv(BASE + r"\03_roadside\gantry_videos.csv", dtype=str)
    pjf = pd.read_csv(BASE + r"\03_roadside\participant_files.csv", dtype=str)
    seg = pd.read_csv(BASE + r"\03_roadside\participant_segments.csv")
    for d in (ve, e9):
        d["T_shift"] = d.T_shift.fillna("").astype(str).replace({"0.0": "0"})
    H["shift"] = H["shift"].astype(str).replace({"0.0": "0"})

    # ---------- 事件全集 ----------
    e9["eid"] = ["E%04d" % i for i in range(len(e9))]
    e9["src"] = "0920"
    e9["D"] = e9.has_desc.astype(str).isin(["True", "1", "1.0"]).astype(int)
    e9["V"] = e9.veid.notna().astype(int)
    e9 = e9.merge(ve[["veid", "chans"]], on="veid", how="left")
    off = ve[ve.in0920 == 0].copy()
    off["eid"] = ["V%04d" % i for i in range(len(off))]
    off["src"] = "video"
    off["D"] = 0; off["V"] = 1; off["cross_name1"] = ""
    cols = ["eid", "src", "vin", "t_sec", "V", "T", "T_shift", "D", "chans", "cross_name1"]
    ev = pd.concat([e9[cols], off[cols]], ignore_index=True)
    # ch1=车头前方 ch2=座舱 ch3=踏板：至少要有 ch1 才算"有视频"，三个都有最好
    ch = ev.chans.fillna("").astype(str).str.replace(".0", "", regex=False)
    ev["chans"] = ch
    ev["V_any"] = (ch != "").astype(int)
    ev["V"] = ch.str.contains("1").astype(int)
    ev["Vgrade"] = np.select([ch.str.contains("1") & ch.str.contains("2") & ch.str.contains("3"),
                              ch.str.contains("1"), ch != ""], ["三通道", "有ch1", "无ch1"], "无视频")
    ev["lat"], ev["lon"] = locate(ev, H)

    # ---------- 路口坐标：用 0920 事件(有cross_name1且定位成功)反推 ----------
    ev["xn"] = ev.cross_name1.apply(norm_inter)
    x = ev[(ev.xn != "") & ev.lat.notna()].groupby("xn").agg(lat=("lat", "median"), lon=("lon", "median"), n=("eid", "size"))
    x = x[x.n >= 3]
    pjm = pjf.copy(); pjm["lat"] = pd.to_numeric(pjm.lat, errors="coerce"); pjm["lon"] = pd.to_numeric(pjm.lon, errors="coerce")
    pj_lat, pj_lon = pjm.lat.median(), pjm.lon.median()
    out("路口坐标(由0920事件反推, >=3个事件) = %d个;  participant设备中心 = %.5f, %.5f" % (len(x), pj_lat, pj_lon))

    # ---------- 自车轨迹里的路侧接管事件（只认 drive_mode/drivemode 列）----------
    okfiles = set(tf[tf.dm_col.fillna("").str.lower().isin(["drive_mode", "drivemode"])].file.astype(str))
    RS = RS[RS.file.astype(str).isin(okfiles)].copy()
    RS = RS.sort_values(["vin", "sec"])
    RS = RS[~(RS.groupby("vin").sec.diff() < MERGE_S).fillna(False).values]
    # 已在 0920/视频事件里的去掉
    known = ev[["vin", "t_sec"]]
    mm = RS.merge(known, on="vin", how="left")
    dup = mm[(mm.sec - mm.t_sec).abs() <= MERGE_S][["vin", "sec"]].drop_duplicates()
    RS = RS.merge(dup, on=["vin", "sec"], how="left", indicator=True)
    RS = RS[RS._merge == "left_only"]
    rsev = pd.DataFrame({"eid": ["R%04d" % i for i in range(len(RS))], "src": "traj_switch", "vin": RS.vin.values,
                         "t_sec": RS.sec.values, "V": 0, "V_any": 0, "Vgrade": "无视频", "T": 1, "T_shift": "0", "D": 0, "chans": "",
                         "cross_name1": "", "lat": pd.to_numeric(RS.lat, errors="coerce").values,
                         "lon": pd.to_numeric(RS.lon, errors="coerce").values, "xn": ""})
    ev = pd.concat([ev, rsev], ignore_index=True)

    # ---------- R 标志 ----------
    g = gv.dropna(subset=["start", "end"]).drop_duplicates(["cam", "start", "end"]).copy()
    g["s"], g["e"] = ts(g.start), ts(g.end)
    g["xn"] = g.inter.apply(norm_inter)
    g = g.merge(x[["lat", "lon"]].rename(columns={"lat": "ilat", "lon": "ilon"}), left_on="xn", right_index=True, how="left")
    pjn = norm_inter(PJ_INTER)
    g.loc[(g.xn == pjn) & g.ilat.isna(), ["ilat", "ilon"]] = [pj_lat, pj_lon]
    seg["s"], seg["e"] = ts(seg.start), ts(seg.end)
    Rv, Rv_inter, Rj = [], [], []
    for r in ev.itertuples():
        c = g[(g.s <= r.t_sec + HALF) & (g.e >= r.t_sec - HALF)]
        hit = ""
        if len(c):
            near = (c.case_vin == r.vin) | ((c.xn != "") & (c.xn == r.xn))
            if pd.notna(r.lat):
                near |= pd.Series(dist_m(c.ilat, c.ilon, r.lat, r.lon) <= RADIUS_M, index=c.index).fillna(False)
            if near.any():
                hit = c[near].inter.iloc[0] if isinstance(c[near].inter.iloc[0], str) else "?"
        Rv.append(int(hit != "")); Rv_inter.append(hit)
        inseg = ((seg.s <= r.t_sec) & (seg.e >= r.t_sec)).any()
        nearpj = pd.notna(r.lat) and dist_m(pj_lat, pj_lon, r.lat, r.lon) <= RADIUS_M
        Rj.append(int(bool(inseg and nearpj)))
    ev["Rv"], ev["Rv_inter"], ev["Rj"] = Rv, Rv_inter, Rj
    ev["R"] = ((ev.Rv == 1) | (ev.Rj == 1)).astype(int)
    ev["U"] = (((ev["T"] == 1) & (ev.R == 1)) | (ev.V == 1) | (ev.Rv == 1)).astype(int)
    # 路侧接管事件只保留真正在路侧覆盖内的
    ev = ev[~((ev.src == "traj_switch") & (ev.R == 0))]
    ev["t"] = pd.to_datetime(ev.t_sec, unit="s")

    def cat(r):
        if r.V and r["T"]:
            return "A 视频+轨迹+原因" if r.D else "B 视频+轨迹(无原因)"
        if r.V:
            return "C 仅视频"
        if r["T"]:
            return "D2 轨迹+路侧" if r.R else "D1 仅自车轨迹"
        if r.V_any:
            return "F 仅无ch1视频(不可用)"
        return "E 仅原因"
    ev["cat"] = ev.apply(cat, axis=1)
    ev.to_csv(OUT_DIR + r"\event_master.csv", index=False, encoding="utf-8-sig")
    try:
        ev.drop(columns=["xn"]).to_excel(OUT_DIR + r"\事件主表.xlsx", index=False)
    except Exception as e:
        out("xlsx 写出失败: %r" % e)

    # ---------- 汇总 ----------
    out("")
    out("事件总数=%d  (0920=%d, 清单外视频=%d, 路侧时段内轨迹接管=%d)  定位成功=%d" % (
        len(ev), (ev.src == "0920").sum(), (ev.src == "video").sum(), (ev.src == "traj_switch").sum(), ev.lat.notna().sum()))
    out("")
    out("分类                     事件  可复现U  有路侧R(Rv/Rj)  时间范围")
    for c, d in ev.groupby("cat"):
        out("  %-22s %5d  %5d   %4d (%d/%d)   %s ~ %s" % (c, len(d), d.U.sum(), d.R.sum(), d.Rv.sum(), d.Rj.sum(),
                                                       d.t.min().strftime("%Y-%m-%d"), d.t.max().strftime("%Y-%m-%d")))
    out("")
    out("分类 x 视频等级:")
    ct = pd.crosstab(ev["cat"], ev.Vgrade)
    out("  %-22s " % "" + " ".join("%6s" % c for c in ct.columns))
    for idx, r in ct.iterrows():
        out("  %-22s " % idx + " ".join("%6d" % v for v in r.values))
    nc1 = ev[ev.Vgrade == "无ch1"]
    out("有视频但无ch1(不算V)=%d: 有轨迹=%d 有路侧=%d 有原因=%d  通道: %s" % (
        len(nc1), nc1["T"].sum(), nc1.R.sum(), nc1.D.sum(),
        " ".join("ch%s:%d" % (k, v) for k, v in nc1.chans.value_counts().items())))
    out("")
    out("V T R D 组合 (V=有ch1):")
    comb = ev.groupby(["V", "T", "R", "D"]).size().reset_index(name="n").sort_values("n", ascending=False)
    for r in comb.itertuples():
        out("  V=%d T=%d R=%d D=%d : %d" % (r.V, r[2], r.R, r.D, r.n))
    out("")
    v = ev[ev.V == 1]
    va = ev[ev.V_any == 1]
    out("视频事件 通道组合 有轨迹/总数:  " + "  ".join("ch%s:%d/%d" % (k, d["T"].sum(), len(d)) for k, d in va.groupby("chans")))
    out("有路侧的事件 按路口(Rv): " + "  ".join("%s:%d" % (k, n) for k, n in ev[ev.Rv == 1].Rv_inter.value_counts().head(8).items()))
    out("有路侧的事件 按来源: " + "  ".join("%s:%d" % (k, n) for k, n in ev[ev.R == 1].src.value_counts().items()))
    c_only = ev[ev["cat"] == "C 仅视频"]
    out("仅视频事件: VIN也在0920里的=%d/%d   按月: %s" % (
        c_only.vin.isin(set(e9.vin)).sum(), len(c_only),
        "  ".join("%s:%d" % (k, n) for k, n in c_only.t.dt.strftime("%y%m").value_counts().sort_index().items())))
    x.to_csv(OUT_DIR + r"\intersections.csv", encoding="utf-8-sig")
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
