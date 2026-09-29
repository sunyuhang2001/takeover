# -*- coding: utf-8 -*-
# 12_verify_all.py v5 : 从头独立重做 + 严格校验 + 事件资产表(2025年前) + 2025年单独一套(同样的分类)（只读）
#   事件唯一索引 event_key = VIN_YYYYMMDD_HHMMSS(北京时间)；同VIN相差<=60s 视为同一事件
#   主表(2025年前) = 自车视频 ∪ 0920 ∪ NPY关键脱离 ∪ 龙门架案例 ∪ 路侧时段内轨迹接管(2025年前)
#   2025表 = 2025年全部表格轨迹中的 drive_mode 1->0 接管 ∪ 2025年的龙门架案例 ∪ 其他来源落在2025年的事件
#   轨迹 = 表格轨迹(逐秒) 或 NPY 31帧样本(labels 与同目录同样本数的3维数组按行配对)
#   地址一律取原始位置：处理产物目录(堡垒机数据筛选/takeover_audit)与桌面拷贝排在最后
# 仍使用 04 的 table_catalog.csv 找轨迹表；其余全部重新扫盘、重新读原始文件
# 用法: python 12_verify_all.py [根目录...]   (默认 C:\ D:\)
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "12_verify_all", "v5"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\12_verify"
ROOTS = ["C:\\", "D:\\"]
SKIP = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information",
        "appdata", "miniconda3", "anaconda3", "matlab", "microsoft vs code", "pycharm", "wps", "node_modules", ".git",
        "site-packages", "takeover_audit"}
DERIVED = ("堡垒机数据筛选", "takeover_audit")          # 处理产物目录：不作为原始地址
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
T_MIN = 20        # ±30s 内有效覆盖 >=20s(或 NPY >=20 帧) 算"有轨迹"
GAP_OK = 5        # 相邻点间隔 <=5s 才算连续覆盖(13 诊断: add_type.csv 约1点/分钟, 只能定位不能复现)
PAD = 90
SHIFTS = (0, 8 * 3600, -8 * 3600)
RS_RADIUS = 500   # 路侧json设备与事件距离(m)
RS_NEAR = 300     # 路侧专项：自车离设备<=300m 算在覆盖内
Y2025 = 1735689600  # 2025-01-01 00:00 北京时间(秒)
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


def rank(p):
    """原始地址优先级：0=原始, 1=桌面拷贝, 2=处理产物"""
    pl = str(p).lower().replace("/", "\\")
    if any(k.lower() in pl for k in DERIVED):
        return 2
    return 1 if "\\desktop\\" in pl else 0


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


def cover(sec):
    """有效覆盖秒 = 1 + 相邻点间隔(<=GAP_OK 的部分)之和；逐秒 61 点=61，2s 采样 16 点=31，1点/分钟≈1"""
    a = np.unique(np.asarray(sec, dtype=np.int64))
    if not len(a):
        return 0
    d = np.diff(a)
    return int(1 + d[d <= GAP_OK].sum())


def sec2str(x):
    return "" if pd.isna(x) else str(pd.to_datetime(x, unit="s"))


def dist(la1, lo1, la2, lo2):
    return np.hypot((np.asarray(la1, float) - la2) * 111320, (np.asarray(lo1, float) - lo2) * 111320 * np.cos(np.radians(31.3)))


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
    """labels 类 npy -> DataFrame(vin, sec, row)；并找同目录同样本数的3维数组作为 31 帧轨迹"""
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
    partner = ""
    d = os.path.dirname(path)
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(".npy") and os.path.join(d, f) != path:
            try:
                x = np.load(os.path.join(d, f), mmap_mode="r")
                if x.ndim == 3 and x.shape[0] == a.shape[0]:
                    partner = os.path.join(d, f); break
            except Exception:
                pass
    return pd.DataFrame({"vin": df[vc].astype(str).str.upper().str.strip(), "sec": to_sec(df[tc]),
                         "row": np.arange(len(df)), "src": path, "partner": partner}).dropna(subset=["sec"])


def npy_frames(partner, row):
    """3维样本中这一行有多少帧不全为0/NaN"""
    try:
        x = np.load(partner, mmap_mode="r")[int(row)]
        x = np.asarray(x, dtype=float)
        return int((np.nan_to_num(np.abs(x)).sum(axis=1) > 0).sum()), x.shape[0]
    except Exception:
        return 0, 0


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
    E["rank"] = E.path.map(rank)
    E["start"] = pd.to_datetime(E.s, format="%y%m%d%H%M%S", errors="coerce")
    E["end"] = pd.to_datetime(E.e, format="%y%m%d%H%M%S", errors="coerce")
    out("[1] 扫盘%.0fs: 自车视频=%d(其中处理产物拷贝=%d) 龙门架=%d 路侧json=%d 地图类=%d labels.npy=%d 0920候选=%d 命名不符ch视频=%d" % (
        time.time() - t00, len(E), (E["rank"] == 2).sum(), len(gant), len(rsj), len(maps), len(npys), len(e9files), unk))
    check("自车视频文件名都能解析时间", E.start.notna().all() and E.end.notna().all(), "失败=%d" % (E.start.isna() | E.end.isna()).sum())
    check("自车视频路径都含VIN", (E.vin != "").all(), "无VIN=%d(无法建索引,单列在clips.csv)" % (E.vin == "").sum())

    # ================= 2. 逐片段检查(代表文件取原始地址) =================
    key4 = ["vin", "ch", "start", "end"]
    E = E.sort_values(["rank", "size"], ascending=[True, False])
    clip = E.groupby(key4, sort=False).agg(copies=("path", "size"), smin=("size", "min"), smax=("size", "max"),
                                           path=("path", "first"), rank=("rank", "first"),
                                           all_paths=("path", lambda s: " | ".join(s))).reset_index()
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
    out("[2] 片段=%d 有多份拷贝=%d 拷贝大小不一致=%d 可读=%d 不可读=%d 实测时长与文件名相符(±5s)=%d  代表文件取自处理产物=%d  (cv2=%s, %.0fs)" % (
        len(clip), (clip.copies > 1).sum(), (clip.smin != clip.smax).sum(), clip.ok.sum(), (~clip.ok).sum(),
        (clip.ok & clip.dur_ok).sum(), (clip["rank"] == 2).sum(), has_cv, time.time() - t0))
    for c in "123":
        x = clip[clip.ch == c]
        out("    ch%s(%s): 片段=%d 可读=%d 实测总时长=%.1fh  文件名时长: %s" % (c, {"1": "前视", "2": "座舱", "3": "踏板"}[c], len(x), x.ok.sum(),
            x[x.ok].dur.sum() / 3600, " ".join("%ds:%d" % (k, v) for k, v in x.dur_name.value_counts().head(4).items())))
    if has_cv:
        bad = clip[clip.ok & ~clip.dur_ok]
        out("    时长不符的片段=%d: 实测-文件名 差值分布(s): %s" % (len(bad), " ".join(
            "%s:%d" % (k, v) for k, v in pd.cut(bad.dur - bad.dur_name, [-1e9, -60, -10, -5, 5, 10, 60, 1e9]).value_counts().sort_index().items())))
    check("拷贝大小一致", (clip.smin == clip.smax).all(), "不一致=%d(代表文件优先原始目录)" % (clip.smin != clip.smax).sum())
    check("片段全部可读", clip.ok.all(), "不可读=%d(见clips.csv)" % (~clip.ok).sum())
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
            rec["ch%s_原始路径" % c] = ";".join(x.path)
            rec["ch%s_全部副本" % c] = " || ".join(x.all_paths)
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
    e9p = sorted(e9files, key=lambda p: (rank(p), os.path.getmtime(p)))[0]
    e9 = pd.read_excel(e9p, sheet_name=0)
    e9["vin"] = e9["vin"].astype(str).str.upper().str.strip()
    e9["sec"] = to_sec(e9["disengage_time"])
    e9["e9_row"] = np.arange(len(e9)) + 2
    vi = nearest(e9[["vin", "sec"]], V[["vin", "sec"]], MERGE_S)
    for i in e9.index[vi < 0]:
        g = V[(V.vin == e9.at[i, "vin"]) & (to_sec(V.v_start) - 5 <= e9.at[i, "sec"]) & (e9.at[i, "sec"] <= to_sec(V.v_end) + 5)]
        if len(g):
            vi.at[i] = g.index[0]
    e9["vidx"] = vi
    out("")
    out("[4] 0920(原始): %s 行=%d  有视频=%d" % (e9p[-60:], len(e9), (e9.vidx >= 0).sum()))
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

    # ================= 5. NPY / 龙门架 / 路侧 基础数据 =================
    labs = [x for x in (npy_labels(p) for p in npys) if x is not None]
    isc = lambda df: os.path.basename(df.src.iloc[0]).lower().startswith("critical")
    CR = pd.concat([x for x in labs if isc(x)]).sort_values("src", key=lambda s: s.map(rank)).drop_duplicates(["vin", "sec"]).reset_index(drop=True) \
        if any(isc(x) for x in labs) else pd.DataFrame(columns=["vin", "sec", "row", "src", "partner"])
    AL = pd.concat([x for x in labs if not isc(x)]).sort_values("src", key=lambda s: s.map(rank)).drop_duplicates(["vin", "sec"]).reset_index(drop=True) \
        if any(not isc(x) for x in labs) else pd.DataFrame(columns=["vin", "sec", "row", "src", "partner"])
    out("")
    out("[5] NPY: 全部脱离标签=%d条(%d文件, 有配对31帧样本的文件=%d)  关键脱离标签=%d条(%d文件, 有配对=%d)" % (
        len(AL), AL.src.nunique() if len(AL) else 0, AL[AL.partner != ""].src.nunique() if len(AL) else 0,
        len(CR), CR.src.nunique() if len(CR) else 0, CR[CR.partner != ""].src.nunique() if len(CR) else 0))
    G = pd.DataFrame(gant)
    if len(G):
        G["path"] = [os.path.join(a, b) for a, b in zip(G.dir, G.name)]
        G["rank"] = G.path.map(rank)
        G = G.sort_values("rank")
        G["s0"] = to_sec(pd.to_datetime(G.s, format="%Y%m%d%H%M%S", errors="coerce"))
        G["s1"] = to_sec(pd.to_datetime(G.e, format="%Y%m%d%H%M%S", errors="coerce"))
        G["inter"] = G.cam.str.extract(r"^(.+?路-.+?路)", expand=False)
        G["case_sec"] = to_sec(pd.to_datetime(G.case_t, format="%Y-%m-%d %H%M%S", errors="coerce"))
    P = pd.DataFrame(rsj)
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
        P = P.sort_values("path", key=lambda s: s.map(rank))
    PJ = P[P.typ == "participant"].drop_duplicates(["s0", "s1", "dlat", "size"]) if len(P) else pd.DataFrame()

    # ================= 6. 事件全集(第一部分) =================
    U = pd.DataFrame({"vin": V.vin, "sec": V.sec, "来源": "视频", "veid": V.veid, "e9_row": -1})
    m9 = e9[e9.vidx >= 0]
    U.loc[m9.vidx.values, "sec"] = m9.sec.values
    U.loc[m9.vidx.values, "来源"] = "视频+0920"
    U.loc[m9.vidx.values, "e9_row"] = m9.e9_row.values
    add = e9[e9.vidx < 0]
    U = pd.concat([U, pd.DataFrame({"vin": add.vin, "sec": add.sec, "来源": "0920", "veid": -1, "e9_row": add.e9_row})], ignore_index=True)
    ci = nearest(CR, U, MERGE_S)
    U = pd.concat([U, pd.DataFrame({"vin": CR.vin[ci < 0], "sec": CR.sec[ci < 0], "来源": "NPY关键脱离", "veid": -1, "e9_row": -1})], ignore_index=True)
    if len(G):
        cs = G[G.case_vin != ""].drop_duplicates(["case_vin", "case_t"])
        cs = pd.DataFrame({"vin": cs.case_vin.values, "sec": cs.case_sec.values})
        gi = nearest(cs, U, 180)
        U = pd.concat([U, pd.DataFrame({"vin": cs.vin[gi < 0], "sec": cs.sec[gi < 0], "来源": "龙门架案例", "veid": -1, "e9_row": -1})], ignore_index=True)
    U = U.dropna(subset=["sec"]).reset_index(drop=True)

    # ================= 7. 读全部轨迹：事件窗口 + 路侧时段 + 每车每天是否有数据 =================
    cat = pd.read_csv(BASE + r"\04_tables\table_catalog.csv", dtype=str, keep_default_na=False)
    cat = cat[cat.traj == "True"].drop_duplicates("path")
    cat = cat[[os.path.exists(p) for p in cat.path]].copy()
    cat["rank"] = cat.path.map(rank)
    cat["mtime"] = [os.path.getmtime(p) for p in cat.path]
    cat["fname"] = cat.path.str.replace("/", "\\").str.split("\\").str[-1]
    cat = cat.sort_values(["rank", "mtime"]).drop_duplicates(["fname", "size_mb"])      # 同名同大小只读原始那份
    win = {}
    for v, g in U.groupby("vin"):
        a = np.sort(g.sec.values.astype(np.int64))
        win[v] = (a - PAD, a + PAD)
    # 路侧时段（participant 每个文件的时间窗 + 设备位置）
    if len(PJ):
        pjw = PJ.dropna(subset=["s0", "s1"]).sort_values("s0")
        pj_st, pj_en = pjw.s0.values.astype(np.int64), pjw.s1.values.astype(np.int64)
        dev = pjw[["dlat", "dlon"]].dropna().drop_duplicates()
    else:
        pj_st = pj_en = np.array([], dtype=np.int64); dev = pd.DataFrame(columns=["dlat", "dlon"])
    VC = {"vin": ["vin", "vin_x", "t2.vin"], "t": ["position_time", "positiontime", "dis_engage_time", "time", "timestamp",
          "position_time_sql", "gps_time"], "dm": ["drive_mode", "drivemode", "drive_mode_switch"],
          "lat": ["latitude", "lat"], "lon": ["longitude", "lon", "lng"]}
    pick = lambda cols, keys: next((c for k in keys for c in cols if str(c).strip().lower() == k), None)
    hits, rhits, y25raw, days, fstat, t0 = [], [], [], set(), [], time.time()
    uvins = set(win)
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
            tmin = tmax = None; nv = set()
            for ch in it:
                vin = ch[cv].astype(str).str.upper().str.strip()
                b = pd.DataFrame({"vin": vin, "sec": to_sec(ch[ct]), "dm": ch[cd].astype(str) if cd else "",
                                  "lat": pd.to_numeric(ch[ca], errors="coerce"), "lon": pd.to_numeric(ch[co], errors="coerce")}).dropna(subset=["sec"])
                b = b[b.lat.notna() & b.lon.notna() & (b.lat != 0)]
                if not len(b):
                    continue
                tmin = b.sec.min() if tmin is None else min(tmin, b.sec.min())
                tmax = b.sec.max() if tmax is None else max(tmax, b.sec.max())
                nv.update(b.vin.unique().tolist())
                y = b[b.sec >= Y2025 - 9 * 3600]              # (d) 任何偏移下可能落在2025年的点
                if len(y):
                    y = y.copy(); y["file"] = p; y["dm_col"] = (cd or "").lower()
                    y25raw.append(y)
                bu = b[b.vin.isin(uvins)]
                for sh in SHIFTS:
                    # (a) 事件窗口
                    if len(bu):
                        tt = bu.sec.values.astype(np.int64) + sh
                        keep = np.zeros(len(bu), bool)
                        for v, idx in bu.groupby("vin").indices.items():
                            st, en = win[v]
                            i = np.searchsorted(st, tt[idx], side="right") - 1
                            ok = i >= 0
                            ok[ok] = tt[idx][ok] <= en[i[ok]]
                            keep[idx] = ok
                        if keep.any():
                            h = bu[keep].copy(); h["sec"] = tt[keep]; h["shift"] = sh; h["file"] = p; h["dm_col"] = (cd or "").lower()
                            hits.append(h)
                        # (c) 每车每天是否有数据(按偏移后日期)
                        dd = pd.DataFrame({"vin": bu.vin.values, "day": (tt // 86400)}).drop_duplicates()
                        days.update(zip(dd.vin, dd.day, [sh] * len(dd)))
                    # (b) 路侧时段 + 离设备近（所有 VIN）
                    if len(pj_st) and len(dev):
                        tt2 = b.sec.values.astype(np.int64) + sh
                        i = np.searchsorted(pj_st, tt2, side="right") - 1
                        ok = i >= 0
                        ok[ok] = tt2[ok] <= pj_en[i[ok]]
                        if ok.any():
                            bb = b[ok].copy(); bb["sec"] = tt2[ok]
                            dmin = np.min(np.vstack([dist(bb.lat, bb.lon, la, lo) for la, lo in zip(dev.dlat, dev.dlon)]), axis=0)
                            bb = bb[dmin <= RS_NEAR]
                            if len(bb):
                                bb["shift"] = sh; bb["file"] = p; bb["dm_col"] = (cd or "").lower()
                                rhits.append(bb)
            fstat.append(dict(file=p, rank=rank(p), tmin=sec2str(tmin), tmax=sec2str(tmax), vins=len(nv)))
        except Exception:
            pass
        if k % 100 == 0:
            print("  ... 轨迹文件 %d/%d  %.0fs" % (k, len(cat), time.time() - t0))
    FS = pd.DataFrame(fstat); FS.to_csv(OUT_DIR + r"\traj_files.csv", index=False, encoding="utf-8-sig")
    H = pd.concat(hits) if hits else pd.DataFrame(columns=["vin", "sec", "dm", "lat", "lon", "shift", "file", "dm_col"])
    # 每个文件只保留命中事件窗口最多的那个时区偏移；路侧命中沿用同一偏移
    fshift = {}
    if len(H):
        best = H.drop_duplicates(["file", "shift", "vin", "sec"]).groupby(["file", "shift"]).size().reset_index(name="n")
        best = best.sort_values("n").drop_duplicates("file", keep="last")
        fshift = dict(zip(best.file, best["shift"]))
        H = H.merge(best[["file", "shift"]], on=["file", "shift"])
    RH = pd.concat(rhits) if rhits else pd.DataFrame(columns=H.columns)
    if len(RH):
        RH["want"] = RH.file.map(fshift)
        # 没有事件可定偏移的文件：取在路侧时段内点数最多的偏移
        nos = RH[RH.want.isna()].groupby(["file", "shift"]).size().reset_index(name="n").sort_values("n").drop_duplicates("file", keep="last")
        RH.loc[RH.want.isna(), "want"] = RH.loc[RH.want.isna(), "file"].map(dict(zip(nos.file, nos["shift"])))
        RH = RH[RH["shift"] == RH.want].drop(columns="want")
    out("")
    out("[7] 轨迹文件(去重后,原始优先)=%d 用时%.0fs  事件窗口命中点=%d  路侧时段命中点=%d" % (len(cat), time.time() - t0, len(H), len(RH)))

    # ================= 8. 路侧时段接管(仅2025年前并入主表) + 2025年事件 =================
    def switches(R):
        """R: DataFrame(vin, sec, dm, dm_col, lat, lon, file) -> drive_mode 1->0 接管(同车60s内去重)"""
        if not len(R):
            return pd.DataFrame(columns=["vin", "sec", "lat", "lon", "file"])
        R = R.drop_duplicates(["vin", "sec"]).sort_values(["vin", "sec"]).reset_index(drop=True)
        dmc = R.dm_col.isin(["drive_mode", "drivemode"])
        d = pd.to_numeric(R.dm, errors="coerce")
        sw = R[dmc & R.vin.eq(R.vin.shift(1)) & (d.shift(1) == 1) & (d == 0) & ((R.sec - R.sec.shift(1)) <= 10)]
        sw = sw[~(sw.groupby("vin").sec.diff() < MERGE_S).fillna(False).values]
        return sw[["vin", "sec", "lat", "lon", "file"]].reset_index(drop=True)
    R1 = RH.drop_duplicates(["vin", "sec"]).sort_values(["vin", "sec"]).reset_index(drop=True) if len(RH) else RH
    if len(R1):
        R1["day"] = pd.to_datetime(R1.sec, unit="s").dt.date
        R1.to_csv(OUT_DIR + r"\roadside_ego_points.csv", index=False, encoding="utf-8-sig")
    rs_events = switches(R1)
    rs_pre = rs_events[rs_events.sec < Y2025]
    ri = nearest(rs_pre, U, MERGE_S)
    U = pd.concat([U, pd.DataFrame({"vin": rs_pre.vin[ri < 0], "sec": rs_pre.sec[ri < 0], "来源": "路侧时段轨迹接管", "veid": -1, "e9_row": -1})], ignore_index=True)
    # 2025 年：全部轨迹点(按文件确定的时区偏移) -> 接管事件
    Y = pd.concat(y25raw) if y25raw else pd.DataFrame(columns=["vin", "sec", "dm", "lat", "lon", "file", "dm_col"])
    if len(Y):
        rsh = RH.groupby("file")["shift"].first().to_dict() if len(RH) else {}
        Y["shift"] = Y.file.map(lambda f: fshift.get(f, rsh.get(f, 0)))
        Y["sec"] = Y.sec + Y["shift"]
        Y = Y[Y.sec >= Y2025]
    H25 = pd.concat([Y[H.columns], RH[RH.sec >= Y2025][H.columns]]).drop_duplicates(["vin", "sec", "file"]) if len(Y) or len(RH) else H.iloc[0:0]
    ev25 = switches(Y)
    U25 = pd.DataFrame({"vin": ev25.vin, "sec": ev25.sec, "来源": "2025轨迹接管", "veid": -1, "e9_row": -1})
    if len(G):
        g25 = G[(G.case_vin != "") & (G.case_sec >= Y2025)].drop_duplicates(["case_vin", "case_t"])
        c25 = pd.DataFrame({"vin": g25.case_vin.values, "sec": g25.case_sec.values})
        gi = nearest(c25, U25, 180)
        U25 = pd.concat([U25, pd.DataFrame({"vin": c25.vin[gi < 0], "sec": c25.sec[gi < 0], "来源": "2025龙门架案例", "veid": -1, "e9_row": -1})], ignore_index=True)
    mv = U[U.sec >= Y2025]                               # 其他来源落在2025年的，移到2025表
    U25 = pd.concat([U25, mv], ignore_index=True).reset_index(drop=True)
    U = U[U.sec < Y2025].reset_index(drop=True)
    if len(RH):
        H = pd.concat([H, RH[RH.sec < Y2025][H.columns]]).drop_duplicates(["vin", "sec", "file"])
    for X in (U, U25):
        X["事件时间"] = pd.to_datetime(X.sec, unit="s")
        X["event_key"] = X.vin + "_" + X["事件时间"].dt.strftime("%Y%m%d_%H%M%S")
        X["日期"] = X["事件时间"].dt.date
    out("")
    out("[8] 主表(2025年前)事件=%d  来源: %s" % (len(U), "  ".join("%s:%d" % (a, b) for a, b in U["来源"].value_counts().items())))
    out("    2025表事件=%d  来源: %s   (2025年轨迹点=%d 车辆=%d 来源文件=%d)" % (len(U25),
        "  ".join("%s:%d" % (a, b) for a, b in U25["来源"].value_counts().items()) or "-", len(H25), H25.vin.nunique() if len(H25) else 0,
        H25.file.nunique() if len(H25) else 0))
    check("event_key 唯一(主表)", U.event_key.is_unique, "重复=%d" % U.event_key.duplicated().sum())
    check("event_key 唯一(2025表)", U25.event_key.is_unique, "重复=%d" % U25.event_key.duplicated().sum())
    day25 = set()
    if len(H25):
        day25 = set(zip(H25.vin, (H25.sec // 86400).astype(int), [0] * len(H25)))

    def process(U, H, days, tag, fname):
        out("")
        out("==================== %s ====================" % tag)
        # ================= 9. 逐事件：表格轨迹 / NPY轨迹 / 当天是否有数据 =================
        Hg = {k: g for k, g in H.groupby("vin")} if len(H) else {}
        ai = nearest(U[["vin", "sec"]], AL, MERGE_S) if len(AL) else pd.Series(-1, index=U.index)
        cj = nearest(U[["vin", "sec"]], CR, MERGE_S) if len(CR) else pd.Series(-1, index=U.index)
        dayset = {}
        for v, dday, sh in days:
            dayset.setdefault(v, set()).add(dday)
        rows = []
        for idx, r in U.iterrows():
            rec = dict(轨迹_秒=0, 轨迹_点数=0, 轨迹_原始文件="", 轨迹_源数=0, 轨迹_全部源="", 轨迹_偏移="", 轨迹_采样s=np.nan, 跳变_偏差s=np.nan,
                       lat=np.nan, lon=np.nan, NPY帧=0, NPY文件="", NPY行=-1)
            g = Hg.get(r.vin)
            if g is not None:
                x = g[(g.sec - r.sec).abs() <= HALF]
                if len(x):
                    per = x.groupby("file").sec.apply(cover).reset_index(name="n")
                    per["pts"] = x.groupby("file").sec.nunique().values
                    per["rank"] = per.file.map(rank)
                    per = per.sort_values(["n", "rank"], ascending=[False, True])
                    bf = per.file.iloc[0]
                    xb = x[x.file == bf].drop_duplicates("sec").sort_values("sec")
                    nb = xb.iloc[(xb.sec - r.sec).abs().argsort()[:3]]
                    rec.update(轨迹_秒=int(per.n.iloc[0]), 轨迹_点数=int(per.pts.iloc[0]), 轨迹_原始文件=bf, 轨迹_源数=len(per),
                               轨迹_全部源="; ".join("%s(%d)" % (f, n) for f, n in zip(per.file.head(5), per.n.head(5))),
                               轨迹_偏移="%+dh" % (int(xb["shift"].iloc[0]) // 3600), lat=nb.lat.median(), lon=nb.lon.median(),
                               轨迹_采样s=float(np.median(np.diff(xb.sec.values))) if len(xb) > 1 else np.nan)
                    if xb.dm_col.iloc[0] in ("drive_mode", "drivemode"):
                        d = pd.to_numeric(xb.dm, errors="coerce").values
                        s = xb.sec.values
                        j = np.where((d[:-1] == 1) & (d[1:] == 0))[0]
                        if len(j):
                            rec["跳变_偏差s"] = float(s[j + 1][np.argmin(np.abs(s[j + 1] - r.sec))] - r.sec)
            for lab, ii in ((CR, cj.at[idx]), (AL, ai.at[idx])):
                if ii >= 0 and lab.at[ii, "partner"]:
                    nf, tot = npy_frames(lab.at[ii, "partner"], lab.at[ii, "row"])
                    if nf > rec["NPY帧"]:
                        rec.update(NPY帧=nf, NPY文件=lab.at[ii, "partner"], NPY行=int(lab.at[ii, "row"]))
            dd = int(r.sec // 86400)
            rec["当天有表格轨迹"] = bool(dayset.get(r.vin, set()) & {dd - 1, dd, dd + 1})
            rows.append(rec)
        U = pd.concat([U, pd.DataFrame(rows, index=U.index)], axis=1)
        U["NPY全部脱离"] = ai >= 0
        U["NPY关键脱离"] = cj >= 0
        U["有表格轨迹"] = U.轨迹_秒 >= T_MIN
        U["有NPY轨迹"] = U.NPY帧 >= T_MIN
        U["有轨迹"] = U.有表格轨迹 | U.有NPY轨迹
        U["轨迹类型"] = np.select([U.有表格轨迹 & U.有NPY轨迹, U.有表格轨迹, U.有NPY轨迹, U.轨迹_秒 > 0],
                               ["表格+NPY", "表格(连续)", "NPY(31帧)", "表格(稀疏/不足20s)"], "无")
        out("")
        out("[9] 轨迹: 事件±30s覆盖秒 0:%d 1-19:%d 20-49:%d >=50:%d ; NPY帧>=20:%d" % (
            (U.轨迹_秒 == 0).sum(), U.轨迹_秒.between(1, 19).sum(), U.轨迹_秒.between(20, 49).sum(), (U.轨迹_秒 >= 50).sum(), U.有NPY轨迹.sum()))
        out("    轨迹类型: " + "  ".join("%s:%d" % (a, b) for a, b in U.轨迹类型.value_counts().items()))
        tv = U[U.有表格轨迹]
        out("    表格轨迹: 采样 %s ; 偏移 %s ; 跳变找到=%d (|偏差|<=5s:%d <=30s:%d)" % (
            " ".join("%gs:%d" % (a, b) for a, b in tv.轨迹_采样s.round().value_counts().head(4).items()),
            " ".join("%s:%d" % (a, b) for a, b in tv.轨迹_偏移.value_counts().items()),
            tv.跳变_偏差s.notna().sum(), (tv.跳变_偏差s.abs() <= 5).sum(), (tv.跳变_偏差s.abs() <= 30).sum()))
        out("    最佳表格轨迹来源(原始地址, 事件数):")
        for f, n in tv.轨迹_原始文件.value_counts().head(8).items():
            out("       %5d  %s" % (n, f))
        if U.有NPY轨迹.any():
            out("    NPY轨迹来源: " + "  ".join("%s:%d" % (f[-60:], n) for f, n in U[U.有NPY轨迹].NPY文件.value_counts().head(3).items()))

        # ================= 10. 路侧逐类型 =================
        cols = {t: [] for t in RS_TYPES}
        gcase, gany, gdt, ginter = [], [], [], []
        for r in U.itertuples():
            for t in RS_TYPES:
                c = P[(P.typ == t) & (P.s0 <= r.sec) & (P.s1 >= r.sec)] if len(P) else pd.DataFrame()
                if len(c):
                    c = c[dist(c.dlat, c.dlon, r.lat, r.lon) <= RS_RADIUS] if pd.notna(r.lat) else c.iloc[0:0]
                cols[t].append(";".join(c.path.head(2)) if len(c) else "")
            if len(G):
                a = G[(G.s0 <= r.sec + HALF) & (G.s1 >= r.sec - HALF)]
                a2 = a[a.case_vin == r.vin].drop_duplicates("name")
                gcase.append(";".join(a2.path.head(6)))
                ginter.append("/".join(sorted(set(a2.inter.dropna()))))
                gdt.append(float((a2.case_sec - r.sec).abs().min()) if len(a2) else np.nan)
                gany.append(";".join(sorted(set(a.inter.dropna())))[:200])
            else:
                gcase.append(""); gany.append(""); gdt.append(np.nan); ginter.append("")
        for t, lab in RS_TYPES.items():
            U["路侧_" + lab] = cols[t]
        U["路侧_龙门架(同VIN)"] = gcase
        U["路侧_龙门架案例时间差s"] = gdt
        U["路侧_龙门架路口(同VIN)"] = ginter
        U["路侧_同时段龙门架路口"] = gany
        U["有路侧"] = (U["路侧_龙门架(同VIN)"] != "") | (U["路侧_周边交通参与者"] != "")

        # ================= 11. 资产表 =================
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
        hasv = U["通道(文件)"] != ""
        U["类别"] = np.select(
            [has1 & U.有轨迹 & U["在0920"], has1 & U.有轨迹 & ~U["在0920"], has1 & ~U.有轨迹,
             (U.ch2_可读 + U.ch3_可读 > 0) & ~has1, hasv & (U["通道(可读)"] == ""),
             U.有轨迹 & U.有路侧, U.有轨迹, U["在0920"]],
            ["A 视频ch1+轨迹+原因", "B 视频ch1+轨迹,无原因", "C 视频ch1,无连续轨迹", "D 仅ch2/ch3视频", "X 视频全部不可读",
             "E 无视频,轨迹+路侧", "F 无视频,仅自车轨迹", "G 仅0920记录(无轨迹)"], "H 无视频,无连续轨迹")
        front = ["event_key", "vin", "日期", "事件时间", "来源", "类别", "通道(可读)", "ch1_可读", "ch2_可读", "ch3_可读",
                 "有轨迹", "轨迹类型", "轨迹_秒", "NPY帧", "轨迹_采样s", "轨迹_偏移", "跳变_偏差s", "当天有表格轨迹",
                 "轨迹_原始文件", "轨迹_全部源", "NPY文件", "NPY行", "在0920", "前人35", "NPY全部脱离", "NPY关键脱离", "有路侧"]
        U = U[front + [c for c in U.columns if c not in front]]
        U.to_csv(OUT_DIR + "\\" + fname + ".csv", index=False, encoding="utf-8-sig")
        try:
            U.drop(columns=["sec"], errors="ignore").to_excel(OUT_DIR + "\\" + fname + ".xlsx", index=False)
        except Exception as e:
            alt = OUT_DIR + "\\" + fname + time.strftime("_%H%M%S") + ".xlsx"
            try:
                U.drop(columns=["sec"], errors="ignore").to_excel(alt, index=False)
                out("xlsx 被占用(%r), 已另存 %s" % (e, alt))
            except Exception as e2:
                out("xlsx 写出失败 %r / %r (csv 已写出)" % (e, e2))

        # ================= 12. 统计 =================
        out("")
        out("################ 资产覆盖(按事件来源) ################")
        items = [("ch1前视", U.ch1_可读 > 0), ("ch2座舱", U.ch2_可读 > 0), ("ch3踏板", U.ch3_可读 > 0),
                 ("三通道", U["通道(可读)"] == "123"), ("表格轨迹", U.有表格轨迹), ("NPY轨迹", U.有NPY轨迹), ("有轨迹(任一)", U.有轨迹),
                 ("0920原因", U["在0920"]), ("NPY全部", U.NPY全部脱离), ("NPY关键", U.NPY关键脱离)] + \
                [(lab, U["路侧_" + lab] != "") for lab in RS_TYPES.values()] + [("龙门架同VIN", U["路侧_龙门架(同VIN)"] != "")]
        srcs = list(U["来源"].value_counts().index)
        out("  %-12s %6s | " % ("资产", "全部") + " ".join("%9s" % s[:8] for s in srcs))
        out("  %-12s %6d | " % ("事件数", len(U)) + " ".join("%9d" % (U["来源"] == s).sum() for s in srcs))
        for lab, m in items:
            out("  %-12s %6d | " % (lab, m.sum()) + " ".join("%9d" % (m & (U["来源"] == s)).sum() for s in srcs))
        out("")
        out("################ 分类 ################")
        for c, g in U.groupby("类别"):
            out("  %-24s %5d  三通道=%d 表格轨迹=%d NPY轨迹=%d 路侧=%d  %s~%s" % (c, len(g), (g["通道(可读)"] == "123").sum(),
                g.有表格轨迹.sum(), g.有NPY轨迹.sum(), g.有路侧.sum(), g.日期.min(), g.日期.max()))
        check("分类合计=事件数", U["类别"].value_counts().sum() == len(U))
        nt = U[~U.有轨迹 & (U.veid >= 0)]
        out("  有视频但无连续轨迹的事件=%d: ±30s内只有稀疏点=%d(点数中位=%d, 只能定位不能复现)  ±30s内无点但当天有=%d  当天完全无数据=%d" % (
            len(nt), (nt.轨迹_点数 > 0).sum(), nt[nt.轨迹_点数 > 0].轨迹_点数.median() if (nt.轨迹_点数 > 0).any() else 0,
            ((nt.轨迹_点数 == 0) & nt.当天有表格轨迹).sum(), (~nt.当天有表格轨迹).sum()))
        for f, n in nt[nt.轨迹_点数 > 0].轨迹_原始文件.value_counts().head(3).items():
            out("     稀疏点来源 %4d  %s" % (n, f))
        out("  前人35=%d ; 视频事件: 在0920=%d  清单外有ch1+轨迹=%d  清单外仅ch1无轨迹=%d" % (U["前人35"].sum(),
            (U["在0920"] & (U.veid >= 0)).sum(), (~U["在0920"] & has1 & U.有轨迹).sum(), (~U["在0920"] & has1 & ~U.有轨迹).sum()))
        ab = U[U["类别"].str[0].isin(["A", "B"]) & U.有表格轨迹 & U.跳变_偏差s.notna()]
        check("A/B 类表格轨迹的接管跳变与事件时间一致(<=30s)", (ab.跳变_偏差s.abs() <= 30).all(),
              "有跳变信息=%d 超出=%d" % (len(ab), (ab.跳变_偏差s.abs() > 30).sum()))

        # ================= 13. E 类逐条确认 =================
        Ecl = U[U["类别"].str.startswith("E")].sort_values("事件时间")
        out("")
        out("################ E 类(无视频,轨迹+路侧) 逐条确认: %d 条 ################" % len(Ecl))
        out("  VIN后6 | 事件时间 | 来源 | 轨迹(秒/偏移/跳变) | 龙门架路口(案例时间差s) | 周边参与者 | 原因")
        for _, r in Ecl.head(40).iterrows():
            out("  %s | %s | %s | %ds/%s/%s | %s(%s) | %s | %s" % (r.vin[-6:], str(r.事件时间)[:19], r["来源"], r.轨迹_秒, r.轨迹_偏移,
                "" if pd.isna(r.跳变_偏差s) else "%+.0fs" % r.跳变_偏差s, str(r["路侧_龙门架路口(同VIN)"])[:30], "" if pd.isna(r["路侧_龙门架案例时间差s"]) else "%.0f" % r["路侧_龙门架案例时间差s"],
                "有" if r["路侧_周边交通参与者"] else "-", str(r.get("描述", ""))[:16]))
        eg = Ecl[Ecl["路侧_龙门架(同VIN)"] != ""]
        check("E类龙门架: 案例目录VIN一致且案例时间与事件相差<=180s", (eg["路侧_龙门架案例时间差s"] <= 180).all(),
              "龙门架=%d 超出=%d" % (len(eg), (eg["路侧_龙门架案例时间差s"] > 180).sum()))
        check("E类都有表格或NPY轨迹", Ecl.有轨迹.all())

        # ================= 15. 数据地址(原始)与匹配方法 =================
        out("")
        out("################ 数据地址(原始位置)与匹配方法 ################")
        def top(s):
            f = s.fillna("").str.split(";").str[0]
            d = f.str.extract(r"^([A-Za-z]:\\[^\\]+)", expand=False)
            return d.fillna(f.map(lambda x: os.path.dirname(os.path.dirname(x)) if x else np.nan))
        for c, g in U.groupby("类别"):
            vp = g.ch1_原始路径.fillna("").where(g.ch1_原始路径.fillna("") != "", g.ch3_原始路径.fillna(""))
            vd = top(vp).value_counts().head(4)
            tf = g[g.有表格轨迹].轨迹_原始文件.value_counts().head(2)
            out("  %s" % c)
            out("     视频: %s" % (" ".join("%s:%d" % (a, b) for a, b in vd.items()) or "-"))
            out("     轨迹: %s%s" % (" ; ".join("%s(%d)" % (a, b) for a, b in tf.items()) or "-",
                                  ("  + NPY:%d" % g.有NPY轨迹.sum()) if g.有NPY轨迹.any() else ""))
        out("  索引: event_key = VIN_YYYYMMDD_HHMMSS(北京时间), 同VIN相差<=60s 归为同一事件")
        out("  视频: 路径中的VIN + 文件名 ch{1|2|3}_{起}_{止}; 多副本取原始目录那份, 其余副本列在 ch*_全部副本")
        out("  0920: VIN + disengage_time; 轨迹: VIN + 事件±30s(每个文件自动选 0/+8h/-8h), 同名同大小的拷贝只读原始那份")
        out("  NPY: labels 的 VIN+时间 ±60s, 行号对应同目录3维样本(31帧); 路侧json: 时段覆盖事件且距事件<=%dm; 龙门架: 时段重叠且案例目录VIN一致" % RS_RADIUS)

        return U

    U = process(U, H, days, "主表: 2025年之前", "事件资产表")
    U25 = process(U25, H25, day25, "2025年(单独统计,同样的分类)", "事件资产表_2025")

    # ================= 14. 路侧覆盖 / 2025 专项 =================
    out("")
    out("################ 路侧覆盖时段(participant) 概览 ################")
    if len(PJ):
        seg = PJ.dropna(subset=["s0"]).copy()
        seg["年"] = pd.to_datetime(seg.s0, unit="s").dt.year
        for (y, d), g in seg.groupby(["年", "dir"]):
            out("  %d %-55s 文件=%4d 时长=%5.1fh  %s~%s  设备(%.4f,%.4f)" % (y, d[-55:], len(g), (g.s1 - g.s0).sum() / 3600,
                sec2str(g.s0.min())[:16], sec2str(g.s1.max())[:16], g.dlat.iloc[0], g.dlon.iloc[0]))
    if len(RH):
        R1["年"] = pd.to_datetime(R1.sec, unit="s").dt.year
        out("  覆盖时段内、离设备<=%dm 的自车轨迹:" % RS_NEAR)
        for y, g in R1.groupby("年"):
            out("    %d年: 车辆=%d 点(秒)=%d 天=%d  来源文件: %s" % (y, g.vin.nunique(), len(g), g.day.nunique(),
                "  ".join("%s:%d" % (f.replace("/", "\\").split("\\")[-1][:28], n) for f, n in g.file.value_counts().head(3).items())))
        rse = rs_events.assign(年=pd.to_datetime(rs_events.sec, unit="s").dt.year) if len(rs_events) else rs_events
        out("  覆盖时段内的接管(drive_mode 1->0): %s" % ("  ".join("%d年:%d(车%d)" % (y, len(g), g.vin.nunique()) for y, g in rse.groupby("年")) or "0"))
    else:
        out("  覆盖时段内没有找到任何自车轨迹点")
    rsdir = FS[FS.file.str.contains("运行安全评价")]
    if len(rsdir):
        out("  运行安全评价 TTC 案例轨迹文件=%d  时间 %s ~ %s  (逐文件见 traj_files.csv)" % (len(rsdir),
            rsdir.tmin[rsdir.tmin != ""].min()[:10], rsdir.tmax[rsdir.tmax != ""].max()[:10]) + " (文件原始时间,未做时区换算)")
    out("  (2025年事件的分类见上方\"2025年\"部分, 表: 事件资产表_2025.xlsx)")

    out("")
    out("检查项 PASS=%d FAIL=%d  资产表: %s\\事件资产表.xlsx 与 事件资产表_2025.xlsx" % (sum(c[1] for c in CHECKS), sum(not c[1] for c in CHECKS), OUT_DIR))
    for n_, ok, d_ in CHECKS:
        if not ok:
            out("  FAIL: %s  %s" % (n_, d_))
    out("=== END %s %s  用时%.0fs ===" % (NAME, VERSION, time.time() - t00))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
