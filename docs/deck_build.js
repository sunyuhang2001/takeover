// 接管数据现状汇报 —— 按 PPT制作/pptx/SKILL.md 规范（白底、单主色 1F3864、微软雅黑、结论框、三段式版式）
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.title = "接管（脱离）数据现状汇报";

const P = "1F3864", TINT = "DDE1E8", TXT = "333333", GRAY = "808080", EMP = "8B0000", WHITE = "FFFFFF";
const F = "Microsoft YaHei";
const TOTAL = 14;
let page = 0;

function header(s, sec, title) {
  s.background = { color: WHITE };
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 0.36, w: 0.52, h: 0.52, fill: { color: P }, line: { color: P } });
  s.addText(sec, { x: 0.5, y: 0.36, w: 0.52, h: 0.52, fontFace: F, fontSize: 16, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
  s.addText(title, { x: 1.14, y: 0.3, w: 8.4, h: 0.64, fontFace: F, fontSize: 26, bold: true, color: P, valign: "middle", margin: 0 });
}
function footer(s) {
  page += 1;
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.3, w: 10, h: 0.325, fill: { color: TINT }, line: { color: TINT } });
  s.addText("接管（脱离）数据现状汇报  ·  口径：12_verify_all v5（2026-09-30）", { x: 0.5, y: 5.3, w: 7.5, h: 0.325, fontFace: F, fontSize: 10, color: GRAY, valign: "middle", margin: 0 });
  s.addText(`${page} / ${TOTAL}`, { x: 8.5, y: 5.3, w: 1.0, h: 0.325, fontFace: F, fontSize: 10, color: P, bold: true, align: "right", valign: "middle", margin: 0 });
}
function concl(s, text, y, h = 0.5, x = 0.5, w = 9.0) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: TINT }, line: { color: P, width: 1 } });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.08, h, fill: { color: P }, line: { color: P } });
  s.addText(text, { x: x + 0.2, y, w: w - 0.3, h, fontFace: F, fontSize: 14, color: TXT, valign: "middle", margin: 0 });
}
// 表格：首行主色表头，隔行浅底纹
function table(s, rows, opt) {
  const fs = opt.fontSize || 12;
  const data = rows.map((r, i) => r.map((c) => {
    const cell = typeof c === "object" ? c : { text: String(c) };
    const o = Object.assign({ fontFace: F, fontSize: fs, color: TXT, valign: "middle" }, cell.options || {});
    if (i === 0) Object.assign(o, { bold: true, color: WHITE, fill: { color: P } });
    else if (i % 2 === 0) o.fill = o.fill || { color: "F2F4F7" };
    return { text: cell.text, options: o };
  }));
  s.addTable(data, Object.assign({ border: { type: "solid", pt: 0.5, color: "C8CED8" }, margin: [2, 5, 2, 5] }, opt, { fontSize: undefined }));
}
const B = (t) => ({ text: t, options: { bold: true, color: EMP } });
// bullets helper for rich runs
function richBullets(s, items, box, fs) {
  const runs = [];
  items.forEach((it, i) => {
    const parts = Array.isArray(it) ? it : [{ text: it }];
    parts.forEach((p, j) => {
      const o = Object.assign({}, p.options || {});
      if (j === 0) o.bullet = true;
      if (j === parts.length - 1 && i < items.length - 1) { o.breakLine = true; o.paraSpaceAfter = 6; }
      runs.push({ text: p.text, options: o });
    });
  });
  s.addText(runs, Object.assign({ fontFace: F, fontSize: fs || 14, color: TXT, valign: "top", margin: 2 }, box));
}
// ---------- 1 封面 ----------
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.35, h: 5.625, fill: { color: P }, line: { color: P } });
  s.addText("接管（脱离）数据现状汇报", { x: 0.9, y: 1.35, w: 8.5, h: 0.9, fontFace: F, fontSize: 40, bold: true, color: P, margin: 0 });
  s.addText("堡垒机数据盘点：自车视频 · 自车轨迹 · 路侧数据 · 0920 台账", { x: 0.9, y: 2.3, w: 8.5, h: 0.5, fontFace: F, fontSize: 18, color: TXT, margin: 0 });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.9, y: 3.05, w: 8.2, h: 0.95, fill: { color: TINT }, line: { color: TINT } });
  s.addText([
    { text: "数据范围：堡垒机 C:\\ 与 D:\\ 全部数据（取数渠道已失效，堡垒机即全部）", options: { breakLine: true } },
    { text: "统计口径：12_verify_all v5 + 13_diag_notraj；只报汇总数字，逐条明细见事件资产表" },
  ], { x: 1.1, y: 3.05, w: 7.9, h: 0.95, fontFace: F, fontSize: 13, color: TXT, valign: "middle", margin: 0, paraSpaceAfter: 4 });
  s.addText("汇报人：[待补充]        2026-09-30", { x: 0.9, y: 4.5, w: 8, h: 0.4, fontFace: F, fontSize: 14, color: GRAY, margin: 0 });
  page += 1;
}

// ---------- 2 目录 ----------
{
  const s = pres.addSlide(); header(s, "目", "汇报目录");
  const items = [
    ["0", "结论摘要", "关键数字与可复现事件"],
    ["1", "视频匹配", "片段、通道；与轨迹、0920、前人 35 个的关系"],
    ["2", "分类统计", "A–H/X 分类：2025 年前主表 + 2025 年单列"],
    ["3", "数据地址与匹配", "各类原始地址；按 VIN + 时间对齐的方法"],
    ["4", "数据量与覆盖", "数据量、字段、时空覆盖"],
    ["5", "数据质量", "3 项 FAIL 与使用注意"],
    ["6", "数据保存位置", "原始数据、处理产出与留存方式"],
  ];
  items.forEach(([n, t, d], i) => {
    const col = i < 4 ? 0 : 1, row = i < 4 ? i : i - 4;
    const x = 0.5 + col * 4.6, y = 1.2 + row * 0.95;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.6, h: 0.72, fill: { color: P }, line: { color: P } });
    s.addText(n, { x, y, w: 0.6, h: 0.72, fontFace: F, fontSize: 22, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
    s.addShape(pres.shapes.RECTANGLE, { x: x + 0.6, y, w: 3.8, h: 0.72, fill: { color: "F2F4F7" }, line: { color: "F2F4F7" } });
    s.addText([{ text: t, options: { bold: true, color: P, fontSize: 16, breakLine: true } }, { text: d, options: { fontSize: 11, color: TXT } }],
      { x: x + 0.75, y, w: 3.6, h: 0.72, fontFace: F, valign: "middle", margin: 0 });
  });
  footer(s);
}

// ---------- 3 结论摘要 ----------
{
  const s = pres.addSlide(); header(s, "0", "结论：可复现事件 335 个，2025 年路侧最完整");
  const cards = [
    ["477", "视频事件", "68 辆车，2023-12 起"],
    ["148", "ch1 + 逐秒轨迹", "A 39 + B 109"],
    ["22", "轨迹 + 龙门架", "E 类，逐条核对通过"],
    ["29", "2025 年接管", "15 个有 participant"],
  ];
  cards.forEach(([n, t, d], i) => {
    const x = 0.5 + i * 2.28;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.15, w: 2.1, h: 1.55, fill: { color: WHITE }, line: { color: P, width: 1 } });
    s.addText(n, { x, y: 1.2, w: 2.1, h: 0.65, fontFace: F, fontSize: 32, bold: true, color: P, align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: x + 0.05, y: 1.85, w: 2.0, h: 0.35, fontFace: F, fontSize: 13, bold: true, color: TXT, align: "center", margin: 0 });
    s.addText(d, { x: x + 0.05, y: 2.2, w: 2.0, h: 0.45, fontFace: F, fontSize: 10.5, color: GRAY, align: "center", valign: "top", margin: 0 });
  });
  richBullets(s, [
    [{ text: "视频：" , options: {bold: true}}, { text: "有 ch1 的 313 个；在 0920 里 44 个，前人 35 个已完整复现" }],
    [{ text: "轨迹：", options: {bold: true} }, { text: "2634 个事件中 2310 个有轨迹；C 类 165 个只有稀疏定位" }],
    [{ text: "路侧：", options: {bold: true} }, { text: "2024 年主要靠龙门架（同车 24 个）；2025 年 participant 时段多" }],
  ], { x: 0.5, y: 2.95, w: 9.0, h: 1.5 }, 14);
  concl(s, "可复现 335 个 = 视频 ch1 313 + 轨迹 + 路侧 22；2025 年另有 15 个", 4.6, 0.55);
  footer(s);
}

// ---------- 4 视频片段与通道 ----------
{
  const s = pres.addSlide(); header(s, "1", "视频：1117 个片段，前视 ch1 全部可读");
  s.addText("按通道的片段（1424 个文件）", { x: 0.5, y: 1.05, w: 5.4, h: 0.3, fontFace: F, fontSize: 13, bold: true, color: P, margin: 0 });
  table(s, [
    ["通道", "片段", "可读", "可读时长", "段数 60/120/600s"],
    ["ch1 前视", "318", "318", "6.2 h", "198 / 119 / 1"],
    ["ch2 座舱", "343", "337", "6.5 h", "225 / 117 / 1"],
    ["ch3 踏板", "456", "444", "8.3 h", "339 / 116 / 1"],
  ], { x: 0.5, y: 1.4, w: 5.4, colW: [1.05, 0.65, 0.65, 0.95, 2.1], fontSize: 12, rowH: 0.36 });
  s.addText("477 个事件按可读通道", { x: 6.2, y: 1.05, w: 3.3, h: 0.3, fontFace: F, fontSize: 13, bold: true, color: P, margin: 0 });
  table(s, [
    ["可读通道", "事件数"],
    [{ text: "ch1+ch2+ch3", options: { bold: true } }, { text: "283", options: { bold: true, color: EMP } }],
    ["仅 ch3", "123"], ["ch2+ch3", "24"], ["ch1+ch2", "19"], ["ch1+ch3", "6"], ["仅 ch2", "6"], ["仅 ch1", "5"], ["全部不可读", "11"],
  ], { x: 6.2, y: 1.4, w: 3.3, colW: [2.1, 1.2], fontSize: 12, rowH: 0.3 });
  richBullets(s, [
    "视频是按“关键脱离”清单（KShape 聚类 + 加速度阈值）调取的，时间 2023-12-01 ~ 2024-07-23，涉及 68 辆车",
    "VIN 取自路径；9 个文件路径中没有 VIN，无法入表；105 个是处理产物里的拷贝",
    "有前视 ch1 的事件共 313 个（含三通道 283 个）",
  ], { x: 0.5, y: 3.0, w: 5.4, h: 1.55 }, 12);
  concl(s, "前视 ch1 是复现的必要条件：313 个事件有 ch1，153 个只有座舱/踏板视频", 4.65, 0.5);
  footer(s);
}

// ---------- 5 视频与轨迹 / 0920 / 前人 35 ----------
{
  const s = pres.addSlide(); header(s, "1", "视频：148 个有逐秒轨迹，44 个在 0920 里");
  // 层级框
  const box = (x, y, w, h, t, n, strong) => {
    s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: strong ? P : WHITE }, line: { color: P, width: 1 } });
    s.addText([{ text: n, options: { bold: true, fontSize: 18, color: strong ? WHITE : P, breakLine: true } }, { text: t, options: { fontSize: 10.5, color: strong ? WHITE : TXT } }],
      { x, y, w, h, fontFace: F, align: "center", valign: "middle", margin: 2 });
  };
  box(0.5, 1.15, 1.9, 0.9, "视频事件", "477", true);
  box(2.9, 1.15, 1.9, 0.9, "有 ch1", "313");
  box(2.9, 2.25, 1.9, 0.9, "只有 ch2/ch3（D）", "153");
  box(2.9, 3.35, 1.9, 0.9, "全部不可读（X）", "11");
  box(5.3, 1.15, 2.0, 0.9, "ch1+轨迹+0920 原因（A）", "39");
  box(5.3, 2.25, 2.0, 0.9, "ch1+轨迹，无原因（B）", "109");
  box(5.3, 3.35, 2.0, 0.9, "ch1，无连续轨迹（C）", "165");
  [[2.4, 1.6, 2.9, 1.6], [2.4, 1.6, 2.9, 2.7], [2.4, 1.6, 2.9, 3.8], [4.8, 1.6, 5.3, 1.6], [4.8, 1.6, 5.3, 2.7], [4.8, 1.6, 5.3, 3.8]].forEach(([x1, y1, x2, y2]) => {
    s.addShape(pres.shapes.LINE, { x: x1, y: Math.min(y1, y2), w: x2 - x1, h: Math.abs(y2 - y1), line: { color: GRAY, width: 1 }, flipV: false });
  });
  // 右侧：0920 与前人
  s.addShape(pres.shapes.RECTANGLE, { x: 7.6, y: 1.15, w: 1.9, h: 3.1, fill: { color: TINT }, line: { color: P, width: 1 } });
  s.addText([
    { text: "在 0920 里：44", options: { bold: true, color: P, fontSize: 14, breakLine: true } },
    { text: "三通道 35", options: { bold: true, color: EMP, breakLine: true } },
    { text: "ch1+ch2 3", options: { breakLine: true } },
    { text: "仅 ch3 4", options: { breakLine: true } },
    { text: "其他组合 2", options: { breakLine: true } },
    { text: " ", options: { breakLine: true } },
    { text: "前人 35 个 = 0920 里三通道齐全的部分；17 辆车、105 个 avi，与前人输出目录一致" },
  ], { x: 7.7, y: 1.2, w: 1.75, h: 3.0, fontFace: F, fontSize: 11, color: TXT, valign: "top", margin: 2, paraSpaceAfter: 3 });
  s.addText("C 类诊断：318 个在事件 ±30 s 内只有约 1 个定位点（采样中位约 69 s，来自 all_events_1828589*.csv、add_type.csv）；±10 min 内几乎找不到 drive_mode 1→0 跳变 → 不是时间没对齐，是本来就没有逐秒数据",
    { x: 0.5, y: 4.3, w: 9.0, h: 0.42, fontFace: F, fontSize: 10.5, color: GRAY, margin: 0, valign: "middle" });
  concl(s, "视频事件与 0920 是两份不同的清单：477 个里只有 44 个在 0920，属正常，不是漏数", 4.75, 0.45);
  footer(s);
}

// ---------- 6 主表分类 ----------
{
  const s = pres.addSlide(); header(s, "2", "分类：2634 个事件，可复现 335 个");
  table(s, [
    ["类别", "数量", "三通道", "表格轨迹", "NPY", "路侧", "时间", "能否复现"],
    [{ text: "A ch1+轨迹+原因", options: { bold: true } }, B("39"), "35", "39", "0", "1", "2024-04~07", "视频+轨迹+原因"],
    [{ text: "B ch1+轨迹", options: { bold: true } }, B("109"), "103", "24", "101", "2", "2023-12~2024-06", "视频+轨迹"],
    [{ text: "C ch1，无连续轨迹", options: { bold: true } }, B("165"), "145", "0", "0", "0", "2023-12~2024-07", "只能靠视频"],
    ["D 只有 ch2/ch3", "153", "–", "5", "1", "0", "2023-12~2024-07", "看不到前方"],
    ["X 视频不可读", "11", "–", "0", "0", "0", "2024-05", "不可用"],
    [{ text: "E 轨迹+路侧", options: { bold: true } }, B("22"), "–", "22", "0", "22", "2024-05~08", "轨迹+龙门架"],
    ["F 只有自车轨迹", "2134", "–", "1876", "275", "0", "2023-12~2024-09", "缺周边信息"],
    ["G 只有 0920", "0", "–", "–", "–", "–", "–", "0920 均有轨迹"],
    ["H 无连续轨迹", "1", "–", "0", "0", "1", "2024-04-20", "只有龙门架"],
  ], { x: 0.5, y: 1.1, w: 9.0, colW: [2.0, 0.65, 0.75, 0.9, 0.6, 0.6, 1.75, 1.75], fontSize: 11, rowH: 0.29 });
  s.addText("轨迹：±30 s 内连续覆盖 ≥ 20 s（间隔 ≤ 5 s 才累计）或 NPY ≥ 20 帧；路侧：同车龙门架案例，或 ≤ 500 m 的 participant",
    { x: 0.5, y: 4.18, w: 9.0, h: 0.42, fontFace: F, fontSize: 10, color: GRAY, margin: 0, valign: "middle" });
  concl(s, "来源：仅 0920 1881 · 仅视频 433 · NPY 关键脱离 275 · 视频+0920 44 · 龙门架 1", 4.68, 0.5);
  footer(s);
}

// ---------- 7 E 类核对 + 2025 ----------
{
  const s = pres.addSlide(); header(s, "2", "E 类 22 条核对通过；2025 年单列 29 个");
  s.addText("E 类（无视频，轨迹 + 路侧）逐条核对", { x: 0.5, y: 1.05, w: 4.3, h: 0.3, fontFace: F, fontSize: 13, bold: true, color: P, margin: 0 });
  richBullets(s, [
    [{ text: "22 条全部来自 0920", options: { bold: true } }, { text: "，都有人工接管原因描述" }],
    [{ text: "轨迹：" }, { text: "均为 61 s 逐秒数据", options: { bold: true } }, { text: "，无需时区偏移；drive_mode 1→0 与事件时间相差 0～2 s" }],
    [{ text: "龙门架：" }, { text: "案例目录 VIN 一致，案例时间差 0 s", options: { bold: true } }],
    "涉及 15 个路口：曹安公路、博园路、嘉松北路、安虹路、新源路一带",
    "时间 2024-05-11 ~ 2024-08-23",
  ], { x: 0.5, y: 1.4, w: 4.3, h: 2.9 }, 12);
  s.addText("2025 年（单独统计，同样的分类）", { x: 5.2, y: 1.05, w: 4.3, h: 0.3, fontFace: F, fontSize: 13, bold: true, color: P, margin: 0 });
  table(s, [
    ["类别", "数量", "说明"],
    [{ text: "E 轨迹 + 路侧", options: { bold: true } }, B("15"), "participant 覆盖，2025-03-20 ~ 05-22"],
    ["F 只有自车轨迹", "12", "2025-03-14 ~ 05-24"],
    ["H 无连续轨迹", "2", "轨迹不足 20 s，1 个有路侧"],
  ], { x: 5.2, y: 1.4, w: 4.3, colW: [1.3, 0.6, 2.4], fontSize: 11, rowH: 0.36 });
  richBullets(s, [
    "事件来源：2025 年全部轨迹中的 drive_mode 1→0（同车 60 s 内合并）",
    "轨迹 47,149 点、67 辆车、1290 个文件（运行安全评价 case 为主）",
    "路侧时段内、离设备 ≤ 300 m：53 辆车、16 天，期间接管 17 次（8 辆车）",
    "2025 年无视频、无 0920 原因、无龙门架同车案例",
  ], { x: 5.2, y: 2.95, w: 4.3, h: 1.6 }, 11);
  concl(s, "2025 年路侧设备固定、时段多，是“路侧 + 自车轨迹”场景复现的最佳数据", 4.65, 0.5);
  footer(s);
}

// ---------- 8 数据地址 ----------
{
  const s = pres.addSlide(); header(s, "3", "地址：各类数据取原始位置，不用处理产物");
  table(s, [
    ["类别", "视频（目录：事件数）", "轨迹（原始文件：事件数）"],
    ["A", "D:\\video0719:30 · D:\\video2:7 · D:\\VIDEO:1 · D:\\video5:1", "…\\920汽车城脱离时间整理\\all927.xlsx:38 · dis_joined1.xlsx:1"],
    ["B", "D:\\video5:42 · D:\\VIDEO:27 · D:\\video2:22 · D:\\video0719:15", "local_vehicle_info_*.csv；NPY：D:\\code\\critical_X.npy、…\\critical\\critical_X2.npy:101"],
    ["C", "D:\\video2:80 · D:\\video0719:34 · D:\\video5:18 · D:\\VIDEO:16", "仅稀疏定位（andy_workspace\\projects\\project\\all_events_*.csv）"],
    ["D", "D:\\video4:53 · D:\\video2:48 · D:\\video3:19 · D:\\VIDEO:13", "all927.xlsx:5 · NPY:1"],
    ["E", "–（龙门架：<序号>-<VIN>-<日期 时间> 案例目录）", "all927.xlsx:17 · D:\\chenming_backup\\DOM\\veh_origin\\case_17_vehicle.csv:1"],
    ["F", "–", "all927.xlsx:1826 · dis_joined1.xlsx:31 · NPY:275"],
    ["X", "D:\\video2:11", "–"],
    ["2025", "–（participant：D:\\250408提供最新、D:\\code\\data\\250408、…\\交通参与者数据拉取0506/0528）", "D:\\运行安全评价\\veh_origin\\Case_*_vehicle_origin.csv、con_res\\case_*_vehicle_end.csv"],
  ], { x: 0.5, y: 1.1, w: 9.0, colW: [0.6, 4.1, 4.3], fontSize: 9.5, rowH: 0.34 });
  concl(s, "多拷贝按“原始目录 > 桌面拷贝 > 处理产物”取；处理产物不作地址", 4.6, 0.55);
  footer(s);
}

// ---------- 9 匹配方法 ----------
{
  const s = pres.addSlide(); header(s, "3", "匹配：以 VIN + 北京时间为唯一索引对齐");
  const steps = [
    ["索引", "event_key = VIN_YYYYMMDD_HHMMSS（北京时间）；同车 ≤ 60 s 为同一事件"],
    ["视频", "VIN 取自路径；时间取文件名 ch{1|2|3}_{起}_{止}，事件时间取片段中点"],
    ["0920", "VIN + disengage_time，误差 ≤ 60 s；disengage_time 即 drive_mode 1→0 时刻"],
    ["表格轨迹", "VIN + 事件 ±30 s；每个文件自动选 0 / +8h / −8h（all927 等为 UTC）；同名同大小只读原始"],
    ["NPY", "labels 的 VIN + 时间 ≤ 60 s；行号对应同目录 (N, 31, 5) 样本：−20 s ~ +10 s"],
    ["路侧 json", "文件名时段覆盖事件，且设备距事件 ≤ 500 m"],
    ["龙门架", "视频时段与事件重叠，且案例目录 VIN 与事件一致"],
  ];
  steps.forEach(([k, v], i) => {
    const y = 1.1 + i * 0.47;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y, w: 1.35, h: 0.4, fill: { color: P }, line: { color: P } });
    s.addText(`${i + 1}  ${k}`, { x: 0.6, y, w: 1.2, h: 0.4, fontFace: F, fontSize: 12, bold: true, color: WHITE, valign: "middle", margin: 0 });
    s.addShape(pres.shapes.RECTANGLE, { x: 1.85, y, w: 7.65, h: 0.4, fill: { color: i % 2 ? WHITE : "F2F4F7" }, line: { color: "C8CED8", width: 0.5 } });
    s.addText(v, { x: 1.95, y, w: 7.5, h: 0.4, fontFace: F, fontSize: 11.5, color: TXT, valign: "middle", margin: 0 });
  });
  concl(s, "校验：A/B 类 56 个事件的 drive_mode 1→0 与事件时间差全部 ≤ 30 s", 4.45, 0.55);
  footer(s);
}

// ---------- 10 数据量与字段 ----------
{
  const s = pres.addSlide(); header(s, "4", "数据量：视频 29 GB，participant 226 GB");
  table(s, [
    ["数据", "数量", "时间", "主要字段"],
    ["自车视频", "1424 文件 · 29 GB", "2023-12~2024-07", "ch1 前视 / ch2 座舱 / ch3 踏板"],
    ["0920 台账", "1925 条", "2024-04~2024-09", "disengage_time, vin, acc_*, 紧急接管, 场景标签, 描述"],
    ["表格轨迹", "2710 文件（去重）", "2023-12~2025-05", "vin, position_time, drive_mode, latitude, longitude"],
    ["local_vehicle_info", "50 文件 · 4.66 GB", "车端原始导出", "vin, positiontime, drivemode, 经纬度"],
    ["NPY 全部脱离", "1,722,711 条", "2021-07~2024-01", "vin, 时间, 经纬度；样本 (N,31,5)"],
    ["NPY 关键脱离", "377 条", "2023-12~2024-01", "速度、横/纵向加速度、经纬度"],
    ["龙门架视频", "394 mp4 · 17 路口", "2024-04~2025-03", "案例目录 序号-VIN-日期 时间"],
    ["路侧 json", "1136（226 GB）", "2024 两天；2025-03~05", "timestamp, ptcType, speed, heading, 经纬度"],
    ["运行安全评价", "818 案例文件", "2025-03~04", "自车与路侧匹配的 case 轨迹"],
    ["地图类", "64,436 文件", "–", "png 瓦片 64,396；shp 33"],
  ], { x: 0.5, y: 1.08, w: 9.0, colW: [1.45, 1.75, 1.8, 4.0], fontSize: 10, rowH: 0.3 });
  concl(s, "信号配时、交通流只有 2024-01-02、02-19 两天样本；地图类几乎全是瓦片图片，无高精地图", 4.75, 0.45);
  footer(s);
}

// ---------- 11 时空覆盖 ----------
{
  const s = pres.addSlide(); header(s, "4", "覆盖：视频与路侧在时间上几乎不重叠");
  // 时间轴 2021-07 ~ 2025-06，只画 2023-10 之后的细节，NPY 用左侧截断标记
  const x0 = 2.4, x1 = 9.3, t0 = 2023 + 9 / 12, t1 = 2025 + 6 / 12;
  const X = (y, m) => x0 + ((y + (m - 1) / 12) - t0) / (t1 - t0) * (x1 - x0);
  const rows = [
    ["NPY 全部脱离", [[2023, 10, 2024, 1.1]], "2021-07 起 → 2024-01-02"],
    ["自车视频", [[2023, 12, 2024, 7.8]], ""],
    ["0920 台账", [[2024, 4, 2024, 9.99]], ""],
    ["表格轨迹", [[2023, 12, 2025, 5.9]], ""],
    ["龙门架视频", [[2024, 4.6, 2025, 3.7]], ""],
    ["路侧 participant", [[2024, 1, 2024, 1.2], [2024, 2.6, 2024, 2.8], [2025, 3.4, 2025, 5.8]], ""],
  ];
  // 年份刻度
  [[2024, 1], [2024, 7], [2025, 1]].forEach(([y, m]) => {
    s.addShape(pres.shapes.LINE, { x: X(y, m), y: 1.1, w: 0, h: 2.55, line: { color: "C8CED8", width: 0.75, dashType: "dash" } });
    s.addText(`${y}-${String(m).padStart(2, "0")}`, { x: X(y, m) - 0.45, y: 3.66, w: 0.9, h: 0.25, fontFace: F, fontSize: 10, color: GRAY, align: "center", margin: 0 });
  });
  rows.forEach(([name, segs, note], i) => {
    const y = 1.15 + i * 0.42;
    s.addText(name, { x: 0.5, y, w: 1.8, h: 0.34, fontFace: F, fontSize: 11.5, bold: true, color: TXT, align: "right", valign: "middle", margin: 0 });
    segs.forEach(([ya, ma, yb, mb]) => {
      const a = X(ya, ma), b = X(yb, mb);
      s.addShape(pres.shapes.RECTANGLE, { x: a, y: y + 0.05, w: Math.max(0.06, b - a), h: 0.24, fill: { color: i === 5 ? EMP : P }, line: { color: i === 5 ? EMP : P } });
    });
    if (note) s.addText(note, { x: X(2024, 1.3), y, w: 2.5, h: 0.34, fontFace: F, fontSize: 10, color: GRAY, valign: "middle", margin: 0 });
  });
  richBullets(s, [
    "空间：2025 年 participant 设备固定在同一路口；龙门架 17 个路口",
    "2025 年批次：03-15~03-20；04-12~04-18 每天 2 h；05-17~05-22 每天 1 h",
  ], { x: 0.5, y: 3.98, w: 9.0, h: 0.7 }, 11);
  concl(s, "有视频的 2023-12~2024-07 几乎没有 participant；2025 年有路侧但没有视频", 4.75, 0.45);
  footer(s);
}

// ---------- 12 数据质量 ----------
{
  const s = pres.addSlide(); header(s, "5", "质量：3 项 FAIL 均为数据本身问题");
  const cards = [
    ["9", "个视频文件路径无 VIN", "无法建索引，单列在 clips.csv"],
    ["101", "个片段拷贝大小不一致", "代表文件优先取原始目录"],
    ["18", "个片段不可读", "另 243 个实际比文件名短，多数短 10 ~ 60 s"],
  ];
  cards.forEach(([n, t, d], i) => {
    const x = 0.5 + i * 3.05;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.15, w: 2.85, h: 1.45, fill: { color: WHITE }, line: { color: P, width: 1 } });
    s.addText(n, { x, y: 1.2, w: 2.85, h: 0.6, fontFace: F, fontSize: 30, bold: true, color: EMP, align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x, y: 1.8, w: 2.85, h: 0.35, fontFace: F, fontSize: 13, bold: true, color: TXT, align: "center", margin: 0 });
    s.addText(d, { x: x + 0.1, y: 2.15, w: 2.65, h: 0.4, fontFace: F, fontSize: 10.5, color: GRAY, align: "center", margin: 0 });
  });
  s.addText("使用注意", { x: 0.5, y: 2.8, w: 9, h: 0.3, fontFace: F, fontSize: 13, bold: true, color: P, margin: 0 });
  richBullets(s, [
    "2024 年 participant / 信号 / 交通流只有 2 天样本，2024 年的 E 类只能依靠龙门架视频",
    "NPY 全部脱离清单只到 2024-01-02，没有覆盖 2024 年 1 ~ 9 月",
    "0920 的“是否紧急接管”、场景标签、描述为人工填写，用加速度阈值只能复现 67.8%",
    "all927 等表的 position_time 为 UTC，使用时需 +8 h",
  ], { x: 0.5, y: 3.12, w: 9.0, h: 1.45 }, 12);
  concl(s, "检查项 PASS 14 / FAIL 3：统计结果可信，FAIL 项已在资产表中标注", 4.68, 0.5);
  footer(s);
}

// ---------- 13 原始数据保存位置 ----------
{
  const s = pres.addSlide(); header(s, "6", "保存：原始数据全部在堡垒机 D 盘");
  table(s, [
    ["数据", "堡垒机上的原始位置"],
    ["自车视频", "D:\\video2 · video0719 · video5 · VIDEO · video4 · video3（另 D:\\code、D:\\case 少量）"],
    ["0920 台账", "D:\\code\\data\\脱离事件汇总-0920（请复制后再做修改）.xlsx"],
    ["表格轨迹", "D:\\code\\data\\920汽车城脱离时间整理\\all927.xlsx；D:\\code\\data\\chenming\\dl\\datasource\\dis_joined1.xlsx"],
    ["车端原始导出", "D:\\code\\data\\chenming\\data\\local_vehicle_info\\（50 个 csv，4.66 GB）"],
    ["NPY", "D:\\code\\critical_X.npy；D:\\code\\data\\chenming\\processing_data\\（critical、all 等）"],
    ["龙门架视频", "D:\\code（178）· D:\\新建文件夹（159）· D:\\chenming_backup（57）"],
    ["路侧 participant", "D:\\code（868）· D:\\250408提供最新（179）· 桌面 250315-0709（28）· D:\\RoadsideData"],
    ["运行安全评价", "D:\\运行安全评价\\（veh_origin、con_res）"],
    ["前人处理产物", "D:\\堡垒机数据筛选（35 个事件、105 个 avi、README）"],
  ], { x: 0.5, y: 1.1, w: 9.0, colW: [1.6, 7.4], fontSize: 10, rowH: 0.31 });
  concl(s, "数据库 / FTP 取数渠道已失效：堡垒机上的数据就是唯一副本，不能再补充", 4.65, 0.5);
  footer(s);
}

// ---------- 14 处理产出与留存 ----------
{
  const s = pres.addSlide(); header(s, "6", "保存：产出在堡垒机，脚本与记录在 GitHub");
  const col = (x, title, items) => {
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.1, w: 2.9, h: 0.42, fill: { color: P }, line: { color: P } });
    s.addText(title, { x, y: 1.1, w: 2.9, h: 0.42, fontFace: F, fontSize: 13, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.52, w: 2.9, h: 2.95, fill: { color: "F7F8FA" }, line: { color: "C8CED8", width: 0.5 } });
    richBullets(s, items, { x: x + 0.08, y: 1.6, w: 2.75, h: 2.85 }, 10.5);
  };
  col(0.5, "堡垒机：处理产出", [
    [{ text: "D:\\takeover_audit\\<步骤>\\", options: { bold: true } }, { text: "：00 ~ 13 各步结果" }],
    [{ text: "12_verify\\事件资产表.xlsx", options: { bold: true } }, { text: "（2025 年前）、事件资产表_2025.xlsx" }],
    "明细：clips.csv、traj_files.csv、summary.txt 等",
    "13_diag\\notraj_diag.csv（稀疏轨迹诊断）",
    "脚本副本：桌面\\新建文件夹\\00 ~ 13.py",
  ]);
  col(3.55, "GitHub：脚本与记录", [
    [{ text: "仓库 sunyuhang2001/takeover", options: { bold: true } }],
    "分支 claude/local-cloud-workspace-diff-3mj8r1",
    "bastion/：00 ~ 13 脚本 + 校验码（README）",
    "notes/round1 ~ 8：每轮汇总结论（不含 VIN）",
    "docs/plan.md、docs/report.md（本汇报文字版）",
  ]);
  col(6.6, "限制与缺口", [
    [{ text: "堡垒机不能导出文件", options: { bold: true } }, { text: "，结果只能截图回传" }],
    "逐条明细（含 VIN、坐标）只留在堡垒机，不进仓库",
    "其他账号堡垒机上的 D:\\SGSJ（事故）、D:\\脱离事件路测数据、D:\\chenming\\anli 本次访问不到",
    "D 盘 800 GB，已用约 486 GB",
  ]);
  concl(s, "复查或重跑：在堡垒机上用 process 环境运行 bastion/ 下脚本，输出写到 D:\\takeover_audit\\", 4.6, 0.55);
  footer(s);
}

pres.writeFile({ fileName: "接管数据现状汇报.pptx" }).then((f) => console.log("written", f, "slides", pres.slides.length));
