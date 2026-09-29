# -*- coding: utf-8 -*-
# 12_verify_all.py v2 : 从头独立重做 + 严格校验 + 事件资产表（只读）
#   事件唯一索引 = VIN + 事件时间(北京时间, 精确到秒)  -> event_key = VIN_YYYYMMDD_HHMMSS
#   事件全集 = 自车视频事件 ∪ 0920台账 ∪ NPY关键脱离(critical_label*) ∪ 龙门架案例目录
#   每个事件逐项列出资产：ch1前视/ch2座舱/ch3踏板(逐文件可读性/时长/副本/路径)、0920原因与标签、
#   各轨迹源覆盖秒数/采样/时区/drive_mode跳变、NPY(全部脱离/关键脱离)、路侧(参与者/车辆轨迹/交通流/信号/事件/龙门架)
# 仍使用 04 的 table_catalog.csv 找轨迹表；其余全部重新扫盘、重新读原始文件
# 用法: python 12_verify_all.py [根目录...]   (默认 C:\ D:\)
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "12_verify_all", "v2"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\12_verify"
ROOTS = ["C:\\", "D:\\"]
SKIP = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information",
        "appdata", "miniconda3", "anaconda3", "matlab", "microsoft vs code", "pycharm", "wps", "node_modules", ".git",
        "site-packages", "takeover_audit"}
RE_EGO = re.compile(r"^ch([123])_(\d{12})_(\d{12})\.(avi|mp4|mkv|h264)$", re.I)
RE_GV = re.compile(r"^(\d+)_(.+?)_(\d{14})-(\d{14})\.mp4$", re.I)
RE_RS = re.compile(r"^(participant|vehicle_track|traffic_flow|signal|event|camera_url)_(\d{14})-(\d{14})\.json$", re.I)
RE_VIN = re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])")
RE_CASE = re.compile(r"\d+-([A-HJ-NPR-Z0-9]{17})-(\d{4}-\d{2}-\d{2}) ?(\d{6})")
RS_TYPES = {"participant": "周边交通参与者", "vehicle_track": "车辆轨迹", "traffic_flow": "交通流", "signal": "信号配时", "event": "路侧事件"}
MAP_EXT = {".osm", ".xodr", ".shp", ".geojson", ".kml", ".kmz", ".gpkg", ".mbtiles", ".tif", ".tiff", ".dwg"}
MAP_KEYS = ("地图", "瓦片", "卫图", "xodr", "opendrive", "hdmap", "高精", "路网")
MERGE_S = 60      # 同VIN、时间相差<=60s 视为同一事件
HALF = 30         # 轨迹覆盖窗口 ±30s
T_MIN = 20        # ±30s 内 >=20 个不同秒有经纬度 算"有轨迹"
PAD = 90
SHIFTS = (0, 8 * 3600, -8 * 3600)
RS_RADIUS = 500
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
    if s.dtype == object and len(s.dropna()) and isinstance(s.dropna().iloc[0], (pd.Timestamp, np.datetime64)):
        s = pd.to_datetime(s, errors="coerce")
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


def nearest(a, b, tol):
    """a,b: DataFrame(vin, sec)；给 a 每行找 b 中同vin最近的一行(|dt|<=tol)，返回 b 的索引(找不到为 -1)"""
    res = pd.Series(-1, index=a.index)
    if not len(a) or not len(b):
        return res
    bb = b[["vin", "sec"]].dropna().reset_index().rename(columns={"index": "bi", "sec": "bsec"}).sort_values("bsec")
    aa = a[["vin", "sec"]].dropna().reset_index().rename(columns={"index": "ai"}).sort_values("sec")
    bb["bsec"] = bb.bsec.astype(float); aa["sec"] = aa.sec.astype(float)
    m = pd.merge_asof(aa, bb, left_on="sec", right_on="bsec", by="vin", direction="nearest")
    ok = (m.sec - m.bsec).abs() <= tol
    res.loc[m.ai[ok].values] = m.bi[ok].astype(int).values
    return res


def npy_labels(path):
    """读 labels 类 npy：返回 DataFrame(vin, sec) 或 None"""
    try:
        a = np.load(path, allow_pickle=True)
    except Exception:
        return None
    if a.ndim != 2 or a.shape[1] > 50 or a.shape[0] == 0:
        return None
    df = pd.DataFrame(a)
    head = df.head(5000)
    vc = next((c for c in df.columns if head[c].astype(str).str.upper().str.match(r"^[A-HJ-NPR-Z0-9]{17}$").mean() > .8), None)
    tc = next((c for c in df.columns if c != vc and to_sec(head[c]).between(1.5e9, 1.9e9).mean() > .8), None)
    if vc is None or tc is None:
        return None
    return pd.DataFrame({"vin": df[vc].astype(str).str.upper().str.strip(), "sec": to_sec(df[tc])}).dropna()


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    t00 = time.time()
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))

    # ================= 1. 重新扫盘 =================
    ego, gant, rsj, e9files, maps, npys, unk = [], [], [], [], [], [], 0
    for r in (sys.argv[1:] or ROOTS):
        if not os.path.exists(r):
            continue
        for d, n, sz in walk(r):
            low = n.lower()
            ext = os.path.splitext(low)[1]
            if ext in (".avi", ".mp4", ".mkv", ".h264"):
                m = RE_EGO.match(n)
                if m:
                    vm = RE_VIN.search((d + os.sep).upper())
                    ego.append(dict(dir=d, name=n, size=sz, ch=m.group(1), s=m.group(2), e=m.group(3), vin=vm.group(0) if vm else ""))
                    continue
                g = RE_GV.match(n)
                if g:
                    cm = RE_CASE.search(d.upper())
                    gant.append(dict(dir=d, name=n, size=sz, cam=g.group(2), s=g.group(3), e=g.group(4),
                                     case_vin=cm.group(1) if cm else "", case_t=(cm.group(2) + " " + cm.group(3)) if cm else ""))
                    continue
                if low.startswith("ch") and "_" in low:
                    unk += 1
            elif RE_RS.match(n):
                p = RE_RS.match(n)
                rsj.append(dict(dir=d, name=n, size=sz, typ=p.group(1).lower(), s=p.group(2), e=p.group(3)))
            elif "脱离事件汇总" in n and low.endswith(".xlsx") and not n.startswith("~$"):
                e9files.append(os.path.join(d, n))
            elif ext == ".npy" and (low.startswith("label") or low.startswith("critical_label")):
                npys.append(os.path.join(d, n))
            elif ext in MAP_EXT or (any(k in (d + n).lower() for k in MAP_KEYS) and ext in (".png", ".jpg", ".xml")):
                maps.append(dict(dir=d, name=n, size=sz, ext=ext))
    E = pd.DataFrame(ego)
    E["path"] = [os.path.join(a, b) for a, b in zip(E.dir, E.name)]
    E["start"] = pd.to_datetime(E.s, format="%y%m%d%H%M%S", errors="coerce")
    E["end"] = pd.to_datetime(E.e, format="%y%m%d%H%M%S", errors="coerce")
    out("[1] 扫盘%.0fs: 自车视频=%d 龙门架=%d 路侧json=%d 地图类=%d labels.npy=%d 0920候选=%d 命名不符的ch视频=%d" % (
        time.time() - t00, len(E), len(gant), len(rsj), len(maps), len(npys), len(e9files), unk))
    check("自车视频文件名都能解析时间", E.start.notna().all() and E.end.notna().all(), "失败=%d" % (E.start.isna() | E.end.isna()).sum())
    check("自车视频路径都含VIN", (E.vin != "").all(), "无VIN=%d(无法建索引,单列)" % (E.vin == "").sum())

    # ================= 2. 逐片段检查 =================
    clip = E.groupby(["vin", "ch", "start", "end"]).agg(copies=("path", "size"), smin=("size", "min"), smax=("size", "max"),
                                                        dirs=("dir", lambda s: " | ".join(sorted(set(s))))).reset_index()
    rep = E.sort_values("size", ascending=False).drop_duplicates(["vin", "ch", "start", "end"]).set_index(["vin", "ch", "start", "end"]).path
    clip["path"] = [rep.loc[k] for k in zip(clip.vin, clip.ch, clip.start, clip.end)]
    clip["dur_name"] = (clip.end - clip.start).dt.total_seconds()
    t0 = time.time()
    probes = [video_probe(p) for p in clip.path]
    has_cv = bool(probes) and probes[0] is not None
    if has_cv:
        clip = pd.concat([clip, pd.DataFrame(probes)], axis=1)
        clip["ok"] = (clip.open == 1) & (clip.decode == 1) & (clip.frames > 0)
        clip["dur_ok"] = (clip.dur - clip.dur_name).abs() <= 5
    else:
        clip["ok"] = clip.smax > 100 * 1024
        clip["dur"] = clip.dur_name
        clip["dur_ok"] = True
    out("")
    out("[2] 片段=%d 有多份拷贝=%d 拷贝大小不一致=%d 可读=%d 不可读=%d 时长符合=%d  (cv2=%s, %.0fs)" % (
        len(clip), (clip.copies > 1).sum(), (clip.smin != clip.smax).sum(), clip.ok.sum(), (~clip.ok).sum(),
        (clip.ok & clip.dur_ok).sum(), has_cv, time.time() - t0))
    for c in "123":
        x = clip[clip.ch == c]
        out("    ch%s(%s): 片段=%d 可读=%d 总时长=%.1fh  名义时长: %s" % (c, {"1": "前视", "2": "座舱", "3": "踏板"}[c], len(x), x.ok.sum(),
            x[x.ok].dur.sum() / 3600, " ".join("%ds:%d" % (k, v) for k, v in x.dur_name.value_counts().head(4).items())))
    check("拷贝大小一致", (clip.smin == clip.smax).all(), "不一致=%d(取最大)" % (clip.smin != clip.smax).sum())
    check("片段全部可读", clip.ok.all(), "不可读=%d" % (~clip.ok).sum())
    clip.to_csv(OUT_DIR + r"\clips.csv", index=False, encoding="utf-8-sig")

    # ================= 3. 视频事件 =================
    c2 = clip[clip.vin != ""].copy()
    c2["mid"] = c2.start + (c2.end - c2.start) / 2
    c2 = c2.sort_values(["vin", "mid"]).reset_index(drop=True)
    gid, lv, lm, k = [], None, None, 0
    for v, m in zip(c2.vin, c2.mid):
        if v != lv or (m - lm).total_seconds() > MERGE_S:
            k += 1
        gid.append(k); lv, lm = v, m
    c2["veid"] = gid
    rows = []
    for vid, g in c2.groupby("veid"):
        rec = dict(veid=vid, vin=g.vin.iloc[0], v_start=g.start.min(), v_end=g.end.max(), mid=g.mid.min() + (g.mid.max() - g.mid.min()) / 2,
                   v_windows=g[["start", "end"]].drop_duplicates().shape[0])
        for c in "123":
            x = g[g.ch == c]
            rec["ch%s_片段" % c] = len(x)
            rec["ch%s_可读" % c] = int(x.ok.sum())
            rec["ch%s_时长s" % c] = float(x[x.ok].dur.sum())
            rec["ch%s_副本" % c] = int(x.copies.sum())
            rec["ch%s_路径" % c] = ";".join(x.path)
        rows.append(rec)
    V = pd.DataFrame(rows)
    V["sec"] = to_sec(V.mid)
    chs = lambda r, suf: "".join(c for c in "123" if r["ch%s_%s" % (c, suf)] > 0)
    V["通道(文件)"] = V.apply(lambda r: chs(r, "片段"), axis=1)
    V["通道(可读)"] = V.apply(lambda r: chs(r, "可读"), axis=1)
    out("")
    out("[3] 视频事件=%d VIN=%d 时间 %s ~ %s  多时间窗事件=%d" % (len(V), V.vin.nunique(), V.v_start.min(), V.v_end.max(), (V.v_windows > 1).sum()))
    out("    通道组合(按文件): " + "  ".join("ch%s:%d" % (a, b) for a, b in V["通道(文件)"].value_counts().items()))
    out("    通道组合(可读):   " + "  ".join("ch%s:%d" % (a if a else "-", b) for a, b in V["通道(可读)"].value_counts().items()))

    # ================= 4. 0920 =================
    e9p = sorted(e9files, key=os.path.getmtime)[0]
    e9 = pd.read_excel(e9p, sheet_name=0)
    e9["vin"] = e9["vin"].astype(str).str.upper().str.strip()
    e9["sec"] = to_sec(e9["disengage_time"])
    e9["e9_row"] = np.arange(len(e9)) + 2
    vi = nearest(e9[["vin", "sec"]], V[["vin", "sec"]], MERGE_S)
    for i in e9.index[vi < 0]:
        g = V[(V.vin == e9.at[i, "vin"]) & (V.sec - (V.mid - V.v_start).dt.total_seconds() - 5 <= e9.at[i, "sec"]) &
              (e9.at[i, "sec"] <= V.sec + (V.v_end - V.mid).dt.total_seconds() + 5)]
        if len(g):
            vi.at[i] = g.index[0]
    e9["vidx"] = vi
    out("")
    out("[4] 0920: %s 行=%d  有视频=%d" % (e9p[-45:], len(e9), (e9.vidx >= 0).sum()))
    check("一个视频事件至多对应一条0920", (e9[e9.vidx >= 0].vidx.value_counts() <= 1).all())
    in9 = V.loc[e9[e9.vidx >= 0].vidx]
    n123 = (in9["通道(文件)"] == "123").sum()
    check("复现前人: 0920内三通道=35", n123 == 35, "实际=%d  ch12=%d  仅ch3=%d" % (
        n123, (in9["通道(文件)"] == "12").sum(), (in9["通道(文件)"] == "3").sum()))
    pd_ = r"D:\堡垒机数据筛选\脱离事件轨迹数据"
    if os.path.isdir(pd_):
        vdirs = [d for d in os.listdir(pd_) if os.path.isdir(os.path.join(pd_, d))]
        avis = sum(len([f for f in os.listdir(os.path.join(pd_, d, "三通道视频")) if f.lower().endswith(".avi")])
                   for d in vdirs if os.path.isdir(os.path.join(pd_, d, "三通道视频")))
        ours = set(in9[in9["通道(文件)"] == "123"].vin)
        check("与前人输出目录一致", avis == 3 * n123 and set(vdirs) == ours,
              "前人VIN=%d avi=%d ; 本次VIN=%d avi应为%d" % (len(vdirs), avis, len(ours), 3 * n123))

    # ================= 5. 事件全集(唯一索引) =================
    U = pd.DataFrame({"vin": V.vin, "sec": V.sec, "来源": "视频", "veid": V.veid, "e9_row": -1})
    m9 = e9[e9.vidx >= 0]
    U.loc[m9.vidx.values, "sec"] = m9.sec.values          # 有0920的，以0920时间为准
    U.loc[m9.vidx.values, "来源"] = "视频+0920"
    U.loc[m9.vidx.values, "e9_row"] = m9.e9_row.values
    add = e9[e9.vidx < 0]
    U = pd.concat([U, pd.DataFrame({"vin": add.vin, "sec": add.sec, "来源": "0920", "veid": -1, "e9_row": add.e9_row})], ignore_index=True)
    lab_all, lab_crit = [], []
    for p in npys:
        d = npy_labels(p)
        if d is None:
            continue
        (lab_crit if os.path.basename(p).lower().startswith("critical") else lab_all).append(d.assign(src=p))
    CR = pd.concat(lab_crit).drop_duplicates(["vin", "sec"]).reset_index(drop=True) if lab_crit else pd.DataFrame(columns=["vin", "sec", "src"])
    AL = pd.concat(lab_all).drop_duplicates(["vin", "sec"]).reset_index(drop=True) if lab_all else pd.DataFrame(columns=["vin", "sec", "src"])
    ci = nearest(CR, U, MERGE_S)
    U = pd.concat([U, pd.DataFrame({"vin": CR.vin[ci < 0], "sec": CR.sec[ci < 0], "来源": "NPY关键脱离", "veid": -1, "e9_row": -1})], ignore_index=True)
    G = pd.DataFrame(gant)
    if len(G):
        G["path"] = [os.path.join(a, b) for a, b in zip(G.dir, G.name)]
        G["s0"] = to_sec(pd.to_datetime(G.s, format="%Y%m%d%H%M%S", errors="coerce"))
        G["s1"] = to_sec(pd.to_datetime(G.e, format="%Y%m%d%H%M%S", errors="coerce"))
        G["inter"] = G.cam.str.extract(r"^(.+?路-.+?路)", expand=False)
        cs = G[G.case_vin != ""].drop_duplicates(["case_vin", "case_t"])
        cs = pd.DataFrame({"vin": cs.case_vin.values, "sec": to_sec(pd.to_datetime(cs.case_t, format="%Y-%m-%d %H%M%S", errors="coerce")).values})
        gi = nearest(cs, U, 180)
        U = pd.concat([U, pd.DataFrame({"vin": cs.vin[gi < 0], "sec": cs.sec[gi < 0], "来源": "龙门架案例", "veid": -1, "e9_row": -1})], ignore_index=True)
    U = U.dropna(subset=["sec"]).reset_index(drop=True)
    U["事件时间"] = pd.to_datetime(U.sec, unit="s")
    U["event_key"] = U.vin + "_" + U["事件时间"].dt.strftime("%Y%m%d_%H%M%S")
    U["日期"] = U["事件时间"].dt.date
    out("")
    out("[5] 事件全集=%d  来源: %s" % (len(U), "  ".join("%s:%d" % (a, b) for a, b in U["来源"].value_counts().items())))
    out("    NPY: 全部脱离标签=%d条(%d个文件)  关键脱离标签=%d条(%d个文件)" % (len(AL), len(lab_all), len(CR), len(lab_crit)))
    check("event_key 唯一", U.event_key.is_unique, "重复=%d" % U.event_key.duplicated().sum())

    # ================= 6. 轨迹(逐事件) =================
    cat = pd.read_csv(BASE + r"\04_tables\table_catalog.csv", dtype=str, keep_default_na=False)
    cat = cat[cat.traj == "True"].drop_duplicates("path")
    cat = cat[~cat.path.str.lower().str.contains("takeover_audit")]
    cat = cat.assign(fname=cat.path.str.replace("/", "\\").str.split("\\").str[-1]).drop_duplicates(["fname", "size_mb"])
    cat = cat[[os.path.exists(p) for p in cat.path]]
    win = {}
    for v, g in U.groupby("vin"):
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
                hdr = enc = None
                for enc in ("utf-8-sig", "gbk"):
                    try:
                        hdr = pd.read_csv(p, nrows=0, encoding=enc).columns; break
                    except UnicodeDecodeError:
                        continue
                cv, ct, cd, ca, co = (pick(hdr, VC[x]) for x in ("vin", "t", "dm", "lat", "lon"))
                if not (cv and ct and ca and co):
                    continue
                it = pd.read_csv(p, usecols=[c for c in (cv, ct, cd, ca, co) if c], dtype=str, chunksize=1_000_000, encoding=enc, on_bad_lines="skip")
            else:
                df = pd.read_excel(p, dtype=str)
                cv, ct, cd, ca, co = (pick(df.columns, VC[x]) for x in ("vin", "t", "dm", "lat", "lon"))
                if not (cv and ct and ca and co):
                    continue
                it = [df]
            for ch in it:
                vin = ch[cv].astype(str).str.upper().str.strip()
                m = vin.isin(win)
                if not m.any():
                    continue
                ch = ch[m]
                b = pd.DataFrame({"vin": vin[m], "sec": to_sec(ch[ct]), "dm": ch[cd].astype(str) if cd else "",
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
                        h = b[keep].copy(); h["sec"] = tt[keep]; h["shift"] = sh; h["file"] = p; h["dm_col"] = (cd or "").lower()
                        hits.append(h)
        except Exception:
            pass
        if k % 100 == 0:
            print("  ... 轨迹文件 %d/%d  %.0fs" % (k, len(cat), time.time() - t0))
    H = pd.concat(hits) if hits else pd.DataFrame(columns=["vin", "sec", "dm", "lat", "lon", "shift", "file", "dm_col"])
    if len(H):
        best = H.drop_duplicates(["file", "shift", "vin", "sec"]).groupby(["file", "shift"]).size().reset_index(name="n")
        H = H.merge(best.sort_values("n").drop_duplicates("file", keep="last")[["file", "shift"]], on=["file", "shift"])
    Hg = {k: g for k, g in H.groupby("vin")} if len(H) else {}
    rows = []
    for r in U.itertuples():
        rec = dict(轨迹_秒=0, 轨迹_文件="", 轨迹_源数=0, 轨迹_全部源="", 轨迹_偏移="", 轨迹_采样s=np.nan, 跳变_偏差s=np.nan, lat=np.nan, lon=np.nan)
        g = Hg.get(r.vin)
        if g is not None:
            x = g[(g.sec - r.sec).abs() <= HALF]
            if len(x):
                per = x.groupby("file").sec.nunique().sort_values(ascending=False)
                bf = per.index[0]
                xb = x[x.file == bf].drop_duplicates("sec").sort_values("sec")
                nb = xb.iloc[(xb.sec - r.sec).abs().argsort()[:3]]
                rec.update(轨迹_秒=int(per.iloc[0]), 轨迹_文件=bf, 轨迹_源数=len(per),
                           轨迹_全部源="; ".join("%s(%d)" % (f.replace("/", "\\").split("\\")[-1], n) for f, n in per.head(4).items()),
                           轨迹_偏移="%+dh" % (int(xb["shift"].iloc[0]) // 3600), lat=nb.lat.median(), lon=nb.lon.median(),
                           轨迹_采样s=float(np.median(np.diff(xb.sec.values))) if len(xb) > 1 else np.nan)
                if xb.dm_col.iloc[0] in ("drive_mode", "drivemode"):
                    d = pd.to_numeric(xb.dm, errors="coerce").values
                    s = xb.sec.values
                    idx = np.where((d[:-1] == 1) & (d[1:] == 0))[0]
                    if len(idx):
                        rec["跳变_偏差s"] = float(s[idx + 1][np.argmin(np.abs(s[idx + 1] - r.sec))] - r.sec)
        rows.append(rec)
    U = pd.concat([U, pd.DataFrame(rows)], axis=1)
    U["有轨迹"] = U.轨迹_秒 >= T_MIN
    out("")
    out("[6] 轨迹文件=%d 用时%.0fs  事件±30s覆盖秒: 0:%d 1-19:%d 20-49:%d >=50:%d" % (len(cat), time.time() - t0,
        (U.轨迹_秒 == 0).sum(), U.轨迹_秒.between(1, 19).sum(), U.轨迹_秒.between(20, 49).sum(), (U.轨迹_秒 >= 50).sum()))
    tv = U[U.有轨迹]
    out("    有轨迹=%d  采样: %s  偏移: %s  多源(>1个文件)=%d" % (len(tv),
        " ".join("%gs:%d" % (a, b) for a, b in tv.轨迹_采样s.round().value_counts().head(4).items()),
        " ".join("%s:%d" % (a, b) for a, b in tv.轨迹_偏移.value_counts().items()), (tv.轨迹_源数 > 1).sum()))
    out("    drive_mode 1->0 跳变在事件附近: 找到=%d |偏差|<=5s:%d <=30s:%d" % (
        tv.跳变_偏差s.notna().sum(), (tv.跳变_偏差s.abs() <= 5).sum(), (tv.跳变_偏差s.abs() <= 30).sum()))
    out("    最佳轨迹来源(事件数):")
    for f, n in tv.轨迹_文件.value_counts().head(8).items():
        out("       %5d  %s" % (n, f[-78:]))

    # ================= 7. NPY 归属 =================
    U["NPY全部脱离"] = (nearest(U[["vin", "sec"]], AL, MERGE_S) >= 0) if len(AL) else False
    U["NPY关键脱离"] = (nearest(U[["vin", "sec"]], CR, MERGE_S) >= 0) if len(CR) else False

    # ================= 8. 路侧(逐类型) =================
    P = pd.DataFrame(rsj)
    out("")
    out("[8] 路侧盘点:")
    if len(P):
        P["path"] = [os.path.join(a, b) for a, b in zip(P.dir, P.name)]
        P["s0"] = to_sec(pd.to_datetime(P.s, format="%Y%m%d%H%M%S", errors="coerce"))
        P["s1"] = to_sec(pd.to_datetime(P.e, format="%Y%m%d%H%M%S", errors="coerce"))
        loc = {}
        for d, g in P.groupby("dir"):
            la = lo = np.nan
            for fp in g.sort_values("size").path.tail(3):
                try:
                    b = open(fp, "rb").read(256 * 1024).decode("utf-8", "replace")
                    m1 = re.findall(r'"(?:refPosLat|ptcPosLat)"\s*:\s*(\d{8,10})', b)
                    m2 = re.findall(r'"(?:refPosLon|ptcPosLon)"\s*:\s*(\d{9,11})', b)
                    if m1 and m2:
                        la, lo = np.median([int(v) for v in m1]) / 1e7, np.median([int(v) for v in m2]) / 1e7
                        break
                except Exception:
                    pass
            loc[d] = (la, lo)
        P["dlat"] = P.dir.map(lambda d: loc[d][0]); P["dlon"] = P.dir.map(lambda d: loc[d][1])
        for t, g in P.groupby("typ"):
            out("    %-12s 文件=%5d %6.1fGB  %s ~ %s  目录=%d" % (RS_TYPES.get(t, t), len(g), g["size"].sum() / 2**30,
                sec2str(g.s0.min())[:16], sec2str(g.s1.max())[:16], g.dir.nunique()))
    if len(G):
        out("    %-12s 文件=%5d %6.1fGB  %s ~ %s  路口=%d 带案例VIN=%d" % ("龙门架视频", len(G), G["size"].sum() / 2**30,
            sec2str(G.s0.min())[:16], sec2str(G.s1.max())[:16], G.inter.nunique(), (G.case_vin != "").sum()))
    M = pd.DataFrame(maps)
    if len(M):
        out("    %-12s 文件=%5d %6.1fGB  %s" % ("地图类(静态)", len(M), M["size"].sum() / 2**30,
            " ".join("%s:%d" % (a, b) for a, b in M.ext.value_counts().head(6).items())))
        M.to_csv(OUT_DIR + r"\map_files.csv", index=False, encoding="utf-8-sig")
    dist = lambda la1, lo1, la2, lo2: np.hypot((la1 - la2) * 111320, (lo1 - lo2) * 111320 * np.cos(np.radians(31.3)))
    cols = {t: [] for t in RS_TYPES}
    gcase, gany = [], []
    for r in U.itertuples():
        for t in RS_TYPES:
            c = P[(P.typ == t) & (P.s0 <= r.sec) & (P.s1 >= r.sec)] if len(P) else pd.DataFrame()
            if len(c):
                c = c[dist(c.dlat, c.dlon, r.lat, r.lon) <= RS_RADIUS] if pd.notna(r.lat) else c.iloc[0:0]
            cols[t].append(";".join(c.path.head(2)) if len(c) else "")
        if len(G):
            a = G[(G.s0 <= r.sec + HALF) & (G.s1 >= r.sec - HALF)]
            gcase.append(";".join(a[a.case_vin == r.vin].path.head(4)))
            gany.append(";".join(sorted(set(a.inter.dropna())))[:200])
        else:
            gcase.append(""); gany.append("")
    for t, lab in RS_TYPES.items():
        U["路侧_" + lab] = cols[t]
    U["路侧_龙门架(同VIN)"] = gcase
    U["路侧_同时段龙门架路口"] = gany
    U["有路侧"] = (U["路侧_龙门架(同VIN)"] != "") | (U["路侧_周边交通参与者"] != "")

    # ================= 9. 资产表 =================
    U = U.merge(V.drop(columns=["sec", "vin"]), on="veid", how="left")
    for c in "123":
        U["ch%s_可读" % c] = U["ch%s_可读" % c].fillna(0).astype(int)
    for c in ("通道(可读)", "通道(文件)"):
        U[c] = U[c].fillna("")
    lab_cols = [c for c in ("描述", "是否紧急接管", "道路类型", "交通灯", "天气", "光线", "主车行为", "目标物", "cross_name1") if c in e9.columns]
    U = U.merge(e9[["e9_row"] + lab_cols], on="e9_row", how="left")
    U["在0920"] = U.e9_row > 0
    U["前人35"] = U["在0920"] & (U["通道(文件)"] == "123")
    has1 = U.ch1_可读 > 0
    U["类别"] = np.select(
        [has1 & U.有轨迹 & U["在0920"], has1 & U.有轨迹 & ~U["在0920"], has1 & ~U.有轨迹,
         (U.ch2_可读 + U.ch3_可读 > 0) & ~has1, U.有轨迹 & U.有路侧, U.有轨迹, U["在0920"]],
        ["A 视频ch1+轨迹+原因", "B 视频ch1+轨迹,无原因", "C 视频ch1,无轨迹", "D 仅ch2/ch3视频",
         "E 无视频,轨迹+路侧", "F 无视频,仅自车轨迹", "G 仅0920记录"], "H 其他(仅NPY/案例)")
    front = ["event_key", "vin", "日期", "事件时间", "来源", "类别", "通道(可读)", "ch1_可读", "ch2_可读", "ch3_可读",
             "有轨迹", "轨迹_秒", "轨迹_采样s", "轨迹_偏移", "跳变_偏差s", "轨迹_源数", "轨迹_全部源", "在0920", "前人35",
             "NPY全部脱离", "NPY关键脱离", "有路侧"]
    U = U[front + [c for c in U.columns if c not in front]]
    U.to_csv(OUT_DIR + r"\事件资产表.csv", index=False, encoding="utf-8-sig")
    try:
        U.drop(columns=["sec"], errors="ignore").to_excel(OUT_DIR + r"\事件资产表.xlsx", index=False)
    except Exception as e:
        out("xlsx 写出失败 %r" % e)

    # ================= 10. 统计 =================
    out("")
    out("################ 资产覆盖(按事件来源) ################")
    items = [("ch1前视", U.ch1_可读 > 0), ("ch2座舱", U.ch2_可读 > 0), ("ch3踏板", U.ch3_可读 > 0),
             ("三通道", U["通道(可读)"] == "123"), ("自车轨迹", U.有轨迹), ("0920原因", U["在0920"]),
             ("NPY全部", U.NPY全部脱离), ("NPY关键", U.NPY关键脱离)] + \
            [(lab, U["路侧_" + lab] != "") for lab in RS_TYPES.values()] + [("龙门架同VIN", U["路侧_龙门架(同VIN)"] != "")]
    srcs = list(U["来源"].value_counts().index)
    out("  %-12s %6s | " % ("资产", "全部") + " ".join("%9s" % s[:9] for s in srcs))
    out("  %-12s %6d | " % ("事件数", len(U)) + " ".join("%9d" % (U["来源"] == s).sum() for s in srcs))
    for lab, m in items:
        out("  %-12s %6d | " % (lab, m.sum()) + " ".join("%9d" % (m & (U["来源"] == s)).sum() for s in srcs))
    out("")
    out("################ 资产组合 Top15 (1=有) ################")
    combo = pd.DataFrame({"ch1": (U.ch1_可读 > 0).astype(int), "ch2": (U.ch2_可读 > 0).astype(int), "ch3": (U.ch3_可读 > 0).astype(int),
                          "轨迹": U.有轨迹.astype(int), "原因": U["在0920"].astype(int), "关键": U.NPY关键脱离.astype(int), "路侧": U.有路侧.astype(int)})
    cc = combo.groupby(list(combo.columns)).size().reset_index(name="n").sort_values("n", ascending=False).head(15)
    out("  " + " ".join("%4s" % c for c in combo.columns) + "   事件数")
    for _, r in cc.iterrows():
        out("  " + " ".join("%4d" % r[c] for c in combo.columns) + "   %5d" % r.n)
    out("")
    out("################ 分类 ################")
    for c, g in U.groupby("类别"):
        out("  %-22s %5d  (三通道=%d 有路侧=%d 日期 %s~%s)" % (c, len(g), (g["通道(可读)"] == "123").sum(), g.有路侧.sum(), g.日期.min(), g.日期.max()))
    check("分类合计=事件数", U["类别"].value_counts().sum() == len(U))
    out("  前人35=%d ; 视频事件中: 在0920=%d 清单外有ch1+轨迹=%d 清单外仅ch1=%d" % (U["前人35"].sum(),
        (U["在0920"] & (U.veid >= 0)).sum(), (~U["在0920"] & has1 & U.有轨迹).sum(), (~U["在0920"] & has1 & ~U.有轨迹).sum()))
    out("")
    out("################ 数据地址与匹配方法 ################")
    top = lambda s: s.fillna("").str.split(";").str[0].str.extract(r"^([A-Za-z]:\\[^\\]+)", expand=False)
    for c, g in U.groupby("类别"):
        vp = g.ch1_路径.fillna("").where(g.ch1_路径.fillna("") != "", g.ch3_路径.fillna(""))
        vd = top(vp).value_counts().head(4)
        tf = g[g.有轨迹].轨迹_文件.str.replace("/", "\\").str.split("\\").str[-1].value_counts().head(3)
        out("  %s: 视频 %s | 轨迹 %s" % (c[:12], " ".join("%s:%d" % (a, b) for a, b in vd.items()) or "-",
                                       " ".join("%s:%d" % (a[:22], b) for a, b in tf.items()) or "-"))
    out("  索引: event_key = VIN_YYYYMMDD_HHMMSS(北京时间)。同VIN且相差<=60s 归为同一事件")
    out("  视频: 路径中的VIN + 文件名 ch{1|2|3}_{起}_{止} ; 0920: VIN + disengage_time ; 轨迹: VIN + 事件±30s(自动 0/+8h/-8h)")
    out("  NPY: labels 的 VIN+时间 ±60s ; 路侧json: 时段覆盖事件 且 距事件<=%dm ; 龙门架: 时段重叠 且 案例目录VIN一致" % RS_RADIUS)
    out("")
    out("检查项 PASS=%d FAIL=%d  资产表: %s\\事件资产表.xlsx" % (sum(c[1] for c in CHECKS), sum(not c[1] for c in CHECKS), OUT_DIR))
    out("=== END %s %s  用时%.0fs ===" % (NAME, VERSION, time.time() - t00))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
