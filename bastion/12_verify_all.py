# -*- coding: utf-8 -*-
# 12_verify_all.py : 从头到尾独立重做 + 严格校验（只读，不依赖 02/03/05/07 的输出）
#   视频为中心：每个自车视频事件 -> 通道(ch1前视/ch2座舱/ch3踏板，逐文件可读性) -> 轨迹(来源/覆盖秒/采样/时区/drive_mode跳变)
#               -> 0920(原因) -> 与前人35条的关系 -> 路侧 -> 分类 -> 数据地址与匹配方法
# 仍然使用 04 的 table_catalog.csv 找轨迹表（表头目录），其余全部重新读原始文件
# 需要 pandas、numpy、openpyxl；cv2 可选（用于检查视频能否解码）
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "12_verify_all", "v1"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\12_verify"
ROOTS = ["C:\\", "D:\\"]
SKIP = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information",
        "appdata", "miniconda3", "anaconda3", "matlab", "microsoft vs code", "pycharm", "wps", "node_modules", ".git",
        "site-packages", "takeover_audit"}
RE_EGO = re.compile(r"^ch([123])_(\d{12})_(\d{12})\.(avi|mp4|mkv|h264)$", re.I)
RE_GV = re.compile(r"^(\d+)_(.+?)_(\d{14})-(\d{14})\.mp4$", re.I)
RE_RS = re.compile(r"^(participant|vehicle_track|traffic_flow|signal|event|camera_url)_(\d{14})-(\d{14})\.json$", re.I)
RS_TYPES = {"participant": "周边交通参与者", "vehicle_track": "车辆轨迹", "traffic_flow": "交通流", "signal": "信号配时", "event": "路侧事件"}
MAP_EXT = {".osm", ".xodr", ".shp", ".geojson", ".kml", ".kmz", ".gpkg", ".mbtiles", ".tif", ".tiff", ".dwg"}
MAP_KEYS = ("地图", "瓦片", "卫图", "xodr", "opendrive", "hdmap", "高精", "路网")
RS_RADIUS = 500   # 路侧设备与事件位置距离(m)
RE_VIN = re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])")
RE_CASE = re.compile(r"\d+-([A-HJ-NPR-Z0-9]{17})-\d{4}-\d{2}-\d{2} ?\d{6}")
MERGE_S = 60      # 同VIN中点相差<=60s 的片段属于同一视频事件
M0920_S = 60      # 0920 时间落在片段内或与中点相差<=60s
HALF = 30         # 轨迹覆盖窗口：中点 ±30s
T_MIN = 20        # ±30s 内 >=20 个不同秒有经纬度 算"有轨迹"
PAD = 90          # 读轨迹时收集中点 ±90s
SHIFTS = (0, 8 * 3600, -8 * 3600)
CHECKS = []


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


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    out("  [%s] %s  %s" % ("PASS" if ok else "FAIL", name, detail))


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


def sec2str(x):
    return "" if pd.isna(x) else str(pd.to_datetime(x, unit="s"))


def walk(root):
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except Exception:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.name.lower() not in SKIP:
                            stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        yield d, e.name, e.stat().st_size
                except Exception:
                    pass


def video_probe(path):
    try:
        import cv2
    except Exception:
        return None
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return dict(open=0, frames=0, fps=0, dur=0, decode=0)
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        ok, _ = cap.read()
        cap.release()
        return dict(open=1, frames=int(n), fps=round(fps, 2), dur=round(n / fps, 1) if fps else 0, decode=int(bool(ok)))
    except Exception:
        return dict(open=0, frames=0, fps=0, dur=0, decode=0)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    t00 = time.time()
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))

    # ================= 1. 重新扫盘：自车视频 / 龙门架 / participant / 0920 =================
    ego, gant, pj, e9files, unk, maps = [], [], [], [], 0, []
    for r in (sys.argv[1:] or ROOTS):
        if not os.path.exists(r):
            continue
        for d, n, sz in walk(r):
            low = n.lower()
            if low.endswith((".avi", ".mp4", ".mkv", ".h264")):
                m = RE_EGO.match(n)
                if m:
                    vm = RE_VIN.search((d + "\\").upper())
                    ego.append(dict(dir=d, name=n, size=sz, ch=m.group(1), s=m.group(2), e=m.group(3), vin=vm.group(0) if vm else ""))
                    continue
                g = RE_GV.match(n)
                if g:
                    cm = RE_CASE.search(d.upper())
                    gant.append(dict(dir=d, name=n, size=sz, cam=g.group(2), s=g.group(3), e=g.group(4), case_vin=cm.group(1) if cm else ""))
                    continue
                if low.startswith("ch") and "_" in low:
                    unk += 1
            elif RE_RS.match(n):
                p = RE_RS.match(n)
                pj.append(dict(dir=d, name=n, size=sz, typ=p.group(1).lower(), s=p.group(2), e=p.group(3)))
            elif os.path.splitext(low)[1] in MAP_EXT or (any(k in (d + n).lower() for k in MAP_KEYS) and
                                                          os.path.splitext(low)[1] in (".png", ".jpg", ".json", ".xml", ".csv")):
                maps.append(dict(dir=d, name=n, size=sz, ext=os.path.splitext(low)[1]))
            elif "脱离事件汇总" in n and low.endswith(".xlsx") and not n.startswith("~$"):
                e9files.append(os.path.join(d, n))
    E = pd.DataFrame(ego)
    E["path"] = [os.path.join(a, b) for a, b in zip(E.dir, E.name)]
    E["start"] = pd.to_datetime(E.s, format="%y%m%d%H%M%S", errors="coerce")
    E["end"] = pd.to_datetime(E.e, format="%y%m%d%H%M%S", errors="coerce")
    out("[1] 扫盘用时%.0fs: 自车视频文件=%d  龙门架mp4=%d  路侧json=%d  地图类文件=%d  0920候选=%d  ch开头但命名不符=%d" % (
        time.time() - t00, len(E), len(gant), len(pj), len(maps), len(e9files), unk))
    check("自车视频文件名全部解析出时间", E.start.notna().all() and E.end.notna().all(),
          "解析失败=%d" % (E.start.isna() | E.end.isna()).sum())
    check("自车视频路径都含VIN", (E.vin != "").all(), "无VIN=%d (这些无法关联轨迹/0920)" % (E.vin == "").sum())

    # ================= 2. 通道文件逐个检查 =================
    E["dur_name"] = (E.end - E.start).dt.total_seconds()
    clip = E.groupby(["vin", "ch", "start", "end"]).agg(copies=("path", "size"), smin=("size", "min"), smax=("size", "max"),
                                                        path=("path", lambda s: s.iloc[0]), dirs=("dir", lambda s: " | ".join(sorted(set(s))))).reset_index()
    rep = E.sort_values("size", ascending=False).drop_duplicates(["vin", "ch", "start", "end"]).set_index(["vin", "ch", "start", "end"]).path
    clip["path"] = [rep.loc[(a, b, c, d)] for a, b, c, d in zip(clip.vin, clip.ch, clip.start, clip.end)]
    clip["size_mb"] = clip.smax / 2**20
    clip["dur_name"] = (clip.end - clip.start).dt.total_seconds()
    t0 = time.time()
    probes = [video_probe(p) for p in clip.path]
    has_cv = probes[0] is not None if probes else False
    if has_cv:
        pr = pd.DataFrame(probes)
        clip = pd.concat([clip, pr], axis=1)
        clip["ok"] = (clip.open == 1) & (clip.decode == 1) & (clip.frames > 0)
        clip["dur_match"] = (clip.dur - clip.dur_name).abs() <= 5
    else:
        clip["ok"] = clip.smax > 100 * 1024
        clip["dur_match"] = True
    out("")
    out("[2] 片段(去重VIN+通道+起止)=%d  有多份拷贝=%d  拷贝大小不一致=%d  用时%.0fs  (cv2=%s)" % (
        len(clip), (clip.copies > 1).sum(), (clip.smin != clip.smax).sum(), time.time() - t0, has_cv))
    out("    可读片段=%d  不可读=%d  时长与文件名相符(±5s)=%d/%d" % (clip.ok.sum(), (~clip.ok).sum(), (clip.ok & clip.dur_match).sum(), clip.ok.sum()))
    for c in "123":
        x = clip[clip.ch == c]
        out("    ch%s: 片段=%d 可读=%d  时长(s)分布: %s" % (c, len(x), x.ok.sum(), " ".join(
            "%d:%d" % (k, v) for k, v in x.dur_name.value_counts().head(4).items())))
    check("拷贝间大小一致", (clip.smin == clip.smax).all(), "不一致=%d (已取最大的一份)" % (clip.smin != clip.smax).sum())
    check("全部片段可读", clip.ok.all(), "不可读=%d" % (~clip.ok).sum())
    clip.to_csv(OUT_DIR + r"\clips.csv", index=False, encoding="utf-8-sig")

    # ================= 3. 视频事件 =================
    c2 = clip[clip.vin != ""].copy()
    c2["mid"] = c2.start + (c2.end - c2.start) / 2
    w = c2.groupby(["vin", "start", "end", "mid"]).apply(lambda g: pd.Series({
        "chans": "".join(sorted(g.ch)), "chans_ok": "".join(sorted(g.ch[g.ok])),
        "p1": ";".join(g.path[g.ch == "1"]), "p2": ";".join(g.path[g.ch == "2"]), "p3": ";".join(g.path[g.ch == "3"])})).reset_index()
    w = w.sort_values(["vin", "mid"]).reset_index(drop=True)
    gid, lv, lm, k = [], None, None, 0
    for v, m in zip(w.vin, w.mid):
        if v != lv or (m - lm).total_seconds() > MERGE_S:
            k += 1
        gid.append(k); lv, lm = v, m
    w["veid"] = gid
    agg = lambda s: "".join(sorted(set("".join(s))))
    V = w.groupby("veid").agg(vin=("vin", "first"), start=("start", "min"), end=("end", "max"), mid=("mid", "first"),
                              n_win=("mid", "size"), chans=("chans", agg), chans_ok=("chans_ok", agg),
                              p1=("p1", lambda s: ";".join(x for x in s if x)), p2=("p2", lambda s: ";".join(x for x in s if x)),
                              p3=("p3", lambda s: ";".join(x for x in s if x))).reset_index()
    V["sec"] = to_sec(V.mid)
    V["ch_grade"] = np.select([V.chans_ok == "123", V.chans_ok.str.contains("1"), V.chans_ok != ""],
                              ["三通道", "有ch1缺其他", "无ch1"], "全部不可读")
    out("")
    out("[3] 视频事件=%d  VIN=%d  时间 %s ~ %s  (一个事件含多个时间窗的=%d)" % (
        len(V), V.vin.nunique(), V.start.min(), V.end.max(), (V.n_win > 1).sum()))
    out("    通道组合(按文件名): " + "  ".join("ch%s:%d" % (a, b) for a, b in V.chans.value_counts().items()))
    out("    通道组合(只算可读): " + "  ".join("ch%s:%d" % (a, b) for a, b in V.chans_ok.value_counts().items()))
    out("    通道等级: " + "  ".join("%s:%d" % (a, b) for a, b in V.ch_grade.value_counts().items()))
    check("视频事件数 = 时间窗合并结果", V.n_win.sum() == len(w), "窗=%d" % len(w))

    # ================= 4. 0920 =================
    e9p = sorted(e9files, key=lambda p: os.path.getmtime(p))[0]
    e9 = pd.read_excel(e9p, sheet_name=0)
    e9["vin_"] = e9["vin"].astype(str).str.upper().str.strip()
    e9["sec"] = to_sec(e9["disengage_time"])
    desc_col = "描述" if "描述" in e9.columns else None
    V["e9_row"] = -1; V["dt9"] = np.nan
    e9["veid"] = -1
    byv = {k: g for k, g in V.groupby("vin")}
    for i, r in e9.iterrows():
        g = byv.get(r.vin_)
        if g is None or pd.isna(r.sec):
            continue
        s0, s1 = to_sec(g.start).values, to_sec(g.end).values
        dt = g.sec.values - r.sec
        ok = ((s0 - 5 <= r.sec) & (r.sec <= s1 + 5)) | (np.abs(dt) <= M0920_S)
        if ok.any():
            j = np.argmin(np.where(ok, np.abs(dt), np.inf))
            vid = g.veid.values[j]
            e9.at[i, "veid"] = vid
            V.loc[V.veid == vid, ["e9_row", "dt9"]] = [i + 2, dt[j]]   # Excel 行号
    V["in0920"] = V.e9_row > 0
    V["desc"] = V.e9_row.map(lambda r: str(e9.at[r - 2, desc_col]) if r > 0 and desc_col else "")
    V["emerg"] = V.e9_row.map(lambda r: str(e9.at[r - 2, "是否紧急接管"]) if r > 0 and "是否紧急接管" in e9.columns else "")
    out("")
    out("[4] 0920=%s 行=%d  有视频的0920事件=%d  对应视频事件=%d  |中点-事件时间|<=5s: %d" % (
        e9p[-45:], len(e9), (e9.veid > 0).sum(), V.in0920.sum(), (V.dt9.abs() <= 5).sum()))
    check("一个视频事件只对应一条0920", (e9[e9.veid > 0].veid.value_counts() <= 1).all(),
          "一对多=%d" % (e9[e9.veid > 0].veid.value_counts() > 1).sum())

    # ================= 5. 与前人 35 条对账 =================
    in9 = V[V.in0920]
    n123 = (in9.chans == "123").sum()
    out("")
    out("[5] 0920内视频事件通道(按文件名): " + "  ".join("ch%s:%d" % (a, b) for a, b in in9.chans.value_counts().items()))
    check("复现前人: 0920内三通道齐全=35", n123 == 35, "实际=%d  ch12=%d  仅ch3=%d" % (
        n123, (in9.chans == "12").sum(), (in9.chans == "3").sum()))
    prev = [p for p in (r"D:\堡垒机数据筛选\脱离事件轨迹数据",) if os.path.isdir(p)]
    if prev:
        vdirs = [d for d in os.listdir(prev[0]) if os.path.isdir(os.path.join(prev[0], d))]
        avis = sum(len([f for f in os.listdir(os.path.join(prev[0], d, "三通道视频")) if f.lower().endswith(".avi")])
                   for d in vdirs if os.path.isdir(os.path.join(prev[0], d, "三通道视频")))
        prev_vins = set(vdirs)
        our_vins = set(in9[in9.chans == "123"].vin)
        out("    前人输出目录: VIN目录=%d  avi=%d (=35x3=105?)  ;  我们的三通道0920事件VIN=%d  两边VIN一致=%s" % (
            len(vdirs), avis, len(our_vins), prev_vins == our_vins))
        check("前人输出与本次一致", avis == 3 * n123 and prev_vins == our_vins,
              "只在前人=%s  只在本次=%s" % (sorted(prev_vins - our_vins)[:3], sorted(our_vins - prev_vins)[:3]))

    # ================= 6. 轨迹：逐事件确认 =================
    cat = pd.read_csv(BASE + r"\04_tables\table_catalog.csv", dtype=str, keep_default_na=False)
    cat = cat[cat.traj == "True"].drop_duplicates("path")
    cat = cat[~cat.path.str.lower().str.contains("takeover_audit")]
    cat = cat.assign(fname=cat.path.str.split("\\").str[-1]).drop_duplicates(["fname", "size_mb"])
    cat = cat[[os.path.exists(p) for p in cat.path]]
    vins = set(V.vin)
    win = {}
    for v, g in V.groupby("vin"):
        a = np.sort(g.sec.values.astype(np.int64))
        win[v] = (a - PAD, a + PAD)
    VC = {"vin": ["vin", "vin_x", "t2.vin"], "t": ["position_time", "positiontime", "dis_engage_time", "time", "timestamp",
          "position_time_sql", "gps_time"], "dm": ["drive_mode", "drivemode", "drive_mode_switch"],
          "lat": ["latitude", "lat"], "lon": ["longitude", "lon", "lng"]}
    pick = lambda cols, keys: next((c for k in keys for c in cols if str(c).strip().lower() == k), None)
    hits, t0 = [], time.time()
    for k, p in enumerate(cat.path, 1):
        try:
            if p.lower().endswith(".csv"):
                hdr = None
                for enc in ("utf-8-sig", "gbk"):
                    try:
                        hdr = pd.read_csv(p, nrows=0, encoding=enc).columns; break
                    except UnicodeDecodeError:
                        continue
                cv, ct, cd, ca, co = (pick(hdr, VC[x]) for x in ("vin", "t", "dm", "lat", "lon"))
                if not (cv and ct and ca and co):
                    continue
                it = pd.read_csv(p, usecols=[c for c in (cv, ct, cd, ca, co) if c], dtype=str, chunksize=1_000_000,
                                 encoding=enc, on_bad_lines="skip")
            else:
                df = pd.read_excel(p, dtype=str)
                cv, ct, cd, ca, co = (pick(df.columns, VC[x]) for x in ("vin", "t", "dm", "lat", "lon"))
                if not (cv and ct and ca and co):
                    continue
                it = [df]
            for ch in it:
                vin = ch[cv].astype(str).str.upper().str.strip()
                m = vin.isin(vins)
                if not m.any():
                    continue
                ch = ch[m]; vin = vin[m]
                sec = to_sec(ch[ct])
                b = pd.DataFrame({"vin": vin, "sec": sec, "dm": ch[cd].astype(str) if cd else "",
                                  "lat": pd.to_numeric(ch[ca], errors="coerce"), "lon": pd.to_numeric(ch[co], errors="coerce")}).dropna(subset=["sec"])
                b = b[b.lat.notna() & b.lon.notna() & (b.lat != 0)]
                for sh in SHIFTS:
                    tt = b.sec.values.astype(np.int64) + sh
                    keep = np.zeros(len(b), bool)
                    for v, idx in b.groupby("vin").indices.items():
                        st, en = win[v]
                        i = np.searchsorted(st, tt[idx], side="right") - 1
                        ok = i >= 0
                        ok[ok] = tt[idx][ok] <= en[i[ok]]
                        keep[idx] = ok
                    if keep.any():
                        h = b[keep].copy(); h["sec"] = tt[keep]; h["shift"] = sh; h["file"] = p; h["dm_col"] = cd or ""
                        hits.append(h)
        except Exception:
            pass
        if k % 100 == 0:
            print("  ... 轨迹文件 %d/%d  %.0fs" % (k, len(cat), time.time() - t0))
    H = pd.concat(hits) if hits else pd.DataFrame(columns=["vin", "sec", "dm", "lat", "lon", "shift", "file", "dm_col"])
    # 每个文件只保留命中最多的那个时区偏移
    if len(H):
        best = H.drop_duplicates(["file", "shift", "vin", "sec"]).groupby(["file", "shift"]).size().reset_index(name="n")
        best = best.sort_values("n").drop_duplicates("file", keep="last")
        H = H.merge(best[["file", "shift"]], on=["file", "shift"])
    out("")
    out("[6] 轨迹候选文件=%d  用时%.0fs  命中事件附近点=%d  来自文件=%d" % (len(cat), time.time() - t0, len(H), H.file.nunique() if len(H) else 0))
    rows = []
    Hg = {k: g for k, g in H.groupby("vin")} if len(H) else {}
    for r in V.itertuples():
        g = Hg.get(r.vin)
        rec = dict(veid=r.veid, t_secs=0, t_rows=0, t_file="", t_shift="", t_step=np.nan, sw=np.nan, n_files=0, lat=np.nan, lon=np.nan)
        if g is not None:
            x = g[(g.sec - r.sec).abs() <= HALF]
            if len(x):
                per = x.groupby("file").sec.nunique().sort_values()
                bf = per.index[-1]
                xb = x[x.file == bf].sort_values("sec")
                near0 = xb.iloc[(xb.sec - r.sec).abs().argsort()[:3]]
                rec.update(lat=near0.lat.median(), lon=near0.lon.median())
                rec.update(t_secs=int(per.iloc[-1]), t_rows=len(xb), t_file=bf, n_files=len(per),
                           t_shift="%+dh" % (xb["shift"].iloc[0] // 3600),
                           t_step=float(np.median(np.diff(np.unique(xb.sec)))) if xb.sec.nunique() > 1 else np.nan)
                if xb.dm_col.iloc[0] in ("drive_mode", "drivemode"):
                    d = pd.to_numeric(xb.drop_duplicates("sec").dm, errors="coerce").values
                    s = xb.drop_duplicates("sec").sec.values
                    idx = np.where((d[:-1] == 1) & (d[1:] == 0))[0]
                    if len(idx):
                        rec["sw"] = float(s[idx[np.argmin(np.abs(s[idx + 1] - r.sec))] + 1] - r.sec)
        rows.append(rec)
    V = V.merge(pd.DataFrame(rows), on="veid")
    V["T"] = V.t_secs >= T_MIN
    out("    视频事件 ±30s 轨迹覆盖秒数: 0:%d  1-19:%d  20-49:%d  >=50:%d" % (
        (V.t_secs == 0).sum(), V.t_secs.between(1, 19).sum(), V.t_secs.between(20, 49).sum(), (V.t_secs >= 50).sum()))
    tv = V[V["T"]]
    out("    有轨迹(>=%ds)=%d  采样间隔中位: %s  时区偏移: %s" % (T_MIN, len(tv),
        " ".join("%gs:%d" % (a, b) for a, b in tv.t_step.round().value_counts().head(4).items()),
        " ".join("%s:%d" % (a, b) for a, b in tv.t_shift.value_counts().items())))
    swk = tv.sw.notna()
    out("    有轨迹且带drive_mode的事件中, 在中点附近找到1->0跳变=%d  |跳变-中点|<=5s:%d  <=30s:%d" % (
        swk.sum(), (tv.sw.abs() <= 5).sum(), (tv.sw.abs() <= 30).sum()))
    out("    轨迹来源文件(有轨迹事件数): ")
    for f, n in tv.t_file.value_counts().head(8).items():
        out("       %4d  %s" % (n, f[-80:]))
    check("0920内的视频事件都有轨迹", V[V.in0920]["T"].all(), "无轨迹=%d" % (~V[V.in0920]["T"]).sum())

    # ================= 7. 路侧：逐类型匹配 =================
    G = pd.DataFrame(gant)
    if len(G):
        G["s0"] = to_sec(pd.to_datetime(G.s, format="%Y%m%d%H%M%S", errors="coerce"))
        G["s1"] = to_sec(pd.to_datetime(G.e, format="%Y%m%d%H%M%S", errors="coerce"))
        G["path"] = [os.path.join(a, b) for a, b in zip(G.dir, G.name)]
        G["inter"] = G.cam.str.extract(r"^(.+?路-.+?路)", expand=False)
    P = pd.DataFrame(pj)
    out("")
    out("[7] 路侧数据盘点:")
    if len(P):
        P["s0"] = to_sec(pd.to_datetime(P.s, format="%Y%m%d%H%M%S", errors="coerce"))
        P["s1"] = to_sec(pd.to_datetime(P.e, format="%Y%m%d%H%M%S", errors="coerce"))
        P["path"] = [os.path.join(a, b) for a, b in zip(P.dir, P.name)]
        # 每个目录抽一个文件取设备/参与者坐标
        loc = {}
        for d, g in P.groupby("dir"):
            la = lo = np.nan
            for fp in g.sort_values("size").path.tail(3):
                try:
                    b = open(fp, "rb").read(256 * 1024).decode("utf-8", "replace")
                    m1 = re.findall(r'"(?:refPosLat|ptcPosLat)"\s*:\s*(\d{8,10})', b)
                    m2 = re.findall(r'"(?:refPosLon|ptcPosLon)"\s*:\s*(\d{9,11})', b)
                    if m1 and m2:
                        la, lo = np.median([int(x) for x in m1]) / 1e7, np.median([int(x) for x in m2]) / 1e7
                        break
                except Exception:
                    pass
            loc[d] = (la, lo)
        P["dlat"] = P.dir.map(lambda d: loc[d][0]); P["dlon"] = P.dir.map(lambda d: loc[d][1])
        for t, g in P.groupby("typ"):
            out("    %-14s 文件=%5d  %6.1fGB  时间 %s ~ %s  目录=%d  已定位目录=%d" % (
                RS_TYPES.get(t, t), len(g), g["size"].sum() / 2**30, sec2str(g.s0.min())[:16], sec2str(g.s1.max())[:16],
                g.dir.nunique(), g.drop_duplicates("dir").dlat.notna().sum()))
    if len(G):
        out("    %-14s 文件=%5d  %6.1fGB  时间 %s ~ %s  路口=%d  带案例VIN=%d" % (
            "龙门架视频", len(G), G["size"].sum() / 2**30, sec2str(G.s0.min())[:16], sec2str(G.s1.max())[:16],
            G.inter.nunique(), (G.case_vin != "").sum()))
    M = pd.DataFrame(maps)
    if len(M):
        out("    %-14s 文件=%5d  %6.1fGB  类型: %s" % ("地图类", len(M), M["size"].sum() / 2**30,
            " ".join("%s:%d" % (a, b) for a, b in M.ext.value_counts().head(6).items())))
        for d, n in M.dir.str.extract(r"^([A-Za-z]:\\[^\\]+\\?[^\\]*)", expand=False).value_counts().head(5).items():
            out("        %4d  %s" % (n, d))
        M.to_csv(OUT_DIR + r"\map_files.csv", index=False, encoding="utf-8-sig")
    def dist(la1, lo1, la2, lo2):
        return np.hypot((la1 - la2) * 111320, (lo1 - lo2) * 111320 * np.cos(np.radians(31.3)))
    cols = {t: [] for t in RS_TYPES}
    gcase, gany = [], []
    for r in V.itertuples():
        for t in RS_TYPES:
            if not len(P):
                cols[t].append(""); continue
            c = P[(P.typ == t) & (P.s0 <= r.sec) & (P.s1 >= r.sec)]
            if len(c) and pd.notna(r.lat):
                c = c[dist(c.dlat, c.dlon, r.lat, r.lon) <= RS_RADIUS]
            elif len(c):
                c = c.iloc[0:0]                     # 没有事件位置就不认
            cols[t].append(";".join(c.path.head(2)))
        if len(G):
            a = G[(G.s0 <= r.sec + HALF) & (G.s1 >= r.sec - HALF)]
            gcase.append(";".join(a[a.case_vin == r.vin].path.head(4)))
            gany.append(";".join(sorted(set(a.inter.dropna())))[:200])
        else:
            gcase.append(""); gany.append("")
    for t in RS_TYPES:
        V["rs_" + t] = cols[t]
    V["gantry"], V["gantry_same_time_inters"] = gcase, gany
    V["R"] = (V.gantry != "") | (V.rs_participant != "")
    out("    视频事件逐类匹配(时间覆盖 且 距离<=%dm):" % RS_RADIUS)
    for t, lab in RS_TYPES.items():
        out("       %-14s %d" % (lab, (V["rs_" + t] != "").sum()))
    out("       %-14s %d  (同时段任意路口有龙门架视频: %d)" % ("龙门架(案例VIN)", (V.gantry != "").sum(), (V.gantry_same_time_inters != "").sum()))
    out("    有事件位置(可做距离判断)的视频事件=%d/%d" % (V.lat.notna().sum(), len(V)))

    # ================= 8. 分类 =================
    has1 = V.chans_ok.str.contains("1")
    V["类别"] = np.select(
        [has1 & V["T"] & V.in0920, has1 & V["T"] & ~V.in0920, has1 & ~V["T"], ~has1 & V["T"], ~has1 & ~V["T"]],
        ["A 视频(ch1)+轨迹+0920原因", "B 视频(ch1)+轨迹, 无原因(需人工看)", "C 仅视频(ch1), 无轨迹",
         "D 无ch1视频, 有轨迹", "E 无ch1视频, 无轨迹(不可用)"], "?")
    V["前人35"] = V.in0920 & (V.chans == "123")
    V.to_csv(OUT_DIR + r"\video_events_verified.csv", index=False, encoding="utf-8-sig")
    try:
        V.drop(columns=["sec"]).to_excel(OUT_DIR + r"\视频事件核验主表.xlsx", index=False)
    except Exception as e:
        out("xlsx写出失败 %r" % e)

    # ================= 报告三部分 =================
    out("")
    out("################ 报告 1: 视频匹配 ################")
    out("  视频事件(有VIN)=%d  其中有ch1可读=%d  三通道可读=%d" % (len(V), has1.sum(), (V.chans_ok == "123").sum()))
    out("  有轨迹=%d  在0920(有原因)=%d  有轨迹且在0920=%d" % (V["T"].sum(), V.in0920.sum(), (V["T"] & V.in0920).sum()))
    out("  前人35条(0920+三通道)=%d ; 本次在其基础上新增: 0920内非三通道=%d, 清单外有ch1+轨迹=%d, 清单外仅ch1视频=%d" % (
        V["前人35"].sum(), (V.in0920 & ~V["前人35"]).sum(), (~V.in0920 & has1 & V["T"]).sum(), (~V.in0920 & has1 & ~V["T"]).sum()))
    out("")
    out("################ 报告 2: 分类计数 ################")
    ct = pd.crosstab(V["类别"], V.ch_grade)
    out("  %-34s %6s | " % ("类别", "合计") + " ".join("%6s" % c for c in ct.columns) + " | 有路侧")
    for idx, r in ct.iterrows():
        out("  %-34s %6d | " % (idx, r.sum()) + " ".join("%6d" % v for v in r.values) + " | %d" % V[V["类别"] == idx].R.sum())
    out("  合计=%d" % len(V))
    check("分类合计=视频事件数", ct.values.sum() == len(V))
    out("")
    out("################ 报告 3: 数据地址与匹配方法 ################")
    top = lambda s: s.str.split(";").str[0].str.extract(r"^([A-Za-z]:\\[^\\]+)", expand=False)
    for c, g in V.groupby("类别"):
        out("  %s (%d)" % (c, len(g)))
        out("    视频目录: " + "  ".join("%s:%d" % (a, b) for a, b in top(g.p1.where(g.p1 != "", g.p3)).value_counts().head(5).items()))
        if g["T"].any():
            out("    轨迹文件: " + "  ".join("%s:%d" % (a.split("\\")[-1][:28], b) for a, b in g[g["T"]].t_file.value_counts().head(4).items()))
    out("  匹配键: 视频文件名 ch{n}_{起}_{止} + 路径中的VIN -> 事件(VIN, 片段中点, 北京时间)")
    out("          0920: VIN相同 且 disengage_time 落在片段内或距中点<=%ds" % M0920_S)
    out("          轨迹: VIN相同 且 时间在中点±%ds (每个轨迹文件自动选 0/+8h/-8h 偏移) ; >=%d个不同秒算有轨迹" % (HALF, T_MIN))
    out("          路侧: 龙门架片段与中点±%ds重叠 且 案例目录VIN一致 ; participant: 时段覆盖中点" % HALF)
    out("")
    out("检查项: PASS=%d  FAIL=%d   明细表: %s\\视频事件核验主表.xlsx" % (sum(c[1] for c in CHECKS), sum(not c[1] for c in CHECKS), OUT_DIR))
    out("=== END %s %s  用时%.0fs ===" % (NAME, VERSION, time.time() - t00))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
