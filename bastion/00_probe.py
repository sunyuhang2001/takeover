# -*- coding: utf-8 -*-
# 00_probe.py : 环境探查 + 粘贴通道测试（只读，不改任何原始数据）
# 用法：保存为 D:\takeover_audit\scripts\00_probe.py，然后运行 python 00_probe.py
import os, sys, hashlib, importlib, platform, shutil, time

NAME, VERSION = "00_probe", "v1"
OUT_DIR = r"D:\takeover_audit\00_probe"

KNOWN_PATHS = [
    r"D:\堡垒机数据筛选",
    r"D:\code\data\920汽车城脱离时间整理",
    r"D:\VIDEO", r"D:\video0719", r"D:\videorequest",
    r"D:\RoadsideData", r"D:\video_audit_output",
    r"D:\chenming_backup", r"D:\andy_workspace", r"D:\新建文件夹",
]


def selfcheck():
    """把换行统一成 LF、去掉行尾空白后算 md5 前 8 位，用来确认粘贴完整。"""
    try:
        t = open(__file__, "rb").read().decode("utf-8", "replace")
    except Exception:
        return "n/a"
    lines = [l.rstrip() for l in t.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return hashlib.md5("\n".join(lines).encode("utf-8")).hexdigest()[:8]


try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
os.makedirs(OUT_DIR, exist_ok=True)
_log = open(os.path.join(OUT_DIR, "probe.txt"), "w", encoding="utf-8")


def out(s=""):
    print(s)
    _log.write(s + "\n")


out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))

# 1. 粘贴通道测试：中文是否被改动
zh = "接管数据盘点"
ok = zh == "\u63a5\u7ba1\u6570\u636e\u76d8\u70b9"
out("[paste] chinese_ok=%s  (能跑到这一行说明缩进没被破坏)" % ok)

# 2. Python 和包
out("[python] %s  %s" % (sys.version.split()[0], sys.executable))
out("[os] %s" % platform.platform())
mods = ["pandas", "numpy", "openpyxl", "xlrd", "xlsxwriter", "cv2", "matplotlib", "psutil", "chardet"]
res = []
for m in mods:
    try:
        v = getattr(importlib.import_module(m), "__version__", "ok")
        res.append("%s=%s" % (m, v))
    except Exception:
        res.append("%s=NO" % m)
out("[pkgs] " + "  ".join(res))
out("[tools] ffprobe=%s  ffmpeg=%s" % (bool(shutil.which("ffprobe")), bool(shutil.which("ffmpeg"))))

# 3. 内存
try:
    import ctypes

    class MS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tot", ctypes.c_ulonglong),
                    ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                    ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
    m = MS(); m.l = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    out("[mem] total=%.1fGB  avail=%.1fGB  cpu=%s" % (m.tot / 2**30, m.avail / 2**30, os.cpu_count()))
except Exception as e:
    out("[mem] n/a (%s)" % e)

# 4. 各盘容量
for L in "CDEFGHIJKLMNOPQRSTUVWXYZ":
    p = L + ":\\"
    if os.path.exists(p):
        try:
            u = shutil.disk_usage(p)
            out("[disk] %s total=%.0fGB used=%.0fGB free=%.0fGB" % (L, u.total / 2**30, u.used / 2**30, u.free / 2**30))
        except Exception as e:
            out("[disk] %s err %s" % (L, e))

# 5. 已知目录是否存在
out("[paths] " + "  ".join("%s=%s" % (os.path.basename(p) or p, "Y" if os.path.exists(p) else "N") for p in KNOWN_PATHS))

# 6. D 盘一级目录
out("[D:\\ top level]")
try:
    ents = sorted(os.scandir("D:\\"), key=lambda e: e.name.lower())
    row = []
    for e in ents:
        try:
            tag = "/" if e.is_dir() else " %.0fMB" % (e.stat().st_size / 2**20)
        except Exception:
            tag = "?"
        row.append(e.name + tag)
        if len(row) == 4:
            out("  " + " | ".join(row)); row = []
    if row:
        out("  " + " | ".join(row))
except Exception as e:
    out("  err %s" % e)

out("=== END %s %s (结果也写到了 %s\\probe.txt) ===" % (NAME, VERSION, OUT_DIR))
_log.close()
