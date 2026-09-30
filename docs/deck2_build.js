// 接管事件字段现状与补充方案 —— 按 PPT制作/pptx/SKILL.md 规范（白底、单主色、微软雅黑、结论框）
const pptxgen = require("pptxgenjs");
const D = require("./deck2_fields.json");
const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; pres.title = "接管事件字段现状与补充方案";
const P = "1F3864", TINT = "DDE1E8", TXT = "333333", GRAY = "808080", EMP = "8B0000", WHITE = "FFFFFF", F = "Microsoft YaHei";
let page = 0; const slides = [];
function header(s, sec, title) {
  s.background = { color: WHITE };
  s.addShape(pres.shapes.RECTANGLE, { x: 0.35, y: 0.25, w: 0.46, h: 0.46, fill: { color: P }, line: { color: P } });
  s.addText(sec, { x: 0.35, y: 0.25, w: 0.46, h: 0.46, fontFace: F, fontSize: 14, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
  s.addText(title, { x: 0.92, y: 0.2, w: 8.8, h: 0.56, fontFace: F, fontSize: 22, bold: true, color: P, valign: "middle", margin: 0 });
}
function footer(s, note) {
  page += 1; slides.push(s);
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.33, w: 10, h: 0.295, fill: { color: TINT }, line: { color: TINT } });
  s.addText(note || "接管事件字段现状与补充方案 · 字段清单 V2.04（110 个字段）", { x: 0.35, y: 5.33, w: 8.2, h: 0.295, fontFace: F, fontSize: 9, color: GRAY, valign: "middle", margin: 0 });
  s._pno = page;
}
function concl(s, text, y, h = 0.42) {
  s.addShape(pres.shapes.RECTANGLE, { x: 0.35, y, w: 9.3, h, fill: { color: TINT }, line: { color: P, width: 1 } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.35, y, w: 0.07, h, fill: { color: P }, line: { color: P } });
  s.addText(text, { x: 0.52, y, w: 9.05, h, fontFace: F, fontSize: 12, color: TXT, valign: "middle", margin: 0 });
}
const hcell = (t) => ({ text: t, options: { bold: true, color: WHITE, fill: { color: P }, align: "center", valign: "middle" } });
function cellStyle(v, part) {
  const o = { align: "center", valign: "middle", color: TXT };
  if (v === "没有") { o.color = "A6A6A6"; return o; }
  if (part === 2) {
    if (v === "已有") { o.fill = { color: TINT }; o.bold = true; o.color = P; }
    else if (v.startsWith("模型")) { o.color = P; }
    else if (v.startsWith("人工")) { o.color = "5A3E1B"; }
    else { o.color = "4A5568"; }
  } else {
    o.fill = { color: TINT }; o.color = P;
    if (v.startsWith("部分") || v.endsWith("≈")) o.italic = true;
  }
  return o;
}
function matrixSlides(part, secNo, title, rows, legend) {
  // 按模块分组，每页最多 12 行
  const groups = []; let cur = null;
  rows.forEach((r) => { if (!cur || cur.mod !== r[0]) { cur = { mod: r[0], rows: [] }; groups.push(cur); } cur.rows.push(r); });
  groups.forEach((g) => {
    const chunks = []; for (let i = 0; i < g.rows.length; i += 12) chunks.push(g.rows.slice(i, i + 12));
    chunks.forEach((ch, ci) => {
      const s = pres.addSlide();
      header(s, secNo, `${title}｜${g.mod}${chunks.length > 1 ? `（${ci + 1}/${chunks.length}）` : ""}`);
      const head = [hcell("字段"), hcell("P")].concat(D.levels.map((l) => hcell(l.replace("(", "\n").replace(")", ""))));
      const body = ch.map((r) => [
        { text: r[1], options: { bold: r[2] === "P0", color: TXT, valign: "middle" } },
        { text: r[2], options: { align: "center", color: r[2] === "P0" ? EMP : GRAY, bold: r[2] === "P0", valign: "middle" } },
      ].concat(r.slice(3).map((v) => ({ text: v, options: cellStyle(v, part) }))));
      s.addTable([head].concat(body), { x: 0.3, y: 0.88, w: 9.4, colW: [1.75, 0.33].concat(Array(11).fill(0.6656)), fontFace: F, fontSize: 8,
        rowH: [0.38].concat(Array(body.length).fill(0.3)), border: { type: "solid", pt: 0.5, color: "C8CED8" }, margin: [1, 2, 1, 2] });
      footer(s, legend);
    });
  });
}

// ---------- 封面 ----------
{
  const s = pres.addSlide(); s.background = { color: WHITE };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.35, h: 5.625, fill: { color: P }, line: { color: P } });
  s.addText("接管事件字段现状与补充方案", { x: 0.9, y: 1.45, w: 8.5, h: 0.8, fontFace: F, fontSize: 36, bold: true, color: P, margin: 0 });
  s.addText("对照《字段清单 V2.04》（110 个字段），按数据等级给出现状与可行的补充方式", { x: 0.9, y: 2.3, w: 8.5, h: 0.45, fontFace: F, fontSize: 16, color: TXT, margin: 0 });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.9, y: 3.0, w: 8.2, h: 0.9, fill: { color: TINT }, line: { color: TINT } });
  s.addText([
    { text: "数据范围：堡垒机全部数据（2023-12 ~ 2025-05），2663 个接管事件", options: { breakLine: true } },
    { text: "口径：只写有真实数据或可行方法的内容；推断不算，暂时写“没有”" },
  ], { x: 1.1, y: 3.0, w: 7.9, h: 0.9, fontFace: F, fontSize: 13, color: TXT, valign: "middle", margin: 0, paraSpaceAfter: 4 });
  s.addText("汇报人：[待补充]        2026-09-30", { x: 0.9, y: 4.4, w: 8, h: 0.4, fontFace: F, fontSize: 13, color: GRAY, margin: 0 });
  page += 1;
}
// ---------- 目录 ----------
{
  const s = pres.addSlide(); header(s, "目", "目录");
  [["1", "各等级事件与数据概况", "每个等级有多少事件，各有哪些数据"], ["2", "表一：字段现状", "110 个字段 × 11 个等级：现在有没有、从哪来"],
   ["3", "表二：补充方式", "缺的字段怎么补：模型、人工、地图、气象"], ["4", "可能的补充方案", "每种方法怎么做、补哪些字段、适用哪些等级"]].forEach(([n, t, d], i) => {
    const y = 1.0 + i * 1.02;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.9, y, w: 0.75, h: 0.78, fill: { color: P }, line: { color: P } });
    s.addText(n, { x: 0.9, y, w: 0.75, h: 0.78, fontFace: F, fontSize: 26, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
    s.addShape(pres.shapes.RECTANGLE, { x: 1.65, y, w: 7.4, h: 0.78, fill: { color: "F2F4F7" }, line: { color: "F2F4F7" } });
    s.addText([{ text: t, options: { bold: true, color: P, fontSize: 18, breakLine: true } }, { text: d, options: { fontSize: 12, color: TXT } }],
      { x: 1.85, y, w: 7.1, h: 0.78, fontFace: F, valign: "middle", margin: 0 });
  });
  footer(s);
}
// ---------- Part 1 ----------
{
  const s = pres.addSlide(); header(s, "1", "各等级事件与数据概况");
  const H = ["等级", "含义", "事件数", "有原因\n(0920)", "前视\n视频", "三路视频\n齐全", "逐秒\n轨迹", "31 帧\n轨迹(NPY)", "路口视频\n拍到本车", "路侧周边\n车辆(JSON)"].map(hcell);
  const R = [
    ["A", "前视视频 + 轨迹 + 原因", 39, 39, 39, 35, 39, 0, 2, 0], ["B", "前视视频 + 轨迹", 109, 0, 109, 103, 24, 101, 0, 2],
    ["C", "只有前视视频（轨迹太稀）", 165, 0, 165, 145, 0, 0, 0, 0], ["D", "只有座舱/踏板视频", 153, 5, 0, 0, 5, 1, 1, 0],
    ["E", "无车载视频：轨迹 + 路口视频", 36, 36, 0, 0, 36, 0, 36, 0], ["F", "只有轨迹", 2120, 1845, 0, 0, 1862, 275, 0, 0],
    ["H", "只有路口视频", 1, 0, 0, 0, 0, 0, 1, 0], ["X", "视频损坏", 11, 0, 0, 0, 0, 0, 0, 0],
    ["2025-E", "轨迹 + 路侧周边车辆", 15, 0, 0, 0, 15, 0, 1, 15], ["2025-F", "只有轨迹", 12, 0, 0, 0, 12, 0, 0, 0],
    ["2025-H", "轨迹不足 20 秒", 2, 0, 0, 0, 0, 0, 0, 1],
  ];
  const tot = ["合计", "", 2663, 1925, 313, 283, 1993, 377, 41, 18];
  const body = R.map((r, i) => r.map((v, j) => ({ text: String(v), options: {
    align: j <= 1 ? "left" : "center", valign: "middle", bold: j === 0 || (j === 2), color: j === 0 ? P : (v === 0 ? "B0B0B0" : TXT),
    fill: i % 2 ? { color: "F5F6F9" } : { color: WHITE } } })));
  body.push(tot.map((v, j) => ({ text: String(v), options: { align: j <= 1 ? "left" : "center", bold: true, color: P, fill: { color: TINT }, valign: "middle" } })));
  s.addTable([H].concat(body), { x: 0.3, y: 0.88, w: 9.4, colW: [0.72, 2.3, 0.72, 0.8, 0.7, 0.8, 0.72, 0.9, 0.82, 0.92], fontFace: F, fontSize: 10,
    rowH: [0.46].concat(Array(body.length).fill(0.27)), border: { type: "solid", pt: 0.5, color: "C8CED8" }, margin: [1, 4, 1, 4] });
  concl(s, "有前视视频 313 个；路口视频拍到本车 41 个（按经纬度补查新增 17 个）；有路侧周边车辆数据 18 个", 4.8, 0.42);
  footer(s, "逐秒轨迹 = 表格轨迹（连续覆盖 ≥20 s）；31 帧轨迹 = NPY 样本（接管前 20 s ~ 后 10 s）；有原因 = 在 0920 台账里有人工描述");
}
// ---------- Part 2 ----------
matrixSlides(1, "2", "表一·现状", D.t1, "表一：写来源 = 现在就有；≈ = 近似；部分 = 只有一部分；没有 = 现在没有");
// ---------- Part 3 ----------
{
  const s = pres.addSlide(); header(s, "3", "表二·补充方式：P0 字段（65 个）按补充方式计数");
  const ks = ["已有", "模型", "人工", "地图", "气象", "没有"];
  const rows = D.levels.map((lv, i) => {
    const c = {}; D.t2.filter((r) => r[2] === "P0").forEach((r) => { const k = r[3 + i].split("·")[0]; c[k] = (c[k] || 0) + 1; });
    return [lv].concat(ks.map((k) => c[k] || 0));
  });
  const body = rows.map((r) => r.map((v, j) => ({ text: String(v), options: { align: j ? "center" : "left", bold: j === 0 || j === 1, color: j === 0 ? P : j === 6 ? "8C8C8C" : TXT,
    fill: j === 1 ? { color: TINT } : { color: WHITE }, valign: "middle" } })));
  s.addTable([["等级"].concat(ks).map(hcell)].concat(body), { x: 0.9, y: 0.95, w: 8.2, colW: [1.6, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1], fontFace: F, fontSize: 11,
    rowH: [0.34].concat(Array(body.length).fill(0.28)), border: { type: "solid", pt: 0.5, color: "C8CED8" } });
  concl(s, "A、B 类缺的字段多数能用模型或人工补；E、F 和 2025 年各等级没有车载视频，驾驶员相关字段写“没有”", 4.55, 0.45);
  footer(s);
}
matrixSlides(2, "3", "表二·补充方式", D.t2, "表二：已有 = 不用补；模型·X / 人工·X = 用 X 视频跑模型 / 人工看；地图、气象 = 外网查询带入；没有 = 暂无办法");
// ---------- Part 4 ----------
const M = [
  ["前视视频 · 模型", "目标检测 + 单目测距（默认内参，用车道宽 3.5 m 标定尺度），逐帧差分得相对速度，距离 ÷ 相对速度 = TTC；误差约 10%~20%", "目标物类型、相对位置/速度、TTC、最小距离、前车距离、障碍物", "A B C"],
  ["前视视频 · 模型", "车道线、交通标志、信号灯、路面识别：数左侧车道线得车道编号；识别限速牌数字；信号灯分红黄绿", "车道编号/类型、交通主标志、信号灯、路面状态、其他参数", "A B C"],
  ["前视视频 · 模型", "视觉里程计（光流 / ORB 特征）求帧间位移，车道宽定尺度，再用路口位置配准到经纬度", "C 类的速度、加速度、航向、经纬度（可升为 B 类）", "C"],
  ["座舱视频 · 模型", "后视镜位置俯拍：人脸关键点估头部朝向和眼睛开合，判断视线、闭眼、分心；手部和身体关键点判断手握方向盘、坐姿；方向盘转动估转角", "注意力、视线、疲劳、手握方向盘及时刻、正常驾驶位、方向盘角度、首次转向", "A B C D"],
  ["踏板视频 · 模型", "脚部检测 / 踏板区域帧差：脚踩下制动踏板的第一帧 = 首次制动，10 fps 精度约 0.1 s；踏板深浅粗分三档", "首次制动/油门时刻、制动状态、踏板开度、接管操作类型、制动反应时间", "A B C D"],
  ["座舱音轨 · 模型（已验证）", "音轨为 PCM，程序可直接读；检测约 2 kHz 提示音的起止、次数、间隔。已验证：只有切换时的一声，没有请求序列", "是否发出接管请求、听觉告警、告警形式", "A B C D"],
  ["路口视频 · 模型", "选停止线/车道线角点对照上海道路 shp 求单应矩阵；YOLO + ByteTrack 跟踪，像素坐标换成地面坐标", "E 类目标物轨迹、相对位置/速度、TTC、最小距离、车流", "E H"],
  ["视频 · 人工审计", "每个事件看接管前后 20 s，按字段枚举勾选，约 10 分钟一个事件", "退出原因、功能边界、事故结果、碰撞方向、是否真实失败、反应时间、安全带、气囊、MRM", "A B C D E H"],
  ["路侧回放 · 人工审计", "把 participant 目标轨迹和自车轨迹画成俯视动画，人工判读冲突对象和接管原因", "退出原因、事故经过/结果、碰撞方向、是否真实失败", "2025-E 2025-H"],
  ["外部地图", "外网查 OSM/高德路网后带入（堡垒机已有上海道路 shp）：轨迹地图匹配，读道路等级、限速、车道数、车道线", "地图匹配、道路类型、车道线几何、特殊区域、坐标类型", "有轨迹的等级"],
  ["外部气象", "外网按日期查嘉定区历史逐小时天气后带入", "天气、温度、湿度、能见度、路面状态", "全部等级"],
];
[[0, 4], [4, 8], [8, 11]].forEach(([a, b], k) => {
  const s = pres.addSlide(); header(s, "4", `可能的补充方案（${k + 1}/3）`);
  const H = ["数据来源 · 方式", "怎么做（例子）", "补哪些字段", "适用等级"].map(hcell);
  const body = M.slice(a, b).map((r, i) => r.map((v, j) => ({ text: v, options: { valign: "middle", bold: j === 0, color: j === 0 ? P : TXT,
    fill: i % 2 ? { color: "F5F6F9" } : { color: WHITE }, align: j === 3 ? "center" : "left" } })));
  s.addTable([H].concat(body), { x: 0.3, y: 0.9, w: 9.4, colW: [1.55, 4.15, 2.75, 0.95], fontFace: F, fontSize: 10,
    rowH: [0.34].concat(Array(body.length).fill(0.8)), border: { type: "solid", pt: 0.5, color: "C8CED8" }, margin: [3, 5, 3, 5] });
  footer(s, "前提已确认：座舱俯拍（看不到中控屏）、踏板清晰、有 GPU 和模型、相机用默认参数、地图和气象可外网带入");
});
{
  const s = pres.addSlide(); header(s, "4", "暂时没有可行办法的字段");
  const rows = [
    ["当前激活的 ADS 功能、系统降级状态", "数据里没有记录；座舱摄像头拍不到中控屏"],
    ["视觉告警、触觉告警", "没有 HMI 记录；拍不到屏幕，也测不到振动"],
    ["档位、GNSS / IMU 运行状态、定位有效性", "轨迹表里没有这些列"],
    ["ODD 运行状态", "没有 ODD 定义，无法判断"],
    ["事故编号", "本批是接管事件，没有事故编号"],
    ["无车载视频等级（E、F、2025 年）的驾驶员状态", "没有座舱和踏板视频，历史数据补不回来"],
  ];
  const body = rows.map((r, i) => r.map((v, j) => ({ text: v, options: { valign: "middle", bold: j === 0, color: j === 0 ? P : TXT, fill: i % 2 ? { color: "F5F6F9" } : { color: WHITE } } })));
  s.addTable([["字段", "原因"].map(hcell)].concat(body), { x: 0.6, y: 0.95, w: 8.8, colW: [4.2, 4.6], fontFace: F, fontSize: 12,
    rowH: [0.36].concat(Array(body.length).fill(0.48)), border: { type: "solid", pt: 0.5, color: "C8CED8" }, margin: [3, 6, 3, 6] });
  concl(s, "这些字段在表里统一写“没有”，后续如果拿到新数据（如 HMI 日志、CAN 数据）再补", 4.55, 0.45);
  footer(s);
}
slides.forEach((s) => s.addText(`${s._pno} / ${page}`, { x: 8.7, y: 5.33, w: 1.0, h: 0.295, fontFace: F, fontSize: 9, color: P, bold: true, align: "right", valign: "middle", margin: 0 }));
pres.writeFile({ fileName: "字段现状与补充方案.pptx" }).then((f) => console.log("written", f, "slides", pres.slides.length));
