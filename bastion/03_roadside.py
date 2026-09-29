# -*- coding: utf-8 -*-
# 03_roadside.py : 路侧数据盘点（龙门架视频 + participant json），只读
# 依赖 01_scan_files 生成的 file_index.csv；需要 pandas
import os, sys, re, hashlib, time
import pandas as pd

NAME, VERSION = "03_roadside", "v1"
INDEX = r"D:\takeover_audit\01_scan\file_index.csv"
OUT_DIR = r"D:\takeover_audit\03_roadside"
HEAD_BYTES = 512 * 1024   # participant json 只读开头这么多字节做抽样
RE_GV = re.compile(r"^(\d+)_(.+?)_(\d{14})-(\d{14})\.", re.I)          # 2303_曹安公路-嘉松北路固态一体机-东北相机_20240511155624-20240511160024.mp4
RE_CASE = re.compile(r"(\d+)-([A-HJ-NPR-Z0-9]{17})-(\d{4}-\d{2}-\d{2}) ?(\d{6})")  # 7-<VIN>-2024-05-11 155824
RE_PJ = re.compile(r"participant_(\d{14})-(\d{14})", re.I)
RE_OTHER_RS = re.compile(r"^(vehicle_track|traffic_flow|signal|event|camera_url)_(\d{14})-(\d{14})", re.I)


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


def merge_segments(df, gap_s=60):
    """把时间窗合并成连续段，返回段列表 DataFrame。"""
    df = df.dropna(subset=["start", "end"]).sort_values("start")
    segs = []
    for s, e in zip(df.start, df.end):
        if segs and (s - segs[-1][1]).total_seconds() <= gap_s:
            segs[-1][1] = max(segs[-1][1], e)
        else:
            segs.append([s, e])
    return pd.DataFrame(segs, columns=["start", "end"])


def sample_json(path):
    try:
        with open(path, "rb") as f:
            b = f.read(HEAD_BYTES).decode("utf-8", "replace")
    except Exception as e:
        return {"err": repr(e)}
    r = {}
    m = re.search(r'"mapDeviceId"\s*:\s*"([^"]*)"', b); r["device"] = m.group(1) if m else ""
    links = re.findall(r'"mapLocationLinkName"\s*:\s*"([^"]*)"', b)
    r["links"] = "|".join(sorted(set(x for x in links if x and x != "null")))[:200]
    ts = re.findall(r'"timestamp"\s*:\s*(\d{13})', b)
    r["ts_first"] = pd.to_datetime(int(ts[0]), unit="ms") + pd.Timedelta(hours=8) if ts else pd.NaT
    lat = re.findall(r'"ptcPosLat"\s*:\s*(\d+)', b); lon = re.findall(r'"ptcPosLon"\s*:\s*(\d+)', b)
    r["lat"] = int(lat[0]) / 1e7 if lat else None
    r["lon"] = int(lon[0]) / 1e7 if lon else None
    r["n_ptc_in_head"] = len(set(re.findall(r'"ptcId"\s*:\s*(\d+)', b)))
    r["keys"] = ",".join(dict.fromkeys(re.findall(r'"(\w+)"\s*:', b[:8000]))) if b else ""
    return r


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))
    fi = pd.read_csv(INDEX, dtype=str, keep_default_na=False)
    fi = fi[~fi.dir.str.lower().str.contains("takeover_audit")]
    fi["size_bytes"] = pd.to_numeric(fi.size_bytes, errors="coerce").fillna(0)
    fi["path"] = fi.dir + "\\" + fi.name

    # ---------------- 龙门架视频 ----------------
    gv = fi[fi.kind == "gantry_video"].copy()
    p = gv.name.str.extract(RE_GV)
    gv["cam_id"], gv["cam"] = p[0], p[1]
    gv["start"] = pd.to_datetime(p[2], format="%Y%m%d%H%M%S", errors="coerce")
    gv["end"] = pd.to_datetime(p[3], format="%Y%m%d%H%M%S", errors="coerce")
    gv["inter"] = gv.cam.str.extract(r"^(.+?路-.+?路)", expand=False)
    c = gv.path.str.extract(RE_CASE)
    gv["case_vin"] = c[1]
    gv["case_t"] = pd.to_datetime(c[2] + " " + c[3], format="%Y-%m-%d %H%M%S", errors="coerce")
    uq = gv.drop_duplicates(["cam", "start", "end"])
    out("[gantry] 文件=%d  %.1fGB  名字解析失败=%d  去重后片段=%d" % (
        len(gv), gv.size_bytes.sum() / 2**30, gv.start.isna().sum(), len(uq)))
    out("         时间=%s ~ %s  时长(s): %s" % (uq.start.min(), uq.end.max(), "  ".join(
        "%s:%d" % (int(k) if k == k else k, n) for k, n in (uq.end - uq.start).dt.total_seconds().value_counts().head(5).items())))
    cases = gv.dropna(subset=["case_vin"]).drop_duplicates(["case_vin", "case_t"])
    out("         案例目录(VIN+时间)=%d  VIN=%d  不在案例目录的片段=%d" % (
        len(cases), cases.case_vin.nunique(), uq.case_vin.isna().sum()))
    out("         路口(去重片段数): " + "  ".join("%s:%d" % (k, n) for k, n in uq.inter.fillna("?").value_counts().head(12).items()))
    out("         一级目录(文件数): " + "  ".join("%s:%d" % (k.split("\\")[-1], n) for k, n in gv["top"].value_counts().head(8).items()))
    gv.to_csv(os.path.join(OUT_DIR, "gantry_videos.csv"), index=False, encoding="utf-8-sig")

    # ---------------- participant json ----------------
    pj = fi[fi.kind == "participant_json"].copy()
    p = pj.name.str.extract(RE_PJ)
    pj["start"] = pd.to_datetime(p[0], format="%Y%m%d%H%M%S", errors="coerce")
    pj["end"] = pd.to_datetime(p[1], format="%Y%m%d%H%M%S", errors="coerce")
    out("")
    out("[pjson] 文件=%d  %.1fGB  名字解析失败=%d  时间=%s ~ %s" % (
        len(pj), pj.size_bytes.sum() / 2**30, pj.start.isna().sum(), pj.start.min(), pj.end.max()))
    t0 = time.time()
    rows = []
    for i, path in enumerate(pj.path):
        rows.append(sample_json(path))
        if (i + 1) % 200 == 0:
            print("  ... sampled %d/%d  %.0fs" % (i + 1, len(pj), time.time() - t0))
    s = pd.DataFrame(rows, index=pj.index)
    pj = pd.concat([pj, s], axis=1)
    pj["small"] = pj.size_bytes < 10 * 1024
    uq = pj.drop_duplicates(["start", "end", "device", "size_bytes"])
    out("        去重后=%d  <10KB(几乎空)=%d  抽样出错=%d" % (len(uq), uq.small.sum(), pj.get("err", pd.Series()).notna().sum()))
    fn_vs_ts = (pj.ts_first - pj.start).dt.total_seconds().dropna()
    out("        文件名时间 vs 首条timestamp(+8h) 差(s): 中位=%.0f  |差|<=600的比例=%.0f%%" % (
        fn_vs_ts.median() if len(fn_vs_ts) else float("nan"), 100 * (fn_vs_ts.abs() <= 600).mean() if len(fn_vs_ts) else 0))
    out("        设备(去重文件数): " + "  ".join("%s:%d" % (k[-20:], n) for k, n in uq.device.replace("", "?").value_counts().head(6).items()))
    out("        路名(出现文件数): " + "  ".join("%s:%d" % (k, n) for k, n in uq.links.str.split("|").explode().replace("", None).dropna().value_counts().head(10).items()))
    out("        坐标范围: lat %.4f~%.4f  lon %.4f~%.4f" % (uq.lat.min(), uq.lat.max(), uq.lon.min(), uq.lon.max()))
    out("        按目录(去重文件数, 时间范围):")
    top_dirs = uq.dir.value_counts().head(10)
    for d, n in top_dirs.items():
        g = uq[uq.dir == d]
        out("          %-45s %4d  %s ~ %s" % (d[-45:], n, g.start.min(), g.end.max()))
    segs = merge_segments(uq[~uq.small])
    hours = ((segs.end - segs.start).dt.total_seconds().sum() / 3600) if len(segs) else 0
    out("        连续覆盖段=%d  覆盖总时长=%.1fh  覆盖天数=%d" % (len(segs), hours, uq.start.dt.date.nunique()))
    out("        按月(去重文件数): " + "  ".join("%s:%d" % (k, n) for k, n in uq.start.dt.strftime("%y%m").value_counts().sort_index().items()))
    out("        字段(首条): " + (pj["keys"].dropna().iloc[0][:300] if len(pj) else ""))
    pj.to_csv(os.path.join(OUT_DIR, "participant_files.csv"), index=False, encoding="utf-8-sig")
    segs.to_csv(os.path.join(OUT_DIR, "participant_segments.csv"), index=False, encoding="utf-8-sig")

    # ---------------- 同批次的其他路侧 json ----------------
    oj = fi[fi.ext == ".json"].copy()
    m = oj.name.str.extract(RE_OTHER_RS)
    oj = oj[m[0].notna()]
    out("")
    out("[other roadside json] " + "  ".join("%s:%d(%.1fGB)" % (k, len(g), g.size_bytes.sum() / 2**30)
                                              for k, g in oj.groupby(m[0].str.lower().reindex(oj.index))))
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(os.path.join(OUT_DIR, "summary.txt"), "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
