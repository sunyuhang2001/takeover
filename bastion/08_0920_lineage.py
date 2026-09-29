# -*- coding: utf-8 -*-
# 08_0920_lineage.py : 0920 表是怎么来的、每一列怎么来的（只读）
#   1) 逐列画像      2) 筛选条件猜测(acc_long_min 阈值)   3) 是否紧急接管 能否用阈值复现
#   4) 用 all927 轨迹重算 acc_long_min / acc_lat_abs_max / acc_long / acc_lat，看窗口多大能对上
#   5) 在 switch 平台表里找 0920 事件：命中率、是不是"switch 事件里 acc<=阈值"的子集
#   6) 找列名和 0920 高度重合的中间表（按时间排序看演变）  7) 代码里给这些列赋值的行
# 依赖 01/02/04 的输出；需要 pandas、numpy、openpyxl
import os, sys, re, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "08_0920_lineage", "v2"
BASE = r"D:\takeover_audit"
OUT_DIR = BASE + r"\08_lineage"
MATCH_S = 60
CODE_EXT = {".py", ".ipynb", ".sql", ".m", ".r"}
COL_TOKENS = ["acc_long_min", "acc_lat_abs_max", "cross_name", "是否紧急接管", "紧急接管", "主车行为", "目标物行为",
              "与目标物相对关系", "道路类型", "有效视频", "mode_switch_acceleration_min", "disengage_time", "distance"]


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
    smp = s.dropna().astype(str).head(2000)
    if s.dtype.kind in "iuf" or (len(smp) and smp.str.fullmatch(r"\d{10,13}(\.\d+)?").mean() > 0.9):
        x = pd.to_numeric(s, errors="coerce")
        sec = x / 1000.0 if x.median() > 1e12 else x
        return (sec + 8 * 3600).round()
    try:
        t = pd.to_datetime(s, errors="coerce", infer_datetime_format=True)
    except TypeError:
        t = pd.to_datetime(s, errors="coerce", format="mixed")
    return ((t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("float")


def read_any(path, **kw):
    if path.lower().endswith(".csv"):
        for enc in ("utf-8-sig", "gbk"):
            try:
                return pd.read_csv(path, encoding=enc, low_memory=False, **kw)
            except UnicodeDecodeError:
                continue
    return pd.read_excel(path, **kw)


def read_text(p):
    b = open(p, "rb").read()
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))
    fi = pd.read_csv(BASE + r"\01_scan\file_index.csv", dtype=str, keep_default_na=False)
    fi["path"] = fi.dir + "\\" + fi.name
    src = fi[fi.name.str.contains("脱离事件汇总") & fi.name.str.lower().str.endswith(".xlsx")
             & ~fi.dir.str.lower().str.contains("takeover_audit")].path.iloc[0]
    ev = pd.read_excel(src, sheet_name=0)
    out("[0920] %s  shape=%s" % (src[-60:], ev.shape))

    # ---------- 1) 逐列画像 ----------
    out("")
    out("[1] 逐列: 非空 / 不同值 / 范围或前几个取值")
    for c in ev.columns:
        s = ev[c]
        nn, nu = s.notna().sum(), s.nunique()
        if pd.api.types.is_numeric_dtype(s):
            desc = "min=%.3f p50=%.3f max=%.3f" % (s.min(), s.median(), s.max())
        elif "time" in str(c).lower():
            t = pd.to_datetime(s, errors="coerce"); desc = "%s ~ %s" % (t.min(), t.max())
        else:
            desc = " ".join("%s:%d" % (str(k)[:10], v) for k, v in s.astype(str).value_counts().head(6).items())
        out("  %-16s %5d %5d  %s" % (str(c)[:16], nn, nu, desc[:110]))

    num = lambda c: pd.to_numeric(ev[c], errors="coerce") if c in ev.columns else None
    alm, alat = num("acc_long_min"), num("acc_lat_abs_max")
    # ---------- 2) 筛选阈值 ----------
    out("")
    if alm is not None:
        out("[2] acc_long_min: max=%.3f (<=-2的比例=%.1f%%)  ;  acc_lat_abs_max: min=%.3f max=%.3f" % (
            alm.max(), 100 * (alm <= -2).mean(), alat.min() if alat is not None else np.nan, alat.max() if alat is not None else np.nan))
        if alat is not None:
            both = ((alm <= -2) | (alat >= 2))
            out("    满足 acc_long_min<=-2 或 acc_lat_abs_max>=2 的比例=%.1f%%;  只满足横向的=%d" % (
                100 * both.mean(), ((alm > -2) & (alat >= 2)).sum()))
        dup = [c for c in ev.columns if str(c).startswith("acc_lat_abs_max")]
        if len(dup) > 1:
            out("    %s 两列完全相同的比例=%.1f%%" % (dup, 100 * (ev[dup[0]] == ev[dup[1]]).mean()))

    # ---------- 3) 是否紧急接管 能否用阈值复现 ----------
    if "是否紧急接管" in ev.columns and alm is not None:
        y = ev["是否紧急接管"].astype(str).str.strip() == "是"
        out("")
        out("[3] 是否紧急接管 是=%d 否=%d ;  acc_long_min 中位 是=%.2f 否=%.2f ; acc_lat_abs_max 中位 是=%.2f 否=%.2f" % (
            y.sum(), (~y).sum(), alm[y].median(), alm[~y].median(),
            alat[y].median() if alat is not None else np.nan, alat[~y].median() if alat is not None else np.nan))
        best = (0, None)
        for a in np.arange(-2.0, -6.01, -0.1):
            for b in list(np.arange(1.0, 5.01, 0.25)) + [99]:
                pred = (alm <= a) | ((alat >= b) if alat is not None else False)
                acc = (pred == y).mean()
                if acc > best[0]:
                    best = (acc, (round(a, 2), b))
        out("    最佳阈值规则: acc_long_min<=%.2f 或 acc_lat_abs_max>=%s  -> 与人工一致 %.1f%%" % (best[1][0], best[1][1], 100 * best[0]))
        out("    (若接近100%说明是按阈值算的; 若只有60-70%说明是人工看视频判的)")

    # ---------- 4) 用 all927 重算加速度列 ----------
    a9 = fi[fi.name.str.lower().isin(["all927.csv", "all927.xlsx"]) & ~fi.dir.str.lower().str.contains("takeover_audit")]
    a9 = a9.sort_values("name").path.tolist()
    out("")
    if a9:
        tr = read_any(a9[0])
        out("[4] all927: %s  行=%d  列=%s" % (a9[0][-50:], len(tr), ",".join(map(str, tr.columns))[:160]))
        tcol = next((c for c in ("dis_engage_time", "position_time", "positiontime", "position_time_sql") if c in tr.columns), None)
        tr["ts"] = to_sec(tr[tcol]) if tcol else np.nan
        tr["t0"] = to_sec(tr["disengage_time"])
        tr["dt"] = tr.ts - tr.t0
        med = tr.dt.median()
        if pd.notna(med) and abs(med) > 4 * 3600:          # 逐行时间是 UTC 时补 8h
            tr["dt"] = tr.dt + (8 * 3600 if med < 0 else -8 * 3600)
        out("    逐行时间列=%s  与disengage_time差的中位=%.0fs(修正后 %.0fs)" % (tcol, med, tr.dt.median()))
        tr["vin"] = tr.vin.astype(str).str.upper().str.strip()
        ev["vin_"] = ev.vin.astype(str).str.upper().str.strip()
        ev["t0"] = to_sec(ev.disengage_time)
        for col, fn, tgt in (("acc_long", "min", "acc_long_min"), ("acceleration", "min", "acc_long_min"),
                             ("acc_lat", "absmax", "acc_lat_abs_max"), ("acc_long", "at0", "acc_long"), ("acc_lat", "at0", "acc_lat")):
            if col not in tr.columns or tgt not in ev.columns:
                continue
            res = []
            for w in ([0] if fn == "at0" else [3, 5, 10, 15, 20, 30, 60]):
                sub = tr[tr.dt.abs() <= w]
                v = pd.to_numeric(sub[col], errors="coerce")
                if fn == "min":
                    g = v.groupby([sub.vin, sub.t0]).min()
                elif fn == "absmax":
                    g = v.abs().groupby([sub.vin, sub.t0]).max()
                else:
                    g = v.groupby([sub.vin, sub.t0]).first()
                m = ev.join(g.rename("re"), on=["vin_", "t0"])
                ok = (pd.to_numeric(m[tgt], errors="coerce") - m.re).abs() <= 0.011
                res.append("±%ds:%.0f%%" % (w, 100 * ok.mean()))
            out("    %-15s <- %s(%s)  吻合率: %s" % (tgt, fn, col, "  ".join(res)))
        if "acc_long_min" in tr.columns:
            m = ev.join(pd.to_numeric(tr.acc_long_min, errors="coerce").groupby([tr.vin, tr.t0]).first().rename("a9"), on=["vin_", "t0"])
            out("    all927 自带 acc_long_min 与 0920 相同的比例=%.1f%%" % (100 * ((m.acc_long_min - m.a9).abs() <= 0.011).mean()))
        # 事件时刻轨迹里有没有 drive_mode 1->0
        if "drive_mode" in tr.columns:
            d = tr.sort_values(["vin", "t0", "ts"])
            dm = pd.to_numeric(d.drive_mode, errors="coerce")
            sw = d[(dm.shift(1) == 1) & (dm == 0) & (d.vin == d.vin.shift(1)) & (d.t0 == d.t0.shift(1))]
            first = sw.groupby(["vin", "t0"]).dt.apply(lambda s: s.iloc[s.abs().argmin()])
            out("    轨迹里有1->0跳变的事件=%d/%d ; 跳变时刻-disengage_time: |<=1s|=%d  <=5s=%d  中位=%.0fs" % (
                len(first), ev.shape[0], (first.abs() <= 1).sum(), (first.abs() <= 5).sum(), first.median() if len(first) else np.nan))

    # ---------- 5) switch 平台表里找 0920 事件 ----------
    cat = pd.read_csv(BASE + r"\04_tables\table_catalog.csv", dtype=str, keep_default_na=False)
    sw_files = cat[cat.cols.str.contains("mode_switch_acceleration_min") & cat.cols.str.contains("vin")].drop_duplicates("path")
    sw_files = sw_files.assign(fname=sw_files.path.str.split("\\").str[-1]).drop_duplicates(["fname", "size_mb"])
    out("")
    out("[5] switch平台表(含 mode_switch_acceleration_min) 文件=%d" % len(sw_files))
    vins = set(ev.vin_)
    tmin, tmax = ev.t0.min() - 86400, ev.t0.max() + 86400
    parts, t0 = [], time.time()
    for p in sw_files.path:
        try:
            hdr = read_any(p, nrows=0).columns
            low = {str(c).lower(): c for c in hdr}
            use = [low[k] for k in ("vin", "time", "drive_mode_switch", "mode_switch_acceleration_min",
                                    "manual_reason", "enterprise", "mode_switch_duration") if k in low]
            df = read_any(p, usecols=use, dtype=str)
            df.columns = [str(c).lower() for c in df.columns]
            df["vin"] = df.vin.str.upper().str.strip()
            df = df[df.vin.isin(vins)]
            if not len(df):
                continue
            df["ts"] = to_sec(df["time"])
            df = df[(df.ts >= tmin) & (df.ts <= tmax)]
            df["file"] = p
            parts.append(df)
        except Exception as e:
            pass
    print("  ... switch 表读完 %.0fs" % (time.time() - t0))
    if parts:
        S = pd.concat(parts).drop_duplicates(["vin", "ts", "drive_mode_switch"])
        out("    0920车辆在0920时间段内的switch记录=%d  drive_mode_switch取值: %s" % (
            len(S), " ".join("%s:%d" % (k, v) for k, v in S.drive_mode_switch.value_counts().head(6).items())))
        if "manual_reason" in S.columns:
            out("    manual_reason: " + " ".join("%s:%d" % (str(k)[:12], v) for k, v in S.manual_reason.value_counts().head(8).items()))
        S = S.sort_values("ts")
        for sh, lab in ((0, "0"), (8 * 3600, "+8h"), (-8 * 3600, "-8h")):
            Ss = S.assign(ts=S.ts + sh).dropna(subset=["ts"]).sort_values("ts")
            mm = pd.merge_asof(ev.sort_values("t0").dropna(subset=["t0"]), Ss[["vin", "ts"]], left_on="t0", right_on="ts",
                               left_by="vin_", right_by="vin", direction="nearest")
            dd = (mm.ts - mm.t0).abs()
            out("    偏移%-4s 找得到(±%ds)=%d  0s=%d  <=5s=%d" % (lab, MATCH_S, (dd <= MATCH_S).sum(), (dd == 0).sum(), (dd <= 5).sum()))
        best_sh = max(((0, "0"), (8 * 3600, "+8h"), (-8 * 3600, "-8h")), key=lambda x: (
            (pd.merge_asof(ev.sort_values("t0").dropna(subset=["t0"]), S.assign(ts=S.ts + x[0]).dropna(subset=["ts"]).sort_values("ts")[["vin", "ts"]],
                           left_on="t0", right_on="ts", left_by="vin_", right_by="vin", direction="nearest").eval("abs(ts - t0)") <= 5).sum()))
        out("    采用偏移 %s" % best_sh[1])
        S = S.assign(ts=S.ts + best_sh[0]).sort_values("ts")
        m = pd.merge_asof(ev.sort_values("t0").dropna(subset=["t0"]), S[["vin", "ts", "mode_switch_acceleration_min", "drive_mode_switch"]].dropna(subset=["ts"]),
                          left_on="t0", right_on="ts", by=None, left_by="vin_", right_by="vin", direction="nearest")
        m["dt"] = (m.ts - m.t0)
        hit = m.dt.abs() <= MATCH_S
        out("    0920 事件在switch表里找得到(±%ds)=%d/%d  时间差: 0s=%d  <=5s=%d" % (
            MATCH_S, hit.sum(), len(m), (m.dt == 0).sum(), (m.dt.abs() <= 5).sum()))
        msam = pd.to_numeric(m.mode_switch_acceleration_min, errors="coerce")
        out("    acc_long_min == mode_switch_acceleration_min 的比例=%.1f%%" % (100 * ((m.acc_long_min - msam).abs() <= 0.011)[hit].mean()))
        # 0920 是不是 "switch 事件里 acc<=-2" 的全集？
        sa = pd.to_numeric(S.mode_switch_acceleration_min, errors="coerce")
        cand = S[sa <= -2]
        out("    同期同车 switch 中 mode_switch_acceleration_min<=-2 的记录=%d  (0920=%d)  ;  <=-2 且 drive_mode_switch 各取值: %s" % (
            len(cand), len(ev), " ".join("%s:%d" % (k, v) for k, v in cand.drive_mode_switch.value_counts().head(4).items())))
        S.to_csv(OUT_DIR + r"\switch_rows_0920_vins.csv", index=False, encoding="utf-8-sig")
        m.to_csv(OUT_DIR + r"\0920_vs_switch.csv", index=False, encoding="utf-8-sig")

    # ---------- 6) 列名高度重合的中间表 ----------
    target = set(str(c).strip().lower() for c in ev.columns if not str(c).startswith("Unnamed"))
    cat["cset"] = cat.cols.str.lower().str.split(",").apply(lambda l: set(x.strip() for x in l))
    cat["ov"] = cat.cset.apply(lambda s: len(s & target))
    near = cat[cat.ov >= 5].merge(fi[["path", "mtime"]], on="path", how="left").sort_values("mtime")
    near = near.drop_duplicates(["sig", "nrow"])
    out("")
    out("[6] 与0920列名重合>=5的表(去重结构+行数, 按修改时间):  重合/行数/多出的列 | 路径")
    for _, r in near.tail(18).iterrows():
        extra = ",".join(sorted(r.cset - target))[:60]
        out("  %s  %2d %7s  +%s | %s" % (r.mtime[:10], r.ov, r.nrow or "-", extra, r.path[-55:]))

    # ---------- 7) 代码里给这些列赋值的行 ----------
    low_dir = fi.dir.str.lower()
    code = fi[fi.ext.isin(CODE_EXT) & ~low_dir.str.contains(r"takeover_audit|site-packages|\\.vscode|appdata|miniconda|pycharm")]
    rows = []
    pat = re.compile(r"(%s)" % "|".join(map(re.escape, COL_TOKENS)))
    for p, mt in zip(code.path, code.mtime):
        try:
            t = read_text(p)
        except Exception:
            continue
        if not pat.search(t):
            continue
        for i, line in enumerate(t.splitlines()):
            if pat.search(line) and re.search(r"=|agg|rename|groupby|select|as |where|<=|>=|<|>", line):
                rows.append(dict(path=p, mtime=mt, line=i + 1, text=line.strip()[:240]))
    cl = pd.DataFrame(rows)
    out("")
    if len(cl):
        cl.to_csv(OUT_DIR + r"\column_code_lines.csv", index=False, encoding="utf-8-sig")
        cl = cl[~cl.path.str.contains("堡垒机数据筛选")]
        out("[7] 代码中涉及这些列的行=%d (文件%d个；全部见 column_code_lines.csv)。每个关键词挑最早的2行:" % (len(cl), cl.path.nunique()))
        for tok in COL_TOKENS:
            s = cl[cl.text.str.contains(re.escape(tok))].sort_values("mtime").drop_duplicates("text").head(2)
            for _, r in s.iterrows():
                out("  [%s] %s L%d: %s" % (tok[:14], r.mtime[:10], r.line, r.text[:120]))
                out("        %s" % r.path[-70:])
    out("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
