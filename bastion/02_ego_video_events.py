# -*- coding: utf-8 -*-
# 02_ego_video_events.py : 自车视频解析 + 0920 事件表统计 + 两者关联（只读）
# 依赖 01_scan_files 生成的 file_index.csv；需要 pandas、openpyxl
# 用法：python 02_ego_video_events.py  [0920表的完整路径，可选，默认自动在索引里找]
import os, sys, re, hashlib, time
from collections import Counter
import pandas as pd

NAME, VERSION = "02_ego_video_events", "v1"
INDEX = r"D:\takeover_audit\01_scan\file_index.csv"
OUT_DIR = r"D:\takeover_audit\02_ego_video"
MERGE_S = 60      # 同一VIN、片段中点相差<=60s 视为同一视频事件
MATCH_S = 60      # 0920 事件时间与视频事件中点相差<=60s（或落在片段内）视为匹配
RE_EGO = re.compile(r"^ch(\d)_(\d{12})_(\d{12})\.", re.I)


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


def find_col(df, *keys):
    for k in keys:
        for c in df.columns:
            if str(c).strip().lower() == k.lower():
                return c
    for k in keys:
        for c in df.columns:
            if k.lower() in str(c).strip().lower():
                return c
    return None


def vc(series, n=8):
    c = series.fillna("<空>").astype(str).str.strip().replace("", "<空>").value_counts()
    return "  ".join("%s:%d" % (k, v) for k, v in c.head(n).items())


def load_0920(fi):
    if len(sys.argv) > 1:
        cands = [sys.argv[1]]
    else:
        m = fi[(fi.kind == "table") & fi.name.str.contains("脱离事件汇总") & fi.name.str.contains("0920")
               & ~fi.dir.str.lower().str.contains("takeover_audit")]
        m = m.sort_values("size_bytes", ascending=False)
        cands = [d + "\\" + n for d, n in zip(m.dir, m.name)]
        out("[0920] candidates=%d (用最大的一个；如不对，把正确路径作为参数传入)" % len(cands))
        for p in cands[:4]:
            out("   " + p[-100:])
    if not cands:
        out("[0920] NOT FOUND"); return None
    path = cands[0]
    sheets = pd.read_excel(path, sheet_name=None)
    for sn, df in sheets.items():
        if find_col(df, "disengage_time") is not None and find_col(df, "vin") is not None:
            out("[0920] use %s  sheet=%s  shape=%s" % (os.path.basename(path), sn, df.shape))
            return df
    out("[0920] no sheet with disengage_time+vin; sheets=%s" % list(sheets)); return None


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))
    fi = pd.read_csv(INDEX, dtype=str, keep_default_na=False)
    fi["size_bytes"] = pd.to_numeric(fi.size_bytes, errors="coerce").fillna(0)

    # ---------------- 0920 事件表 ----------------
    ev = load_0920(fi)
    if ev is not None:
        c_t, c_v = find_col(ev, "disengage_time"), find_col(ev, "vin")
        c_d, c_valid = find_col(ev, "描述"), find_col(ev, "有效视频")
        c_emg = find_col(ev, "是否紧急接管")
        ev = ev.copy()
        ev["t"] = pd.to_datetime(ev[c_t], errors="coerce")
        ev["vin_"] = ev[c_v].astype(str).str.strip().str.upper()
        ev = ev[ev.t.notna() & (ev.vin_.str.len() == 17)].copy()
        desc = ev[c_d].fillna("").astype(str).str.strip() if c_d else pd.Series("", index=ev.index)
        ev["has_desc"] = ~desc.isin(["", "nan", "None", "无"])
        dup = ev.duplicated(["vin_", "t"]).sum()
        out("[0920] 有效行=%d  重复(vin+时间)=%d  VIN=%d  时间=%s ~ %s" % (
            len(ev), dup, ev.vin_.nunique(), ev.t.min(), ev.t.max()))
        out("       按月: " + "  ".join("%s:%d" % (k, v) for k, v in ev.t.dt.strftime("%y%m").value_counts().sort_index().items()))
        out("       描述非空=%d (%.0f%%)" % (ev.has_desc.sum(), 100 * ev.has_desc.mean()))
        if c_valid: out("       有效视频: " + vc(ev[c_valid]))
        if c_emg: out("       是否紧急接管: " + vc(ev[c_emg]))
        out("       列: " + ",".join(str(c) for c in ev.columns[:24]))

    # ---------------- 自车视频 ----------------
    v = fi[(fi.kind == "ego_video") & ~fi.dir.str.lower().str.contains("takeover_audit")].copy()
    p = v.name.str.extract(RE_EGO)
    v["ch"] = p[0]
    v["start"] = pd.to_datetime(p[1], format="%y%m%d%H%M%S", errors="coerce")
    v["end"] = pd.to_datetime(p[2], format="%y%m%d%H%M%S", errors="coerce")
    v["dur"] = (v.end - v.start).dt.total_seconds()
    v["top"] = v["top"].astype(str)
    novin = (v.vin == "").sum()
    out("")
    out("[video] 文件=%d  %.1fGB  路径无VIN=%d  时长分布(s): %s" % (
        len(v), v.size_bytes.sum() / 2**30, novin,
        "  ".join("%s:%d" % (int(k) if k == k else k, c) for k, c in v.dur.value_counts().head(6).items())))
    out("        小于100KB的文件=%d" % (v.size_bytes < 100 * 1024).sum())
    # 去重：同 VIN+通道+起止 为同一片段
    key = ["vin", "ch", "start", "end"]
    g = v.groupby(key, dropna=False)
    clips = g.agg(copies=("name", "size"), size_min=("size_bytes", "min"), size_max=("size_bytes", "max"),
                  dirs=("dir", lambda s: " | ".join(sorted(set(s))))).reset_index()
    out("        去重后片段=%d  (有多份拷贝的=%d, 拷贝间大小不一致=%d)" % (
        len(clips), (clips.copies > 1).sum(), (clips.size_min != clips.size_max).sum()))
    out("        拷贝来源(一级目录 文件数): " + "  ".join("%s:%d" % (k.split("\\")[-1], c) for k, c in v["top"].value_counts().head(10).items()))
    clips.to_csv(os.path.join(OUT_DIR, "ego_clips.csv"), index=False, encoding="utf-8-sig")

    # 窗口：同 VIN+起止 的几个通道合在一起
    w = clips.groupby(["vin", "start", "end"], dropna=False).ch.apply(lambda s: "".join(sorted(set(s)))).reset_index()
    w["mid"] = w.start + (w.end - w.start) / 2
    # 视频事件：同VIN，中点相近的窗口合并
    w = w.sort_values(["vin", "mid"]).reset_index(drop=True)
    eid, last_vin, last_mid, cur = [], None, None, 0
    for vin_, mid in zip(w.vin, w.mid):
        if vin_ != last_vin or vin_ == "" or pd.isna(mid) or pd.isna(last_mid) or (mid - last_mid).total_seconds() > MERGE_S:
            cur += 1
        eid.append(cur); last_vin, last_mid = vin_, mid
    w["veid"] = eid
    ve = w.groupby("veid").agg(vin=("vin", "first"), start=("start", "min"), end=("end", "max"),
                                mid=("mid", "first"), n_windows=("mid", "size"),
                                chans=("ch", lambda s: "".join(sorted(set("".join(s)))))).reset_index()
    out("        时间窗=%d  视频事件=%d  VIN=%d  时间=%s ~ %s" % (
        len(w), len(ve), ve.vin[ve.vin != ""].nunique(), ve.start.min(), ve.end.max()))
    out("        视频事件按月: " + "  ".join("%s:%d" % (k, c) for k, c in ve.mid.dt.strftime("%y%m").value_counts().sort_index().items()))
    out("        通道组合(事件数): " + "  ".join("ch%s:%d" % (k, c) for k, c in ve.chans.value_counts().items()))

    # ---------------- 关联 ----------------
    if ev is not None:
        ve["in0920"] = 0; ve["has_desc"] = 0; ve["dt_s"] = None
        ev["veid"] = None; ev["dt_s"] = None
        by_vin = {k: d for k, d in ve.groupby("vin")}
        off8 = 0
        for i, r in ev.iterrows():
            d = by_vin.get(r.vin_)
            if d is None:
                continue
            dt = (d.mid - r.t).dt.total_seconds()
            inside = (d.start <= r.t) & (r.t <= d.end)
            ok = inside | (dt.abs() <= MATCH_S)
            if ok.any():
                j = dt[ok].abs().idxmin()
                ev.at[i, "veid"] = d.at[j, "veid"]; ev.at[i, "dt_s"] = dt[j]
                ve.loc[ve.veid == d.at[j, "veid"], ["in0920", "dt_s"]] = [1, dt[j]]
                if r.has_desc:
                    ve.loc[ve.veid == d.at[j, "veid"], "has_desc"] = 1
            elif ((dt.abs() - 8 * 3600).abs() <= MATCH_S).any():
                off8 += 1
        m = ev.veid.notna()
        out("")
        out("[match] 0920事件有自车视频=%d / %d   (若按±8h才对得上的=%d)" % (m.sum(), len(ev), off8))
        dts = pd.to_numeric(ev.dt_s[m], errors="coerce").abs()
        out("        |视频中点-事件时间|: <=5s:%d  <=30s:%d  <=60s:%d" % ((dts <= 5).sum(), (dts <= 30).sum(), (dts <= 60).sum()))
        if c_valid:
            out("        0920'有效视频' x 找到视频:")
            ct = pd.crosstab(ev[c_valid].fillna("<空>").astype(str), m.map({True: "找到", False: "没找到"}))
            for idx, r in ct.iterrows():
                out("          %-6s %s" % (idx, "  ".join("%s:%d" % (c, r[c]) for c in ct.columns)))
        out("        视频事件: 在0920=%d (有描述=%d, 无描述=%d)  清单外=%d" % (
            ve.in0920.sum(), ((ve.in0920 == 1) & (ve.has_desc == 1)).sum(),
            ((ve.in0920 == 1) & (ve.has_desc == 0)).sum(), (ve.in0920 == 0).sum()))
        out("        在0920的视频事件 通道组合: " + "  ".join("ch%s:%d" % (k, c) for k, c in ve[ve.in0920 == 1].chans.value_counts().items()))
        out("        清单外视频事件按月: " + "  ".join("%s:%d" % (k, c) for k, c in ve[ve.in0920 == 0].mid.dt.strftime("%y%m").value_counts().sort_index().items()))
        ev.to_csv(os.path.join(OUT_DIR, "events0920_with_video.csv"), index=False, encoding="utf-8-sig")
    ve.to_csv(os.path.join(OUT_DIR, "video_events.csv"), index=False, encoding="utf-8-sig")
    w.to_csv(os.path.join(OUT_DIR, "video_windows.csv"), index=False, encoding="utf-8-sig")
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(os.path.join(OUT_DIR, "summary.txt"), "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
