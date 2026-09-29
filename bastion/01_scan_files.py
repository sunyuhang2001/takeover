# -*- coding: utf-8 -*-
# 01_scan_files.py : 全盘文件索引（只读）。结果 file_index.csv 供后续所有步骤复用。
# 用法：python 01_scan_files.py            （默认扫所有本地盘）
#       python 01_scan_files.py D:\ E:\    （只扫指定盘/目录）
import os, sys, re, csv, time, hashlib
from collections import defaultdict

NAME, VERSION = "01_scan_files", "v2"
OUT_DIR = r"D:\takeover_audit\01_scan"

SKIP_DIRS = {  # 目录名（小写）命中即跳过
    "windows", "program files", "program files (x86)", "programdata", "$recycle.bin",
    "system volume information", "recovery", "perflogs", "appdata", "miniconda3", "anaconda3",
    "matlab", "microsoft vs code", "pycharm", "wps", "node_modules", ".git", "site-packages",
    "__pycache__", "takeover_audit", "tslearn-main",
}
VIDEO_EXT = {".avi", ".mp4", ".mkv", ".mov", ".h264", ".h265", ".264", ".flv", ".wmv", ".dav"}
TABLE_EXT = {".xlsx", ".xls", ".xlsm", ".csv"}
ARCH_EXT = {".zip", ".rar", ".7z", ".tar", ".gz"}
DATA_EXT = {".db", ".sqlite", ".sql", ".parquet", ".mat", ".pcd", ".bag", ".pcap", ".npy", ".pkl", ".h5", ".feather"}

RE_EGO = re.compile(r"^ch(\d)_(\d{12})_(\d{12})\.", re.I)  # ch1_240429101716_240429101816.avi
RE_VIN = re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])")
GANTRY_KEYS = ("相机", "摄像机", "一体机", "龙门架")


def selfcheck():
    try:
        t = open(__file__, "rb").read().decode("utf-8", "replace")
    except Exception:
        return "n/a"
    lines = [l.rstrip() for l in t.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return hashlib.md5("\n".join(lines).encode("utf-8")).hexdigest()[:8]


def classify(name, ext):
    low = name.lower()
    if ext in VIDEO_EXT:
        if RE_EGO.match(name):
            return "ego_video"
        if any(k in name for k in GANTRY_KEYS):
            return "gantry_video"
        return "video_unknown"
    if ext == ".json":
        return "participant_json" if "participant" in low else "json_other"
    if ext in TABLE_EXT:
        return "table"
    if ext in ARCH_EXT:
        return "archive"
    if ext in DATA_EXT:
        return "data_other"
    return "other"


def local_roots():
    return [L + ":\\" for L in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(L + ":\\")]


def walk(root, errors):
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except Exception as e:
            errors.append((d, repr(e))); continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.name.lower() not in SKIP_DIRS:
                            stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        st = e.stat()
                        yield d, e.name, st.st_size, st.st_mtime
                except Exception as ex:
                    errors.append((e.path, repr(ex)))


def top_of(path):
    drive, rest = os.path.splitdrive(path)
    parts = [p for p in rest.split("\\") if p]
    return drive + "\\" + (parts[0] if parts else "")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    roots = sys.argv[1:] or local_roots()
    t0 = time.time()
    errors = []
    kinds = defaultdict(lambda: [0, 0, set(), None, None])   # n, bytes, vins, tmin, tmax
    tops = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # top -> kind -> [n, bytes]
    unknown_vid, pjson = [], []
    n = 0
    f = open(os.path.join(OUT_DIR, "file_index.csv"), "w", newline="", encoding="utf-8-sig")
    w = csv.writer(f)
    w.writerow(["dir", "name", "ext", "size_bytes", "mtime", "kind", "vin", "top"])
    for r in roots:
        for d, name, size, mt in walk(r, errors):
            ext = os.path.splitext(name)[1].lower()
            kind = classify(name, ext)
            m = RE_VIN.search((d + "\\" + name).upper())
            vin = m.group(0) if m else ""
            top = top_of(d + "\\")
            mts = time.strftime("%Y-%m-%d %H:%M", time.localtime(mt))
            w.writerow([d, name, ext, size, mts, kind, vin, top])
            k = kinds[kind]
            k[0] += 1; k[1] += size
            if vin:
                k[2].add(vin)
            k[3] = mts if k[3] is None or mts < k[3] else k[3]
            k[4] = mts if k[4] is None or mts > k[4] else k[4]
            tops[top][kind][0] += 1; tops[top][kind][1] += size
            if kind == "video_unknown":
                unknown_vid.append(d + "\\" + name)
            elif kind == "participant_json":
                pjson.append(d + "\\" + name)
            n += 1
            if n % 50000 == 0:
                print("  ... %d files, %.0fs, at %s" % (n, time.time() - t0, d[:80]))
    f.close()
    with open(os.path.join(OUT_DIR, "unknown_videos.txt"), "w", encoding="utf-8") as g:
        g.write("\n".join(unknown_vid))
    with open(os.path.join(OUT_DIR, "participant_json.txt"), "w", encoding="utf-8") as g:
        g.write("\n".join(pjson))
    with open(os.path.join(OUT_DIR, "errors.csv"), "w", newline="", encoding="utf-8-sig") as g:
        csv.writer(g).writerows(errors)

    # ---------- 一屏摘要 ----------
    L = []
    GB = 2 ** 30
    L.append("=== %s %s  check=%s  roots=%s ===" % (NAME, VERSION, selfcheck(), ",".join(roots)))
    L.append("files=%d  total=%.1fGB  errors=%d  elapsed=%.0fs" % (
        n, sum(v[1] for v in kinds.values()) / GB, len(errors), time.time() - t0))
    L.append("%-17s %9s %9s %5s  %-16s  %-16s" % ("kind", "files", "GB", "VINs", "mtime_min", "mtime_max"))
    for kd in sorted(kinds, key=lambda x: -kinds[x][1]):
        v = kinds[kd]
        L.append("%-17s %9d %9.1f %5d  %-16s  %-16s" % (kd, v[0], v[1] / GB, len(v[2]), v[3], v[4]))
    cols = ["ego_video", "gantry_video", "video_unknown", "participant_json", "table"]
    L.append("")
    L.append("top dirs containing data (count per kind, total GB):")
    L.append("%-34s %7s %7s %7s %7s %7s %8s" % ("top", "ego", "gantry", "vid?", "pjson", "table", "GB"))
    rows = []
    for tp, kk in tops.items():
        cnt = [kk[c][0] if c in kk else 0 for c in cols]
        if sum(cnt):
            rows.append((sum(v[1] for v in kk.values()), tp, cnt))
    for gb, tp, cnt in sorted(rows, reverse=True)[:25]:
        L.append("%-34s %7d %7d %7d %7d %7d %8.1f" % ((tp[:34],) + tuple(cnt) + (gb / GB,)))
    L.append("")
    L.append("video_unknown examples (%d, full list in unknown_videos.txt):" % len(unknown_vid))
    for p in unknown_vid[:6]:
        L.append("  " + p[-110:])
    L.append("participant_json examples (%d):" % len(pjson))
    for p in pjson[:4]:
        L.append("  " + p[-110:])
    L.append("=== END %s %s  -> %s ===" % (NAME, VERSION, OUT_DIR))
    s = "\n".join(L)
    print(s)
    with open(os.path.join(OUT_DIR, "summary.txt"), "w", encoding="utf-8") as g:
        g.write(s)


if __name__ == "__main__":
    main()
