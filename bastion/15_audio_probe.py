# -*- coding: utf-8 -*-
# 15_audio_probe.py v1 : 自车视频音轨探查 + 接管提示音检测（只读，不需要喇叭）
#   [1] 全部 ch1/ch2/ch3 视频: 音频编码格式统计(读文件头 strf/WAVEFORMATEX)
#   [2] 全盘找 ffmpeg.exe(压缩音频 MP3/AAC 需要它解码)
#   [3] 抽样事件(默认 6 个 0920 事件, 优先座舱 ch2): 解码音频 -> 频谱 -> 检测“嘀”声(窄带、稳定频率)
#       输出每段的提示音起止/频率/与接管时刻的相对时间, 并画时频图 PNG(事件时刻画竖线)
#   解码: PCM / A-law / μ-law / IMA-ADPCM 用纯 Python; 其他格式有 ffmpeg 才解
# 用法: python 15_audio_probe.py [抽样数]
import os, sys, re, struct, hashlib, time, subprocess
import numpy as np
import pandas as pd

NAME, VERSION = "15_audio_probe", "v1"
BASE = r"D:\takeover_audit"
IN12 = BASE + r"\12_verify"
OUT_DIR = BASE + r"\15_audio"
ROOTS = ["C:\\", "D:\\"]
SKIP = {"windows", "$recycle.bin", "system volume information", "node_modules", ".git", "takeover_audit"}
RE_EGO = re.compile(r"ch([123])_(\d{12})_(\d{12})", re.I)
FMT = {1: "PCM", 2: "MS-ADPCM", 3: "IEEE-float", 6: "A-law", 7: "mu-law", 0x11: "IMA-ADPCM", 0x31: "GSM610",
       0x45: "G726", 0x55: "MP3", 0xFF: "AAC", 0x1610: "AAC", 0x2000: "AC3"}
BAND = (300, 6000)       # 提示音搜索频段 Hz
WIN = 0.05               # 50 ms 窗


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


# ---------------- AVI 解析 ----------------
def avi_audio_info(path, head_only=True):
    """返回 dict(tag, fmt, ch, sr, bits, block, stream) ; head_only=False 时额外返回音频字节 data"""
    with open(path, "rb") as f:
        buf = f.read(256 * 1024) if head_only else f.read()
    if buf[:4] != b"RIFF" or buf[8:12] != b"AVI ":
        return dict(fmt="非AVI", tag=-1)
    info, sidx, pos = None, -1, 12
    # 遍历 strh/strf
    for m in re.finditer(b"strh", buf[:256 * 1024]):
        sidx += 1
        p = m.start()
        if buf[p + 8:p + 12] == b"auds":
            q = buf.find(b"strf", p)
            if q < 0:
                continue
            tag, ch, sr, avg, block, bits = struct.unpack("<HHIIHH", buf[q + 8:q + 24])
            info = dict(tag=tag, fmt=FMT.get(tag, "0x%X" % tag), ch=ch, sr=sr, bits=bits, block=block, stream=sidx)
            if tag == 0x11 and q + 26 <= len(buf):
                info["spb"] = struct.unpack("<H", buf[q + 26:q + 28])[0] if struct.unpack("<H", buf[q + 24:q + 26])[0] >= 2 else 0
            break
    if info is None:
        return dict(fmt="无音轨", tag=0)
    if head_only:
        return info
    cid = b"%02dwb" % info["stream"]
    mv = buf.find(b"movi")
    chunks, p = [], mv + 4
    while 0 <= p < len(buf) - 8:
        fid, sz = buf[p:p + 4], struct.unpack("<I", buf[p + 4:p + 8])[0]
        if fid == b"LIST":
            p += 12; continue
        if fid == cid:
            chunks.append(buf[p + 8:p + 8 + sz])
        if fid == b"idx1":
            break
        p += 8 + sz + (sz & 1)
    info["data"] = b"".join(chunks)
    return info


def ulaw(b):
    u = ~np.frombuffer(b, np.uint8).astype(np.int32) & 0xFF
    t = ((u & 0x0F) << 3) + 0x84
    t <<= (u & 0x70) >> 4
    return np.where(u & 0x80, 0x84 - t, t - 0x84).astype(np.float32) / 32768


def alaw(b):
    a = np.frombuffer(b, np.uint8).astype(np.int32) ^ 0x55
    t = (a & 0x0F) << 4
    seg = (a & 0x70) >> 4
    t = np.where(seg == 0, t + 8, np.where(seg == 1, t + 0x108, (t + 0x108) << (seg - 1)))
    return np.where(a & 0x80, t, -t).astype(np.float32) / 32768


IMA_STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
            130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060,
            1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484,
            7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
IMA_IDX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]


def ima_adpcm(b, block, nch):
    """IMA ADPCM(WAV 格式)，只取第一个声道"""
    outs = []
    for s in range(0, len(b) - 4 * nch + 1, block):
        blk = b[s:s + block]
        if len(blk) < 4 * nch:
            break
        pred, idx = struct.unpack("<hB", blk[0:3]); idx = min(max(idx, 0), 88)
        res = [pred]
        data = blk[4 * nch:]
        # 每声道每 4 字节交错；取第 0 声道
        nib = []
        for g in range(0, len(data), 4 * nch):
            for byte in data[g:g + 4]:
                nib += [byte & 0x0F, byte >> 4]
        for n in nib:
            step = IMA_STEP[idx]
            d = step >> 3
            if n & 4: d += step
            if n & 2: d += step >> 1
            if n & 1: d += step >> 2
            pred = pred - d if n & 8 else pred + d
            pred = max(-32768, min(32767, pred))
            idx = min(max(idx + IMA_IDX[n], 0), 88)
            res.append(pred)
        outs.append(np.array(res, np.float32))
    return (np.concatenate(outs) / 32768) if outs else np.zeros(0, np.float32)


def decode(path, ffmpeg=None):
    """返回 (采样 float32 单声道, 采样率, 说明)"""
    if path.lower().endswith(".avi"):
        inf = avi_audio_info(path, head_only=False)
        tag = inf.get("tag", -1)
        if tag in (1, 3, 6, 7, 0x11) and inf.get("data"):
            d, ch, sr = inf["data"], max(inf["ch"], 1), inf["sr"]
            if tag == 1:
                x = (np.frombuffer(d[:len(d) // 2 * 2], "<i2").astype(np.float32) / 32768) if inf["bits"] == 16 else \
                    (np.frombuffer(d, np.uint8).astype(np.float32) - 128) / 128
            elif tag == 3:
                x = np.frombuffer(d[:len(d) // 4 * 4], "<f4")
            elif tag == 6:
                x = alaw(d)
            elif tag == 7:
                x = ulaw(d)
            else:
                x = ima_adpcm(d, inf["block"], ch); ch = 1
            if ch > 1:
                x = x[:len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
            return x, sr, inf["fmt"]
        fmt = inf.get("fmt", "?")
    else:
        fmt = "mp4/其他"
    if ffmpeg:
        try:
            r = subprocess.run([ffmpeg, "-v", "quiet", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                               capture_output=True, timeout=120)
            if r.stdout:
                return np.frombuffer(r.stdout, "<i2").astype(np.float32) / 32768, 16000, fmt + "(ffmpeg)"
        except Exception:
            pass
    return None, 0, fmt + "(无法解码)"


# ---------------- 提示音检测 ----------------
def spectro(x, sr):
    n = max(256, int(sr * WIN)); hop = n // 2
    if len(x) < n:
        return None, None, None
    fr = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    S = np.abs(np.fft.rfft(fr, axis=1)) + 1e-9
    f = np.fft.rfftfreq(n, 1 / sr)
    t = np.arange(S.shape[0]) * hop / sr + n / 2 / sr
    return t, f, 20 * np.log10(S)


def beeps(t, f, S):
    """窄带稳定频率: 频段内峰值比频段中位数高 >=18dB, 连续 >=3 帧(≈75ms) 且频率漂移 <=60Hz"""
    band = (f >= BAND[0]) & (f <= min(BAND[1], f[-1]))
    B = S[:, band]; fb = f[band]
    pk = B.argmax(axis=1); prom = B.max(axis=1) - np.median(B, axis=1)
    on = prom >= 18
    ev, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j + 1 < len(on) and on[j + 1] and abs(fb[pk[j + 1]] - fb[pk[i]]) <= 60:
                j += 1
            if j - i + 1 >= 3:
                ev.append((t[i], t[j], float(np.median(fb[pk[i:j + 1]])), float(prom[i:j + 1].mean())))
            i = j + 1
        else:
            i += 1
    return ev


def plot(t, f, S, ev, t_evt, title, png):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        fig, ax = plt.subplots(figsize=(14, 4.5), dpi=100)
        keep = f <= 8000
        ax.pcolormesh(t, f[keep], S[:, keep].T, shading="auto", cmap="magma", vmin=np.percentile(S, 20), vmax=np.percentile(S, 99.5))
        for a, b, fq, _ in ev:
            ax.plot([a, b], [fq, fq], color="cyan", lw=2)
        if t_evt is not None:
            ax.axvline(t_evt, color="lime", lw=2, ls="--", label="接管时刻")
            ax.legend(loc="upper right")
        ax.set_xlabel("片段内时间 (s)"); ax.set_ylabel("频率 (Hz)"); ax.set_title(title)
        fig.tight_layout(); fig.savefig(png); plt.close(fig)
        return True
    except Exception as e:
        out("   画图失败 %r" % e)
        return False


def walk_find(roots, names):
    hit = []
    for r in roots:
        stack = [r]
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
                        elif e.name.lower().startswith(names) and e.name.lower().endswith(".exe"):
                            hit.append(e.path)
                    except Exception:
                        pass
    return hit


def main():
    t0 = time.time()
    nsample = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 6
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))
    U = pd.read_csv(IN12 + r"\事件资产表.csv", dtype={"vin": str}, encoding="utf-8-sig")

    # [1] 编码格式统计
    out("")
    out("[1] 视频音频编码(读文件头):")
    for c in "123":
        ps = sorted(set(p for s in U["ch%s_原始路径" % c].fillna("") for p in str(s).split(";") if p and os.path.exists(p)))
        cnt = {}
        det = {}
        for p in ps:
            inf = avi_audio_info(p) if p.lower().endswith(".avi") else dict(fmt="mp4/其他")
            k = inf["fmt"]; cnt[k] = cnt.get(k, 0) + 1
            if "sr" in inf:
                det.setdefault(k, set()).add("%dHz/%dch/%dbit" % (inf["sr"], inf["ch"], inf["bits"]))
        out("  ch%s 文件=%d : %s" % (c, len(ps), "  ".join("%s:%d%s" % (k, v, ("(" + ",".join(sorted(det[k]))[:60] + ")") if k in det else "")
                                                   for k, v in sorted(cnt.items(), key=lambda x: -x[1]))))

    # [2] ffmpeg
    ff = walk_find(ROOTS, ("ffmpeg",))
    out("")
    out("[2] 找到 ffmpeg: %d 个 %s" % (len(ff), " | ".join(ff[:4])))
    ffmpeg = next((p for p in ff if os.path.basename(p).lower().startswith("ffmpeg")), None)

    # [3] 抽样检测
    out("")
    out("[3] 抽样提示音检测(频段 %d-%dHz, 窄带峰值高出中位 >=18dB 且持续 >=75ms 记为一声)" % BAND)
    U["事件时间"] = pd.to_datetime(U["事件时间"])
    cand = U[(U["ch2_可读"].fillna(0) > 0) & (U["在0920"].astype(str).str.lower() == "true")]
    if len(cand) < nsample:
        cand = pd.concat([cand, U[U["ch2_可读"].fillna(0) > 0]]).drop_duplicates("event_key")
    cand = cand.sort_values("事件时间").iloc[np.linspace(0, len(cand) - 1, min(nsample, len(cand))).astype(int)] if len(cand) else cand
    rows = []
    for _, r in cand.iterrows():
        for c in ("2", "1"):
            clips = [p for p in str(r.get("ch%s_原始路径" % c, "")).split(";") if p and os.path.exists(p)]
            if not clips:
                continue
            best = None
            for p in clips:     # 选覆盖接管时刻的片段
                m = RE_EGO.search(os.path.basename(p))
                if not m:
                    continue
                s = pd.to_datetime(m.group(2), format="%y%m%d%H%M%S", errors="coerce")
                e = pd.to_datetime(m.group(3), format="%y%m%d%H%M%S", errors="coerce")
                if pd.notna(s) and s - pd.Timedelta(seconds=5) <= r["事件时间"] <= e + pd.Timedelta(seconds=5):
                    best = (p, s); break
                best = best or (p, s)
            if not best:
                continue
            p, s = best
            x, sr, how = decode(p, ffmpeg)
            key = "%s_ch%s" % (r["event_key"][-15:], c)
            if x is None or not len(x):
                rows.append(dict(事件=key, 格式=how, 时长s=0, 提示音数=-1)); out("  %s  %s" % (key, how)); continue
            t, f, S = spectro(x, sr)
            if t is None:
                continue
            ev = beeps(t, f, S)
            te = (r["事件时间"] - s).total_seconds() if pd.notna(s) else None
            rel = [a - te for a, *_ in ev] if te is not None else []
            before = [v for v in rel if -30 <= v <= 1]
            freqs = sorted(set(int(round(fq / 50) * 50) for *_, fq, _ in ev))
            rows.append(dict(事件=key, 格式=how, 采样率=sr, 时长s=round(len(x) / sr, 1), 提示音数=len(ev),
                             接管前30s内=len(before), 首声相对接管s=round(min(before), 1) if before else None,
                             频率Hz=",".join(map(str, freqs[:6])), 平均单声s=round(np.mean([b - a for a, b, *_ in ev]), 2) if ev else None))
            png = OUT_DIR + "\\spec_%s.png" % key
            plot(t, f, S, ev, te, "%s  %s  %s  提示音=%d" % (key, r.get("类别", "")[:1], how, len(ev)), png)
            out("  %s  %-10s %5.1fs  提示音=%3d  接管前30s内=%2d  首声相对接管=%s  频率=%s" % (
                key, how, len(x) / sr, len(ev), len(before), rows[-1]["首声相对接管s"], rows[-1]["频率Hz"]))
            desc = str(r.get("描述", ""))
            if desc and desc != "nan":
                out("      0920描述: %s" % desc[:60])
            break
    pd.DataFrame(rows).to_csv(OUT_DIR + r"\beeps.csv", index=False, encoding="utf-8-sig")
    out("")
    out("  时频图: %s\\spec_*.png (横线=检测到的提示音, 绿色虚线=接管时刻)" % OUT_DIR)
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))
    out("=== END %s %s  用时%.0fs ===" % (NAME, VERSION, time.time() - t0))


if __name__ == "__main__":
    main()
