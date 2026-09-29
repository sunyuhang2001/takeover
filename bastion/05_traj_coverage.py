# -*- coding: utf-8 -*-
# 05_traj_coverage.py : 读所有轨迹表，只保留"事件附近"和"路侧覆盖时段+路口范围内"的点，
#                       判断每个视频事件 / 0920 事件有没有自车轨迹，以及路侧时段内有没有车和接管（只读）
# 依赖 02、03、04 的输出；需要 pandas、numpy、openpyxl
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "05_traj_coverage", "v1"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\05_traj"
HALF = 30          # 事件前后各 30s
T_MIN_SEC = 20     # 前后 30s 内至少 20 个不同秒有经纬度，算"有轨迹"
PAD = 60           # 收集数据时事件窗口再放宽 60s
SHIFTS = {"0": 0, "+8h": 8 * 3600, "-8h": -8 * 3600}   # 轨迹时间加上这个偏移后再和事件比
CHUNK = 1_000_000
BBOX_MARGIN = 0.005   # 路侧坐标范围外扩约 500m

VIN_COLS = ["vin", "vin_x", "t2.vin", "vin_y"]
TIME_COLS = ["position_time", "positiontime", "dis_engage_time", "time", "timestamp", "position_time_sql",
             "receive_time", "create_time", "gps_time", "collect_time"]
DM_COLS = ["drive_mode", "drivemode", "drive_mode_switch"]
LAT_COLS = ["latitude", "lat"]
LON_COLS = ["longitude", "lon", "lng"]


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


def pick(cols, cands):
    low = {str(c).strip().lower(): c for c in cols}
    for k in cands:
        if k in low:
            return low[k]
    return None


def to_sec(s):
    """任意时间列 -> int64 秒（北京时间视角；epoch 数字按 UTC 转 +8h）。返回 (secs, kind)"""
    smp = s.dropna().astype(str).head(2000)
    if s.dtype.kind in "iuf" or (len(smp) and smp.str.fullmatch(r"\d{10,13}(\.\d+)?").mean() > 0.9):
        x = pd.to_numeric(s, errors="coerce")
        med = x.median()
        if pd.isna(med):
            return None, "bad"
        sec = (x / 1000.0) if med > 1e12 else x
        return (sec + 8 * 3600).round().astype("Int64"), "epoch"
    try:
        t = pd.to_datetime(s, errors="coerce", infer_datetime_format=True)
    except TypeError:
        t = pd.to_datetime(s, errors="coerce", format="mixed")
    sec = (t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)
    return sec.astype("Int64"), "str"


def norm_deg(x):
    x = pd.to_numeric(x, errors="coerce")
    med = x.abs().median()
    if pd.isna(med):
        return x
    f = 1.0
    while med / f > 180:
        f *= 10
    return x / f


def ts(dt):
    return (pd.to_datetime(dt) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)


def build_vin_windows(ev):
    """ev: DataFrame(vin, t_sec) -> {vin: (starts, ends)}，已合并"""
    res = {}
    for vin, g in ev.groupby("vin"):
        a = np.sort(g.t_sec.values.astype(np.int64))
        st, en = a - HALF - PAD, a + HALF + PAD
        ms, me = [st[0]], [en[0]]
        for s, e in zip(st[1:], en[1:]):
            if s <= me[-1]:
                me[-1] = max(me[-1], e)
            else:
                ms.append(s); me.append(e)
        res[vin] = (np.array(ms), np.array(me))
    return res


def in_windows(t, starts, ends):
    i = np.searchsorted(starts, t, side="right") - 1
    ok = i >= 0
    ok[ok] = t[ok] <= ends[i[ok]]
    return ok


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))

    # ---------- 事件 ----------
    ve = pd.read_csv(BASE + r"\02_ego_video\video_events.csv", dtype={"vin": str})
    ve = ve[ve.vin.notna() & (ve.vin.str.len() == 17)].copy()
    ve["t_sec"] = ts(ve.mid)
    e9 = pd.read_csv(BASE + r"\02_ego_video\events0920_with_video.csv", dtype={"vin_": str})
    e9["vin"] = e9.vin_
    e9["t_sec"] = ts(e9.t)
    targets = pd.concat([ve[["vin", "t_sec"]], e9[["vin", "t_sec"]]])
    win = build_vin_windows(targets)
    vins = set(win)

    # 路侧时段（participant 连续段 + 龙门架片段）和范围
    seg = pd.read_csv(BASE + r"\03_roadside\participant_segments.csv")
    seg["kind"] = "pjson"
    gv = pd.read_csv(BASE + r"\03_roadside\gantry_videos.csv", dtype=str).drop_duplicates(["cam", "start", "end"])
    gv = gv.dropna(subset=["start", "end"])[["start", "end"]].assign(kind="gantry")
    rs = pd.concat([seg[["start", "end", "kind"]], gv]).reset_index(drop=True)
    rs["s"], rs["e"] = ts(rs.start), ts(rs.end)
    rs_sorted = rs.sort_values("s")
    ms, me = [], []
    for s, e in zip(rs_sorted.s, rs_sorted.e):
        if ms and s <= me[-1]:
            me[-1] = max(me[-1], e)
        else:
            ms.append(s); me.append(e)
    rs_st, rs_en = np.array(ms, dtype=np.int64), np.array(me, dtype=np.int64)
    pj = pd.read_csv(BASE + r"\03_roadside\participant_files.csv", usecols=["lat", "lon"])
    lat0, lat1 = pj.lat.min() - BBOX_MARGIN, pj.lat.max() + BBOX_MARGIN
    lon0, lon1 = pj.lon.min() - BBOX_MARGIN, pj.lon.max() + BBOX_MARGIN
    out("targets: 视频事件=%d  0920事件=%d  VIN=%d ;  路侧时段=%d段(合并后%d)  bbox lat %.4f~%.4f lon %.4f~%.4f" % (
        len(ve), len(e9), len(vins), len(rs), len(rs_st), lat0, lat1, lon0, lon1))

    # ---------- 轨迹文件 ----------
    cat = pd.read_csv(BASE + r"\04_tables\table_catalog.csv", dtype=str, keep_default_na=False)
    cat = cat[cat.traj == "True"].copy()
    cat["size_mb"] = pd.to_numeric(cat.size_mb, errors="coerce")
    sig_rank = cat.drop_duplicates("path").groupby("sig").size_mb.sum().sort_values(ascending=False)
    gid = {s: i + 1 for i, s in enumerate(sig_rank.index)}
    cat["grp"] = cat.sig.map(gid)
    cat["fname"] = cat.path.str.split("\\").str[-1]
    files = cat.drop_duplicates("path").drop_duplicates(["fname", "size_mb"])  # 同名同大小的拷贝只读一份
    out("轨迹文件: 候选=%d  去掉拷贝后=%d  %.1fGB" % (cat.path.nunique(), len(files), files.size_mb.sum() / 1024))

    hits, rsh, fstat, errs, t0 = [], [], [], [], time.time()
    for k, r in enumerate(files.itertuples(), 1):
        path = r.path
        try:
            if path.lower().endswith(".csv"):
                hdr = None
                for enc in ("utf-8-sig", "gbk"):
                    try:
                        hdr = pd.read_csv(path, nrows=0, encoding=enc).columns; break
                    except UnicodeDecodeError:
                        continue
                cv, ct, cd = pick(hdr, VIN_COLS), pick(hdr, TIME_COLS), pick(hdr, DM_COLS)
                cla, clo = pick(hdr, LAT_COLS), pick(hdr, LON_COLS)
                if not (cv and ct and cla and clo):
                    errs.append((path, "cols")); continue
                use = [c for c in (cv, ct, cd, cla, clo) if c]
                it = pd.read_csv(path, usecols=use, dtype=str, chunksize=CHUNK, encoding=enc, on_bad_lines="skip")
            else:
                sheets = pd.read_excel(path, sheet_name=None, dtype=str)
                it, cv = [], None
                for df in sheets.values():
                    cv, ct, cd = pick(df.columns, VIN_COLS), pick(df.columns, TIME_COLS), pick(df.columns, DM_COLS)
                    cla, clo = pick(df.columns, LAT_COLS), pick(df.columns, LON_COLS)
                    if cv and ct and cla and clo:
                        it.append(df); break
                if not it:
                    errs.append((path, "cols")); continue
            n, vs, tmin, tmax, kind = 0, set(), None, None, ""
            for ch in it:
                sec, kind = to_sec(ch[ct])
                if sec is None:
                    continue
                vin = ch[cv].astype(str).str.strip().str.upper()
                ok = sec.notna()
                n += len(ch); vs.update(vin[ok].unique().tolist())
                if ok.any():
                    a, b = int(sec[ok].min()), int(sec[ok].max())
                    tmin = a if tmin is None else min(tmin, a); tmax = b if tmax is None else max(tmax, b)
                lat, lon = norm_deg(ch[cla]), norm_deg(ch[clo])
                dm = ch[cd].astype(str) if cd else pd.Series("", index=ch.index)
                base = pd.DataFrame({"vin": vin, "sec": sec, "dm": dm, "lat": lat, "lon": lon})[ok]
                base["sec"] = base.sec.astype(np.int64)
                for sname, sh in SHIFTS.items():
                    t = base.sec.values + sh
                    # 事件窗口
                    m = base.vin.isin(vins).values
                    if m.any():
                        sub = base[m]
                        tt = t[m]
                        keep = np.zeros(len(sub), bool)
                        for v, idx in sub.groupby("vin").indices.items():
                            st, en = win[v]
                            keep[idx] = in_windows(tt[idx], st, en)
                        if keep.any():
                            h = sub[keep].copy(); h["sec"] = tt[keep]; h["shift"] = sname; h["grp"] = r.grp; h["file"] = k
                            hits.append(h)
                    # 路侧时段 + 范围
                    inbox = ((base.lat >= lat0) & (base.lat <= lat1) & (base.lon >= lon0) & (base.lon <= lon1)).values
                    if inbox.any() and len(rs_st):
                        okr = inbox.copy(); okr[inbox] = in_windows(t[inbox], rs_st, rs_en)
                        if okr.any():
                            h = base[okr].copy(); h["sec"] = t[okr]; h["shift"] = sname; h["grp"] = r.grp; h["file"] = k
                            rsh.append(h)
            fstat.append(dict(file=k, grp=r.grp, path=path, rows=n, vins=len(vs), kind=kind,
                              tmin=pd.to_datetime(tmin, unit="s") if tmin is not None else None,
                              tmax=pd.to_datetime(tmax, unit="s") if tmax is not None else None,
                              vin_col=cv, time_col=ct, dm_col=cd))
        except Exception as e:
            errs.append((path, repr(e)[:200]))
        if k % 50 == 0 or k == len(files):
            print("  ... %d/%d files  %.0fs  hits=%d" % (k, len(files), time.time() - t0, sum(len(h) for h in hits)))

    fs = pd.DataFrame(fstat); fs.to_csv(OUT_DIR + r"\traj_files.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(errs, columns=["path", "err"]).to_csv(OUT_DIR + r"\errors.csv", index=False, encoding="utf-8-sig")
    H = pd.concat(hits) if hits else pd.DataFrame(columns=["vin", "sec", "dm", "lat", "lon", "shift", "grp", "file"])
    R = pd.concat(rsh) if rsh else pd.DataFrame(columns=H.columns)
    H.to_csv(OUT_DIR + r"\event_hits.csv", index=False, encoding="utf-8-sig")
    R.to_csv(OUT_DIR + r"\roadside_hits.csv", index=False, encoding="utf-8-sig")
    out("读完: 文件=%d 失败=%d 行=%d  用时%.0fs" % (len(fs), len(errs), fs.rows.sum() if len(fs) else 0, time.time() - t0))

    # ---------- 各轨迹源概况 ----------
    out("")
    out("轨迹源(按04的分组号)  文件 / 行数 / VIN / 时间范围 / 时间格式")
    if len(fs):
        g = fs.groupby("grp").agg(files=("file", "size"), rows=("rows", "sum"), vins=("vins", "max"),
                                  tmin=("tmin", "min"), tmax=("tmax", "max"), kind=("kind", "first")).sort_index()
        for gi, x in g.head(15).iterrows():
            out("  [%s] %5d %11d %5d  %s ~ %s  %s" % (gi, x.files, x.rows, x.vins, str(x.tmin)[:16], str(x.tmax)[:16], x.kind))

    # ---------- 每个事件的轨迹覆盖 ----------
    def coverage(evdf, key):
        res = {}
        if not len(H):
            return pd.DataFrame(index=evdf.index)
        for sname in SHIFTS:
            h = H[H["shift"] == sname][["vin", "sec", "grp"]].drop_duplicates(["vin", "sec", "grp"])
            m = evdf[[key, "vin", "t_sec"]].merge(h, on="vin")
            m = m[(m.sec >= m.t_sec - HALF) & (m.sec <= m.t_sec + HALF)]
            c = m.groupby([key, "grp"]).sec.nunique().reset_index()
            best = c.sort_values("sec").groupby(key).tail(1).set_index(key)
            res["sec_" + sname] = best.sec
            res["grp_" + sname] = best.grp
        return pd.DataFrame(res).reindex(evdf[key]).fillna({"sec_0": 0, "sec_+8h": 0, "sec_-8h": 0})

    ve["key"] = range(len(ve)); e9["key"] = range(len(e9))
    cv_ = coverage(ve, "key"); ce_ = coverage(e9, "key")
    for c in cv_.columns: ve[c] = cv_[c].values
    for c in ce_.columns: e9[c] = ce_[c].values
    for d in (ve, e9):
        d["T"] = (d[["sec_0", "sec_+8h", "sec_-8h"]].max(axis=1) >= T_MIN_SEC).astype(int)
        d["T_shift"] = d[["sec_0", "sec_+8h", "sec_-8h"]].idxmax(axis=1).str[4:].where(d["T"] == 1, "")
    ve.to_csv(OUT_DIR + r"\video_events_T.csv", index=False, encoding="utf-8-sig")
    e9.to_csv(OUT_DIR + r"\events0920_T.csv", index=False, encoding="utf-8-sig")

    out("")
    out("[视频事件 x 轨迹]  (T=前后30s内>=%ds有经纬度)" % T_MIN_SEC)
    for lab, d in (("全部", ve), ("在0920", ve[ve.in0920 == 1]), ("清单外", ve[ve.in0920 == 0])):
        out("  %-6s 事件=%4d  有轨迹=%4d  无轨迹(仅视频)=%4d   对上的时区: %s" % (
            lab, len(d), d["T"].sum(), (d["T"] == 0).sum(),
            "  ".join("%s:%d" % (k, v) for k, v in d.T_shift[d["T"] == 1].value_counts().items())))
    out("  有轨迹的视频事件 通道组合: " + "  ".join("ch%s:%d" % (k, v) for k, v in ve[ve["T"] == 1].chans.value_counts().items()))
    out("  有轨迹的视频事件 最佳来源组: " + "  ".join("[%s]:%d" % (int(k), v) for k, v in
        ve[ve["T"] == 1].apply(lambda r: r["grp_" + r.T_shift], axis=1).value_counts().head(8).items()))
    has_v = e9.veid.notna()
    out("")
    out("[0920事件 x 轨迹]  事件=%d  有轨迹=%d  (其中有视频=%d, 无视频=%d)  无轨迹=%d" % (
        len(e9), e9["T"].sum(), (e9["T"].astype(bool) & has_v).sum(), (e9["T"].astype(bool) & ~has_v).sum(), (e9["T"] == 0).sum()))
    out("  0920有轨迹 按月: " + "  ".join("%s:%d" % (k, v) for k, v in pd.to_datetime(e9.t[e9["T"] == 1]).dt.strftime("%y%m").value_counts().sort_index().items()))

    # ---------- 路侧时段内的车辆和接管 ----------
    out("")
    out("[路侧时段 x 路口范围内的轨迹]")
    rs_by = {k: (g.s.values.astype(np.int64), g.e.values.astype(np.int64)) for k, g in rs.sort_values("s").groupby("kind")}
    for sname in SHIFTS:
        r = R[R["shift"] == sname].drop_duplicates(["vin", "sec"]).sort_values(["vin", "sec"])
        if not len(r):
            out("  shift %-4s 无数据" % sname)
            continue
        d = r.dm.astype(str).str.strip().str.lower()
        auto = d.isin(["1", "1.0", "auto", "true"]).values
        man = d.isin(["0", "0.0", "manual", "false"]).values
        same = (r.vin.values[1:] == r.vin.values[:-1])
        swm = np.zeros(len(r), bool)
        swm[1:] = same & auto[:-1] & man[1:]
        sw = r[swm].copy()
        if len(sw):
            sw = sw[~(sw.groupby("vin").sec.diff() < 60).fillna(False).values]
        parts = []
        for kd, (st, en) in rs_by.items():
            inr = in_windows(r.sec.values, st, en)
            insw = in_windows(sw.sec.values, st, en) if len(sw) else np.zeros(0, bool)
            parts.append("%s: 点=%d VIN=%d 接管=%d" % (kd, inr.sum(), r.vin[inr].nunique(), insw.sum()))
        out("  shift %-4s 点=%d  VIN=%d  drive_mode 1->0=%d (VIN=%d)  |  %s" % (
            sname, len(r), r.vin.nunique(), len(sw), sw.vin.nunique(), " ; ".join(parts)))
        sw.to_csv(OUT_DIR + "\\roadside_switches_%s.csv" % sname.replace("+", "p").replace("-", "m"), index=False, encoding="utf-8-sig")
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
