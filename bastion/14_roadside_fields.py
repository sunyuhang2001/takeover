# -*- coding: utf-8 -*-
# 14_roadside_fields.py v3 : 路侧数据统计 + 理想字段表(V2.04, 110 个字段)与现有数据的映射 + 各等级补充方案（只读）
#   输入: 12 的 事件资产表.csv / 事件资产表_2025.csv、04 的 table_catalog.csv；重新扫盘找龙门架视频与路侧 json
#   [1] 路侧: 龙门架视频(案例目录/路口/相机/分辨率/时长) 与 路侧 json(各类型文件/时段/字段样例/频率)
#   [2] 事件层面: 每个等级(A–H/X, 2025 单列)有龙门架 / 有 json 的事件
#   [3] 现有数据源的列名清点(轨迹表 / 0920 / switch 平台表 / 运行安全评价 / NPY)
#   [4] switch 平台表按 VIN+时间匹配事件, 取 manual_reason(退出原因候选)
#   [5] 字段映射: 每个字段按"规定动作"顺序判断每个事件能否获得 -> 字段映射表.xlsx(总表 + 每个等级一张表)
#   规定动作: D 直接读取 / C 计算推导 / L 已有人工标注(0920台账) / R 路侧提取 / M 模型恢复 / V 视频人工审计 / X 外部地图 / W 外部气象 / N 无法补充
# 用法: python 14_roadside_fields.py [根目录...]   (默认 C:\ D:\)
import os, sys, re, json, hashlib, time
import numpy as np
import pandas as pd

NAME, VERSION = "14_roadside_fields", "v3"
BASE = r"D:\takeover_audit"
IN12 = BASE + r"\12_verify"
CATALOG = BASE + r"\04_tables\table_catalog.csv"
OUT_DIR = BASE + r"\14_fields"
ROOTS = ["C:\\", "D:\\"]
SKIP = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information",
        "appdata", "miniconda3", "anaconda3", "matlab", "microsoft vs code", "pycharm", "wps", "node_modules", ".git",
        "site-packages", "takeover_audit"}
RE_GV = re.compile(r"^(\d+)_(.+?)_(\d{14})-(\d{14})\.mp4$", re.I)
RE_RS = re.compile(r"^(participant|vehicle_track|traffic_flow|signal|event|camera_url)_(\d{14})-(\d{14})\.json$", re.I)
RE_CASE = re.compile(r"\d+-([A-HJ-NPR-Z0-9]{17})-(\d{4}-\d{2}-\d{2}) ?(\d{6})")
MAP_EXT = {".osm", ".xodr", ".shp", ".geojson", ".kml", ".kmz", ".gpkg", ".mbtiles", ".dwg"}
Y2025 = 1735689600
SHIFTS = (0, 8 * 3600, -8 * 3600)
RS_COLS = {"participant": "路侧_周边交通参与者", "vehicle_track": "路侧_车辆轨迹", "traffic_flow": "路侧_交通流",
           "signal": "路侧_信号配时", "event": "路侧_路侧事件"}

ACT = {"D": "直接读取", "C": "计算推导", "L": "已有人工标注(0920)", "R": "路侧提取", "M": "模型恢复",
       "V": "视频人工审计", "X": "外部地图数据", "W": "外部气象数据", "N": "无法补充"}
HAVE = ("D", "C", "L", "R")          # 现有数据即可
ABLE = HAVE + ("M", "V", "X", "W")   # 可补充
# 外部数据只用两类: 地图(OSM/高德/百度路网, 有条件用高精地图) 与 历史气象(按日期+位置查站点/再分析数据)

# 理想字段表 V2.04：(模块, 字段, 优先级)
SPEC = [
    ("基础信息与时间同步", "样本类型", "P0"), ("基础信息与时间同步", "自动驾驶运行里程与运行时长", "P0"),
    ("基础信息与时间同步", "车辆识别码", "P0"), ("基础信息与时间同步", "事件编号", "P0"),
    ("基础信息与时间同步", "数据创建时间", "P0"), ("基础信息与时间同步", "数据上报时间", "P0"),
    ("基础信息与时间同步", "车端时间戳", "P0"), ("基础信息与时间同步", "数据来源", "P1"),
    ("基础信息与时间同步", "采样频率", "P1"),
    ("驾驶权与系统状态", "控制模式", "P0"), ("驾驶权与系统状态", "自动驾驶系统运行状态", "P0"),
    ("驾驶权与系统状态", "当前激活的ADS功能", "P0"), ("驾驶权与系统状态", "系统降级状态", "P0"),
    ("驾驶权与系统状态", "自动驾驶退出原因", "P0"), ("驾驶权与系统状态", "最小风险策略状态", "P1"),
    ("驾驶权与系统状态", "接管完成状态", "P0"), ("驾驶权与系统状态", "远程控制状态", "P1"),
    ("驾驶权与系统状态", "ODD运行状态", "P1"), ("驾驶权与系统状态", "ODD退出原因", "P1"),
    ("驾驶权与系统状态", "功能边界类型", "P1"), ("驾驶权与系统状态", "最小风险策略触发原因", "P1"),
    ("接管请求与告警信息", "是否发出接管请求", "P0"), ("接管请求与告警信息", "接管请求开始时间", "P0"),
    ("接管请求与告警信息", "接管请求原因", "P0"), ("接管请求与告警信息", "接管紧急等级", "P1"),
    ("接管请求与告警信息", "告警形式", "P0"), ("接管请求与告警信息", "视觉告警", "P0"),
    ("接管请求与告警信息", "听觉告警", "P0"), ("接管请求与告警信息", "触觉告警", "P0"),
    ("接管请求与告警信息", "第一阶段告警开始、结束时间", "P0"), ("接管请求与告警信息", "第二阶段告警开始、结束时间", "P0"),
    ("接管请求与告警信息", "第三阶段告警开始、结束时间", "P0"), ("接管请求与告警信息", "告警是否升级", "P1"),
    ("接管请求与告警信息", "ADS事件", "P0"), ("接管请求与告警信息", "失效事件", "P0"),
    ("驾驶员状态与人因数据", "驾驶员是否手握方向盘", "P0"), ("驾驶员状态与人因数据", "驾驶员是否在正常驾驶位", "P0"),
    ("驾驶员状态与人因数据", "安全带状态", "P1"), ("驾驶员状态与人因数据", "驾驶员注意力状态", "P0"),
    ("驾驶员状态与人因数据", "驾驶员疲劳状态", "P1"), ("驾驶员状态与人因数据", "驾驶员视线方向", "P1"),
    ("驾驶员状态与人因数据", "驾驶员接管反应时间", "P0"), ("驾驶员状态与人因数据", "驾驶员状态视频证据", "P1"),
    ("驾驶员状态与人因数据", "驾驶员制动油门反应时间", "P0"), ("驾驶员状态与人因数据", "手握方向盘时间", "P0"),
    ("车辆运动与操作响应", "车辆速度", "P0"), ("车辆运动与操作响应", "纵向加速度", "P0"),
    ("车辆运动与操作响应", "横向加速度", "P0"), ("车辆运动与操作响应", "航向角", "P1"),
    ("车辆运动与操作响应", "方向盘角度", "P0"), ("车辆运动与操作响应", "方向盘角速度", "P1"),
    ("车辆运动与操作响应", "制动状态", "P0"), ("车辆运动与操作响应", "制动踏板开度", "P0"),
    ("车辆运动与操作响应", "加速踏板开度", "P0"), ("车辆运动与操作响应", "档位", "P0"),
    ("车辆运动与操作响应", "前车距离", "P1"), ("车辆运动与操作响应", "碰撞方向", "P0"),
    ("车辆运动与操作响应", "气囊状态", "P0"), ("车辆运动与操作响应", "首次制动时间", "P0"),
    ("车辆运动与操作响应", "首次转向时间", "P0"), ("车辆运动与操作响应", "首次油门操作时间", "P1"),
    ("车辆运动与操作响应", "接管操作类型", "P0"),
    ("位置、轨迹与道路场景", "经度", "P0"), ("位置、轨迹与道路场景", "纬度", "P0"),
    ("位置、轨迹与道路场景", "坐标类型", "P0"), ("位置、轨迹与道路场景", "定位有效性", "P0"),
    ("位置、轨迹与道路场景", "GNSS运行状态", "P1"), ("位置、轨迹与道路场景", "IMU运行状态", "P1"),
    ("位置、轨迹与道路场景", "地图匹配状态", "P1"), ("位置、轨迹与道路场景", "道路类型", "P0"),
    ("位置、轨迹与道路场景", "车道类型", "P1"), ("位置、轨迹与道路场景", "车道编号", "P1"),
    ("位置、轨迹与道路场景", "道路限速", "P1"), ("位置、轨迹与道路场景", "特殊区域边界", "P0"),
    ("感知目标物数据", "感知目标物类型", "P0"), ("感知目标物数据", "目标物相对位置X向", "P0"),
    ("感知目标物数据", "目标物相对位置Y向", "P0"), ("感知目标物数据", "目标物相对速度X向", "P0"),
    ("感知目标物数据", "目标物相对速度Y向", "P0"), ("感知目标物数据", "目标物长度", "P1"),
    ("感知目标物数据", "目标物高度", "P1"), ("感知目标物数据", "目标物宽度", "P1"),
    ("感知目标物数据", "目标物置信度", "P1"), ("感知目标物数据", "目标物编号", "P1"),
    ("感知目标物数据", "碰撞时间", "P0"), ("感知目标物数据", "与目标物最小距离", "P0"),
    ("感知目标物数据", "系统风险等级", "P1"),
    ("道路设施与交通环境", "交通主标志", "P1"), ("道路设施与交通环境", "交通管制信息", "P1"),
    ("道路设施与交通环境", "前方信号灯识别", "P1"), ("道路设施与交通环境", "异常路况信息", "P1"),
    ("道路设施与交通环境", "其他参数", "P1"), ("道路设施与交通环境", "车道线几何", "P1"),
    ("道路设施与交通环境", "障碍物类型", "P0"),
    ("自然环境数据", "天气信息", "P1"), ("自然环境数据", "外部光线", "P1"), ("自然环境数据", "外部温度", "P2"),
    ("自然环境数据", "外部湿度", "P2"), ("自然环境数据", "能见度", "P1"), ("自然环境数据", "路面状态", "P1"),
    ("事故与复核材料", "事故编号", "P0"), ("事故与复核材料", "事故发生时间", "P0"), ("事故与复核材料", "事故地点", "P0"),
    ("事故与复核材料", "事故经过描述", "P0"), ("事故与复核材料", "事故结果", "P0"), ("事故与复核材料", "损失程度", "P1"),
    ("事故与复核材料", "责任认定", "P1"), ("事故与复核材料", "事故前后视频", "P0"),
    ("事故与复核材料", "事故位置和轨迹证据", "P1"), ("事故与复核材料", "是否真实接管失败案例", "P0"),
]

# 现有表格里的列名识别（在事件所用轨迹文件的表头里找）
COLS = {
    "drive_mode": r"drive_?mode|drivemode|驾驶模式",
    "speed": r"^(?:speed|vehicle_?speed|velocity|spd|gps_?speed|车速|速度)$",
    "acc_long": r"acc_?long|long_?acc|acc_?x|纵向加速",
    "acc_lat": r"acc_?lat\b|acc_?lat$|lat_?acc|acc_?y|横向加速",
    "heading": r"heading|yaw|course|direction|航向",
    "steer": r"steer|wheel_?angle|方向盘",
    "brake": r"brake|制动",
    "throttle": r"throttle|accel_?pedal|acc_?pedal|油门|加速踏板",
    "gear": r"gear|档位|挡位",
    "upload": r"receive|upload|report|insert|create|入库|上报",
    "ads_status": r"ads_?status|auto\w*_?(?:state|status)|system_?status",
}
# 每个字段的规定动作顺序：(动作, 条件, 数据来源, 做法)。事件取第一个条件成立的动作；都不成立 = N 无法补充
#   条件: all/e9/traj/npy/anytraj/ch1/ch2/ch3/ch2a(座舱有音轨)/anyvid/gantry/rsp/rsig/revent/tsa/sw/lvi/col:<列>
R_ = lambda *a: a
VO = "单目视觉里程计/SLAM：从前视视频恢复自车相对轨迹，再用路口/地图配准到经纬度"
MOT = "路口视频多目标跟踪 + 相机标定(用地图/车道线求单应矩阵) → 各目标轨迹"
DET = "前视视频目标检测 + 单目测距/跟踪"
DMS = "座舱视频 DMS 模型(人脸关键点、视线、闭眼、手部检测) + 人工抽检"
PEDAL = "踏板视频动作识别(脚部检测/踏板区域帧差) + 人工抽检"
RULES = {
    "样本类型": [R_("L", "e9", "0920 是否紧急接管", "接管事件；按“是否紧急接管”分安全/不安全接管"),
             R_("C", "dm_or_npy", "drive_mode 1→0 / NPY", "有 1→0 即接管完成；加速度阈值区分不安全接管"),
             R_("V", "anyvid", "视频", "人工审计判定接管结果")],
    "自动驾驶运行里程与运行时长": [R_("C", "lvi", "local_vehicle_info 连续导出", "按 VIN 累计 drive_mode=1 的时长与经纬度里程"),
                        R_("C", "anytraj", "事件所在文件", "仅能给窗口内时长，全局暴露率需连续数据")],
    "车辆识别码": [R_("D", "all", "路径/表格 vin", "直接读取")],
    "事件编号": [R_("C", "all", "event_key", "VIN_YYYYMMDD_HHMMSS")],
    "数据创建时间": [R_("C", "all", "导出文件时间", "用源文件修改时间近似，标注“近似”")],
    "数据上报时间": [R_("D", "col:upload", "表中上报/入库时间列", "直接读取"), R_("C", "sw", "switch 平台记录时间", "平台记录时间近似上报时间")],
    "车端时间戳": [R_("D", "traj", "轨迹 position_time", "直接读取(注意 UTC +8h)"), R_("C", "npy", "NPY labels 时间", "labels 时间 + 帧序号"),
              R_("C", "anyvid", "视频文件名起止时间", "片段起点 + 帧号/帧率")],
    "数据来源": [R_("C", "all", "资产表来源列", "按来源文件填写")],
    "采样频率": [R_("C", "anytraj", "轨迹采样间隔 / NPY 1 Hz", "相邻点间隔"), R_("C", "anyvid", "视频帧率", "视频 fps")],
    "控制模式": [R_("D", "col:drive_mode", "drive_mode 列", "直接读取(1 自动 / 0 人工)"), R_("D", "sw", "switch 平台表", "drive_mode_switch"),
             R_("C", "npy", "NPY", "样本即 1→0：前 20 s 自动、后 10 s 人工"),
             R_("V", "ch2", "座舱视频", "看 HMI 模式显示/安全员接手时刻")],
    "自动驾驶系统运行状态": [R_("D", "col:ads_status", "表格", "直接读取"), R_("C", "dm_or_npy", "drive_mode", "drive_mode=1 视为运行"),
                   R_("V", "ch2", "座舱视频", "看 HMI 状态显示")],
    "当前激活的ADS功能": [R_("C", "all", "车队运营属性", "城市道路 Robotaxi 统一填写；需核对车队"), ],
    "系统降级状态": [R_("V", "ch2", "座舱视频", "看 HMI 降级提示"), R_("C", "anytraj", "轨迹", "限速/减速等行为特征推断(弱)")],
    "自动驾驶退出原因": [R_("D", "swreason", "switch manual_reason", "直接读取"), R_("L", "e9", "0920 描述", "文本归类到退出原因枚举"),
                 R_("V", "ch1", "前视+座舱视频", "人工审计归类"), R_("V", "gantry", "龙门架视频", "人工审计归类")],
    "最小风险策略状态": [R_("V", "ch1", "前视+座舱视频", "看是否靠边/停车(MRM 行为)"), R_("C", "anytraj", "轨迹", "接管前是否减速至停车")],
    "接管完成状态": [R_("C", "dm_or_npy", "drive_mode 1→0", "发生 1→0 即接管完成"), R_("L", "e9", "0920", "台账即已接管"),
               R_("V", "anyvid", "视频", "人工审计")],
    "远程控制状态": [R_("L", "e9", "0920 描述", "描述中是否远程接管"), R_("V", "ch2", "座舱视频", "安全员是否操作")],
    "ODD运行状态": [R_("V", "ch1", "前视视频", "按 ODD 定义人工判定"), R_("X", "anytraj", "地图", "道路等级/区域是否在 ODD 内")],
    "ODD退出原因": [R_("V", "ch1", "前视视频", "人工归类"), R_("L", "e9", "0920 描述", "文本归类")],
    "功能边界类型": [R_("V", "ch1", "前视视频(+0920 描述)", "人工归类"), R_("L", "e9", "0920 描述", "文本归类")],
    "最小风险策略触发原因": [R_("V", "ch1", "前视+座舱视频", "人工归类"), R_("L", "e9", "0920 描述", "文本归类")],
    "是否发出接管请求": [R_("M", "ch2a", "座舱视频音轨", "提示音检测"), R_("V", "ch2", "座舱视频", "看 HMI 弹窗；拍不到屏幕则按安全员行为判断主动/被动"),
                 R_("L", "e9", "0920 描述", "关键词(提示/请求/报警/主动)")],
    "接管请求开始时间": [R_("M", "ch2a", "座舱视频音轨", "提示音起点"), R_("V", "ch2", "座舱视频", "HMI 弹窗出现帧")],
    "接管请求原因": [R_("L", "e9", "0920 描述", "文本归类"), R_("V", "ch1", "视频", "人工归类")],
    "接管紧急等级": [R_("L", "e9", "0920 是否紧急接管", "直接映射"), R_("C", "anytraj", "轨迹/NPY 加速度", "阈值规则分级"),
               R_("V", "anyvid", "视频", "人工分级")],
    "告警形式": [R_("M", "ch2a", "座舱视频音轨", "有提示音=声音"), R_("V", "ch2", "座舱视频", "看屏幕/听声音")],
    "视觉告警": [R_("V", "ch2", "座舱视频", "截取 HMI 画面(文字/图标/颜色/是否倒计时)；字号、亮度等无法从历史视频得到")],
    "听觉告警": [R_("M", "ch2a", "座舱视频音轨", "提示音时长/间隔/重复次数、语音转文字；声压级无法得到")],
    "触觉告警": [R_("V", "ch2", "座舱视频", "只能看到安全员对振动的反应(弱)，振动参数无法补充")],
    "第一阶段告警开始、结束时间": [R_("M", "ch2a", "座舱视频音轨", "提示音分段"), R_("V", "ch2", "座舱视频", "HMI 画面分段")],
    "第二阶段告警开始、结束时间": [R_("M", "ch2a", "座舱视频音轨", "提示音分段"), R_("V", "ch2", "座舱视频", "HMI 画面分段")],
    "第三阶段告警开始、结束时间": [R_("M", "ch2a", "座舱视频音轨", "提示音分段"), R_("V", "ch2", "座舱视频", "HMI 画面分段")],
    "告警是否升级": [R_("M", "ch2a", "座舱视频音轨", "提示音频率/音量变化"), R_("V", "ch2", "座舱视频", "HMI 变化")],
    "ADS事件": [R_("C", "dm_or_npy", "drive_mode", "退出时刻；激活时刻由 0→1 得到"), R_("V", "ch2", "座舱视频", "HMI 状态")],
    "失效事件": [R_("L", "e9", "0920 描述", "文本归类(感知/定位/规划…)"), R_("V", "ch1", "前视+座舱视频", "人工归类")],
    "驾驶员是否手握方向盘": [R_("M", "ch2", "座舱视频", DMS)], "驾驶员是否在正常驾驶位": [R_("M", "ch2", "座舱视频", DMS)],
    "安全带状态": [R_("V", "ch2", "座舱视频", "人工审计(主驾)")], "驾驶员注意力状态": [R_("M", "ch2", "座舱视频", DMS)],
    "驾驶员疲劳状态": [R_("M", "ch2", "座舱视频", DMS)], "驾驶员视线方向": [R_("M", "ch2", "座舱视频", DMS)],
    "驾驶员接管反应时间": [R_("V", "ch1_ch2", "前视+座舱/踏板视频", "请求或风险出现 → 手/脚动作，逐帧标注")],
    "驾驶员状态视频证据": [R_("D", "ch2", "座舱视频 ch2", "原始视频")],
    "驾驶员制动油门反应时间": [R_("M", "ch3", "踏板视频", PEDAL)],
    "手握方向盘时间": [R_("M", "ch2", "座舱视频", "手部检测，取手接触方向盘帧")],
    "车辆速度": [R_("D", "col:speed", "速度列", "直接读取"), R_("D", "npy", "NPY 第 1 维", "直接读取"),
             R_("C", "anytraj", "经纬度", "相邻点距离/时间"), R_("M", "ch1", "前视视频", VO)],
    "纵向加速度": [R_("D", "col:acc_long", "纵向加速度列", "直接读取"), R_("D", "npy", "NPY", "直接读取"),
              R_("C", "anytraj", "速度/经纬度", "差分"), R_("M", "ch1", "前视视频", VO)],
    "横向加速度": [R_("D", "col:acc_lat", "横向加速度列", "直接读取"), R_("D", "npy", "NPY", "直接读取"),
              R_("C", "anytraj", "速度×航向变化率", "计算"), R_("M", "ch1", "前视视频", VO)],
    "航向角": [R_("D", "col:heading", "航向列", "直接读取"), R_("C", "anytraj", "经纬度", "相邻点方位角"), R_("M", "ch1", "前视视频", VO)],
    "方向盘角度": [R_("D", "col:steer", "方向盘列", "直接读取"), R_("C", "anytraj", "横摆角速度+车速", "自行车模型反推(需轴距/转向比)"),
              R_("M", "ch2", "座舱视频", "方向盘关键点姿态估计")],
    "方向盘角速度": [R_("D", "col:steer", "方向盘列", "角度差分"), R_("C", "anytraj", "反推的方向盘角度", "差分")],
    "制动状态": [R_("D", "col:brake", "制动列", "直接读取"), R_("M", "ch3", "踏板视频", PEDAL), R_("C", "anytraj", "纵向加速度", "减速度超阈值视为制动")],
    "制动踏板开度": [R_("D", "col:brake", "制动列", "直接读取"), R_("M", "ch3", "踏板视频", "踏板角度估计(粗)"), R_("C", "anytraj", "减速度", "按制动特性反推(粗)")],
    "加速踏板开度": [R_("D", "col:throttle", "油门列", "直接读取"), R_("M", "ch3", "踏板视频", "踏板角度估计(粗)"), R_("C", "anytraj", "加速度", "反推(粗)")],
    "档位": [R_("D", "col:gear", "档位列", "直接读取"), R_("C", "anytraj", "速度", "行驶中为 D 档"), R_("V", "anyvid", "视频", "倒车/停车可见")],
    "前车距离": [R_("R", "rsp", "路侧 participant", "同车道前方最近目标距离"), R_("M", "ch1", "前视视频", DET), R_("M", "gantry", "龙门架视频", MOT)],
    "碰撞方向": [R_("V", "ch1", "前视视频", "人工审计(无碰撞填无)"), R_("V", "gantry", "龙门架视频", "人工审计"), R_("C", "anytraj", "加速度突变方向", "冲击方向推断")],
    "气囊状态": [R_("V", "ch2", "座舱视频", "是否弹出"), R_("C", "anytraj", "加速度", "无碰撞冲击即未触发")],
    "首次制动时间": [R_("D", "col:brake", "制动列", "首个制动时刻"), R_("M", "ch3", "踏板视频", PEDAL), R_("C", "anytraj", "纵向加速度", "减速起点作代理")],
    "首次转向时间": [R_("D", "col:steer", "方向盘列", "首个转向时刻"), R_("C", "anytraj", "航向变化率", "代理"), R_("M", "ch2", "座舱视频", "手部/方向盘转动检测")],
    "首次油门操作时间": [R_("D", "col:throttle", "油门列", "直接读取"), R_("M", "ch3", "踏板视频", PEDAL), R_("C", "anytraj", "加速度", "加速起点作代理")],
    "接管操作类型": [R_("M", "ch3", "踏板+座舱视频", "制动/转向/组合识别"), R_("C", "anytraj", "加速度/航向", "规则判定"), R_("L", "e9", "0920 主车行为", "映射")],
    "经度": [R_("D", "anytraj", "轨迹/NPY 经度", "直接读取"), R_("M", "ch1", "前视视频", VO), R_("C", "e9", "0920 cross_name1", "路口坐标近似")],
    "纬度": [R_("D", "anytraj", "轨迹/NPY 纬度", "直接读取"), R_("M", "ch1", "前视视频", VO), R_("C", "e9", "0920 cross_name1", "路口坐标近似")],
    "坐标类型": [R_("C", "anytraj", "底图叠加", "GCJ02 与 WGS84 偏差约数百米，叠到道路底图可判定")],
    "定位有效性": [R_("C", "anytraj", "经纬度", "非零、无跳点即有效")],
    "GNSS运行状态": [R_("C", "anytraj", "轨迹", "缺点/跳点/静止漂移推断定位异常(代理)")],
    "IMU运行状态": [R_("C", "anytraj", "轨迹", "加速度/航向连续性推断(代理)")],
    "地图匹配状态": [R_("X", "anytraj", "路网(OSM/高精地图)", "轨迹地图匹配，输出匹配置信度")],
    "道路类型": [R_("L", "e9", "0920 道路类型", "直接映射"), R_("X", "anytraj", "路网", "地图匹配后读道路等级"), R_("V", "anyvid", "视频", "人工标注")],
    "车道类型": [R_("M", "ch1", "前视视频", "车道线/路面标识检测"), R_("X", "anytraj", "高精地图", "地图匹配"), R_("V", "gantry", "龙门架视频", "人工")],
    "车道编号": [R_("M", "ch1", "前视视频", "车道线检测定位所在车道"), R_("M", "gantry", "龙门架视频", MOT), R_("X", "anytraj", "高精地图", "车道级匹配")],
    "道路限速": [R_("X", "anytraj", "路网/OSM", "地图匹配后读限速"), R_("M", "ch1", "前视视频", "限速标志识别")],
    "特殊区域边界": [R_("X", "anytraj_or_e9", "地图(OSM/高德 POI)", "园区、停车场、地库多边形；当前事件均为城市道路")],
    "感知目标物类型": [R_("R", "rsp", "participant ptcType", "直接读取"), R_("L", "e9", "0920 目标物", "映射"),
                 R_("M", "ch1", "前视视频", DET), R_("M", "gantry", "龙门架视频", MOT)],
    "目标物相对位置X向": [R_("R", "rsp_traj", "participant + 自车轨迹", "转到自车坐标系"), R_("M", "ch1", "前视视频", DET), R_("M", "gantry", "龙门架视频", MOT)],
    "目标物相对位置Y向": [R_("R", "rsp_traj", "participant + 自车轨迹", "转到自车坐标系"), R_("M", "ch1", "前视视频", DET), R_("M", "gantry", "龙门架视频", MOT)],
    "目标物相对速度X向": [R_("R", "rsp_traj", "participant + 自车轨迹", "速度差投影"), R_("M", "ch1", "前视视频", DET + "，跟踪求导"), R_("M", "gantry", "龙门架视频", MOT)],
    "目标物相对速度Y向": [R_("R", "rsp_traj", "participant + 自车轨迹", "速度差投影"), R_("M", "ch1", "前视视频", DET + "，跟踪求导"), R_("M", "gantry", "龙门架视频", MOT)],
    "目标物长度": [R_("R", "rsp", "participant ptcSizeLength", "直接读取"), R_("M", "anyvid_ext", "视频检测框", "按类型取典型尺寸/3D 检测")],
    "目标物高度": [R_("R", "rsp", "participant ptcSizeHeight", "直接读取"), R_("M", "anyvid_ext", "视频检测框", "按类型取典型尺寸/3D 检测")],
    "目标物宽度": [R_("R", "rsp", "participant ptcSizeWidth", "直接读取"), R_("M", "anyvid_ext", "视频检测框", "按类型取典型尺寸/3D 检测")],
    "目标物置信度": [R_("R", "rsp_conf", "participant 置信度字段", "直接读取"), R_("M", "anyvid_ext", "检测模型", "模型输出置信度")],
    "目标物编号": [R_("R", "rsp", "participant ptcId", "直接读取"), R_("M", "anyvid_ext", "视频跟踪", "跟踪 ID")],
    "碰撞时间": [R_("R", "tsa", "运行安全评价", "已算好的 TTC(待核对列名)"), R_("R", "rsp_traj", "participant + 自车轨迹", "计算 TTC"),
             R_("M", "ch1", "前视视频", DET + " → TTC"), R_("M", "gantry", "龙门架视频", MOT + " → TTC")],
    "与目标物最小距离": [R_("R", "rsp_traj", "participant + 自车轨迹", "窗口内最小距离"), R_("M", "ch1", "前视视频", DET), R_("M", "gantry", "龙门架视频", MOT)],
    "系统风险等级": [R_("C", "anytraj", "加速度 / TTC", "按阈值规则分级"), R_("V", "anyvid", "视频", "人工分级")],
    "交通主标志": [R_("M", "ch1", "前视视频", "交通标志识别"), R_("X", "anytraj", "地图 POI", "地图匹配")],
    "交通管制信息": [R_("R", "revent", "路侧 event", "直接读取"), R_("V", "ch1", "前视视频", "人工标注"), R_("V", "gantry", "龙门架视频", "人工标注")],
    "前方信号灯识别": [R_("R", "rsig", "路侧 signal", "直接读取"), R_("L", "e9", "0920 交通灯", "映射"),
                 R_("M", "ch1", "前视视频", "信号灯检测识别"), R_("V", "gantry", "龙门架视频", "人工标注")],
    "异常路况信息": [R_("R", "revent", "路侧 event", "直接读取"), R_("V", "anyvid", "视频", "人工标注"), R_("V", "gantry", "龙门架视频", "人工标注")],
    "其他参数": [R_("R", "rsp", "participant/traffic_flow", "交通密度、参与者数量、平均车速"),
             R_("M", "ch1", "前视视频", "遮挡、眩光、施工、车流检测"), R_("M", "gantry", "龙门架视频", "车流统计"),
             R_("X", "anytraj", "地图", "曲率、坡度、车道宽度、交叉口类型")],
    "车道线几何": [R_("X", "anytraj", "高精地图/OSM", "地图读取"), R_("M", "ch1", "前视视频", "车道线检测(相对几何)")],
    "障碍物类型": [R_("R", "rsp", "participant", "类型映射"), R_("M", "ch1", "前视视频", DET), R_("M", "gantry", "龙门架视频", MOT)],
    "天气信息": [R_("L", "e9", "0920 天气", "直接映射"), R_("W", "all", "历史气象", "按日期+位置查"), R_("V", "anyvid", "视频", "人工标注")],
    "外部光线": [R_("L", "e9", "0920 光线", "直接映射"), R_("C", "all", "事件时间+位置", "日出日落推算"), R_("M", "anyvid", "视频", "画面亮度")],
    "外部温度": [R_("W", "all", "历史气象", "按日期+位置查")], "外部湿度": [R_("W", "all", "历史气象", "按日期+位置查")],
    "能见度": [R_("W", "all", "历史气象", "按日期+位置查"), R_("M", "anyvid", "视频", "图像能见度估计")],
    "路面状态": [R_("M", "ch1", "前视视频", "路面湿滑/积水识别"), R_("V", "gantry", "龙门架视频", "人工标注"), R_("W", "all", "历史气象", "按降水/气温推断湿滑、结冰")],
    "事故编号": [R_("C", "all", "event_key", "以事件编号作案例编号(非事故)")],
    "事故发生时间": [R_("C", "all", "事件时间", "接管时刻")],
    "事故地点": [R_("C", "anytraj", "轨迹经纬度", "接管地点"), R_("L", "e9", "0920 cross_name1", "路口名"), R_("V", "anyvid", "视频", "人工识别路口")],
    "事故经过描述": [R_("L", "e9", "0920 描述", "直接读取"), R_("V", "anyvid", "视频", "人工撰写"), R_("V", "gantry", "龙门架视频", "人工撰写"),
               R_("C", "anytraj", "轨迹", "按速度/加速度自动生成模板描述")],
    "事故结果": [R_("V", "ch1", "前视视频", "人工判定碰撞/急刹/险情"), R_("V", "gantry", "龙门架视频", "人工判定"), R_("C", "anytraj", "加速度", "急刹/险情按阈值")],
    "损失程度": [R_("V", "anyvid", "视频", "有无碰撞及程度"), R_("V", "gantry", "龙门架视频", "同上"), R_("C", "anytraj", "加速度", "无冲击即无损失")],
    "责任认定": [R_("V", "anyvid", "视频", "按交通规则人工判定"), R_("V", "gantry", "龙门架视频", "同上")],
    "事故前后视频": [R_("D", "ch1", "前视视频", "原始视频"), R_("D", "gantry", "龙门架视频", "原始视频"), R_("D", "anyvid", "车内视频", "原始视频")],
    "事故位置和轨迹证据": [R_("D", "anytraj", "轨迹", "原始轨迹"), R_("M", "ch1", "前视视频", VO), R_("M", "gantry", "龙门架视频", MOT)],
    "是否真实接管失败案例": [R_("V", "ch1", "前视视频+轨迹", "人工判定"), R_("V", "gantry", "龙门架视频+轨迹", "人工判定"),
                   R_("C", "anytraj", "加速度", "筛候选，需复核")],
}


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
    s = pd.Series(s)
    if s.dtype.kind == "M":
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


def probe(path):
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return dict(ok=0, fps=0, w=0, h=0, dur=0)
        n, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0, cap.get(cv2.CAP_PROP_FPS) or 0
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ok, _ = cap.read(); cap.release()
        return dict(ok=int(bool(ok)), fps=round(fps, 1), w=w, h=h, dur=round(n / fps, 1) if fps else 0)
    except Exception:
        return dict(ok=-1, fps=0, w=0, h=0, dur=0)


def colhas(colstr, pat):
    """colstr = 逗号分隔的列名；逐列匹配(使 ^$ 锚点生效)"""
    return any(re.search(pat, c.strip(), re.I) for c in str(colstr).split(",") if c.strip())


def np_info(path):
    try:
        a = np.load(path, mmap_mode="r", allow_pickle=False)
        return dict(shape=str(tuple(a.shape)), dtype=str(a.dtype))
    except Exception as e:
        return dict(shape="?", dtype=type(e).__name__)


def has_audio(path):
    """avi: strh 里有 auds；mp4/mov: 有 soun 轨。只读文件头/尾各 2MB"""
    try:
        sz = os.path.getsize(path)
        with open(path, "rb") as f:
            b = f.read(2 * 2**20)
            if sz > 4 * 2**20:
                f.seek(-2 * 2**20, 2); b += f.read()
        return int(b"auds" in b or b"soun" in b)
    except Exception:
        return -1


def json_schema(path, size):
    """小文件: 解析第一条记录的嵌套键; 大文件: 读前 2MB 用正则取键和样例值。返回 (记录结构说明, [(键, 样例)], 帧信息)"""
    head = open(path, "rb").read(2 * 1024 * 1024).decode("utf-8", "replace")
    keys = {}
    for k, v in re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*("[^"]{0,200}"|-?\d+(?:\.\d+)?|true|false|null|\[|\{)', head):
        if k not in keys:
            keys[k] = v[:40]
    shape = ""
    if size <= 20 * 2**20:
        try:
            obj = json.load(open(path, encoding="utf-8"))
            if isinstance(obj, list):
                shape = "list[%d] of %s" % (len(obj), type(obj[0]).__name__ if obj else "-")
            elif isinstance(obj, dict):
                shape = "dict{%s}" % ",".join(list(obj)[:8])
        except Exception as e:
            shape = "解析失败 %s" % type(e).__name__
    ts = sorted(set(int(x) for x in re.findall(r'"timestamp"\s*:\s*(\d{13})', head)))
    fr = ""
    if len(ts) > 2:
        d = np.diff(ts)
        fr = "timestamp 帧数(前2MB)=%d 间隔中位=%dms" % (len(ts), int(np.median(d)))
    return shape, list(keys.items()), fr


def main():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    out("=== %s %s  check=%s  %s ===" % (NAME, VERSION, selfcheck(), time.strftime("%Y-%m-%d %H:%M")))
    U = pd.read_csv(IN12 + r"\事件资产表.csv", dtype={"vin": str}, encoding="utf-8-sig")
    U25 = pd.read_csv(IN12 + r"\事件资产表_2025.csv", dtype={"vin": str}, encoding="utf-8-sig")
    U["表"] = "主表"; U25["表"] = "2025"
    E = pd.concat([U, U25], ignore_index=True)
    E["sec"] = to_sec(pd.to_datetime(E["事件时间"]))
    E["等级"] = np.where(E["表"] == "2025", "2025-" + E["类别"].str[0], E["类别"].str[0])
    for c in list(RS_COLS.values()) + ["路侧_龙门架(同VIN)", "路侧_同时段龙门架路口", "路侧_龙门架路口(同VIN)", "轨迹_原始文件", "NPY文件"]:
        if c not in E.columns:
            E[c] = ""
        E[c] = E[c].fillna("").astype(str)
    for c in ("ch1_可读", "ch2_可读", "ch3_可读"):
        E[c] = pd.to_numeric(E.get(c, 0), errors="coerce").fillna(0)
    for c in ("有表格轨迹", "有NPY轨迹", "在0920"):
        E[c] = E[c].astype(str).str.lower().eq("true")
    out("资产表: 主表=%d  2025=%d" % (len(U), len(U25)))

    # ================= 1. 扫盘: 龙门架 / 路侧 json / 运行安全评价 / 地图 =================
    gant, rsj, tsa, maps, PDNPY = [], [], [], [], []
    rs_conf = False
    for r in (sys.argv[1:] or ROOTS):
        if not os.path.exists(r):
            continue
        for d, n, sz in walk(r):
            low = n.lower(); ext = os.path.splitext(low)[1]
            g = RE_GV.match(n)
            if g and ext == ".mp4":
                cm = RE_CASE.search(d.upper())
                gant.append(dict(dir=d, name=n, size=sz, cam=g.group(2), s=g.group(3), e=g.group(4),
                                 case=os.path.basename(d), case_vin=cm.group(1) if cm else "",
                                 case_t=(cm.group(2) + " " + cm.group(3)) if cm else ""))
            elif RE_RS.match(n):
                p = RE_RS.match(n)
                rsj.append(dict(dir=d, name=n, size=sz, typ=p.group(1).lower(), s=p.group(2), e=p.group(3)))
            elif "运行安全评价" in d and ext in (".csv", ".xlsx"):
                tsa.append(dict(dir=d, name=n, size=sz, sub=d.split("运行安全评价")[-1].strip("\\/").split("\\")[0].split("/")[0]))
            elif ext == ".npy" and "processing_data" in d.lower():
                PDNPY.append(os.path.join(d, n))
            elif ext in MAP_EXT:
                maps.append(dict(dir=d, name=n, size=sz, ext=ext))
    G, P, T, M = pd.DataFrame(gant), pd.DataFrame(rsj), pd.DataFrame(tsa), pd.DataFrame(maps)
    out("")
    out("[1] 扫盘 %.0fs: 龙门架mp4=%d  路侧json=%d  运行安全评价表=%d  地图矢量文件=%d" % (time.time() - t0, len(G), len(P), len(T), len(M)))

    # ---- 1a 龙门架视频 ----
    out("")
    out("################ 1a 龙门架视频：长什么样 ################")
    if len(G):
        G["path"] = [os.path.join(a, b) for a, b in zip(G.dir, G.name)]
        G["inter"] = G.cam.str.extract(r"^(.+?路-.+?路)", expand=False).fillna(G.cam)
        G["camid"] = G.cam.str.replace(r"^(.+?路-.+?路)", "", regex=True).str.strip("_- ")
        G["s0"] = to_sec(pd.to_datetime(G.s, format="%Y%m%d%H%M%S", errors="coerce"))
        G["s1"] = to_sec(pd.to_datetime(G.e, format="%Y%m%d%H%M%S", errors="coerce"))
        G["case_sec"] = to_sec(pd.to_datetime(G.case_t, format="%Y-%m-%d %H%M%S", errors="coerce"))
        G = G.sort_values("size").drop_duplicates(["name", "size"], keep="last")        # 同名同大小的拷贝只算一次
        pr = [probe(p) for p in G.path]
        G = pd.concat([G.reset_index(drop=True), pd.DataFrame(pr)], axis=1)
        G.drop(columns=["dir"]).to_csv(OUT_DIR + r"\gantry_videos.csv", index=False, encoding="utf-8-sig")
        cases = G.groupby("dir").agg(case=("case", "first"), vin=("case_vin", "first"), t=("case_t", "first"), inter=("inter", "first"),
                                     n=("name", "size"), cams=("camid", "nunique"), dur=("dur", "sum")).reset_index()
        out("  去重后 mp4=%d  可读=%d  案例目录=%d(其中目录名带 VIN=%d)  路口=%d  时间 %s ~ %s" % (
            len(G), (G.ok == 1).sum(), len(cases), (cases.vin != "").sum(), G.inter.nunique(),
            pd.to_datetime(G.s0.min(), unit="s"), pd.to_datetime(G.s1.max(), unit="s")))
        out("  分辨率: " + "  ".join("%dx%d:%d" % (a, b, n) for (a, b), n in G.groupby(["w", "h"]).size().sort_values(ascending=False).head(4).items()) +
            " ; 帧率: " + "  ".join("%g:%d" % (a, n) for a, n in G.fps.value_counts().head(3).items()) +
            " ; 单段时长(s) 中位=%.0f 最短=%.0f 最长=%.0f ; 总时长=%.1fh" % (G.dur.median(), G.dur.min(), G.dur.max(), G.dur.sum() / 3600))
        out("  每个案例: mp4 中位=%d 个, 相机 中位=%d 个, 视频合计中位=%.0fs" % (cases.n.median(), cases.cams.median(), cases.dur.median()))
        out("  文件名样例: " + " | ".join(G.name.head(3)))
        out("  按路口(案例数/mp4数):")
        for it, g in G.groupby("inter"):
            out("     %-22s 案例=%3d  mp4=%4d  %s~%s" % (it[:22], g.dir.nunique(), len(g), str(pd.to_datetime(g.s0.min(), unit="s"))[:10], str(pd.to_datetime(g.s1.max(), unit="s"))[:10]))
        # 案例 -> 事件
        ek = E[E["路侧_龙门架(同VIN)"] != ""]
        hit = set()
        for p in ek["路侧_龙门架(同VIN)"]:
            hit.update(os.path.dirname(x) for x in p.split(";") if x)
        cases["对上事件"] = cases.dir.isin(hit)
        vins_all = set(E.vin)
        cases["VIN在事件表"] = cases.vin.isin(vins_all)
        out("  案例目录对上资产表事件=%d / %d ; 没对上的 %d 个中: VIN 不在任何事件里=%d, VIN 在但时间对不上=%d, 目录名无 VIN=%d" % (
            cases["对上事件"].sum(), len(cases), (~cases["对上事件"]).sum(),
            ((~cases["对上事件"]) & (cases.vin != "") & ~cases["VIN在事件表"]).sum(),
            ((~cases["对上事件"]) & cases["VIN在事件表"]).sum(), ((~cases["对上事件"]) & (cases.vin == "")).sum()))
        cases.drop(columns=["dir"]).to_csv(OUT_DIR + r"\gantry_cases.csv", index=False, encoding="utf-8-sig")

    # ---- 1b 路侧 json ----
    out("")
    out("################ 1b 路侧 json：长什么样 ################")
    if len(P):
        P["path"] = [os.path.join(a, b) for a, b in zip(P.dir, P.name)]
        P["s0"] = to_sec(pd.to_datetime(P.s, format="%Y%m%d%H%M%S", errors="coerce"))
        P["s1"] = to_sec(pd.to_datetime(P.e, format="%Y%m%d%H%M%S", errors="coerce"))
        P["year"] = pd.to_datetime(P.s0, unit="s").dt.year
        P = P.drop_duplicates(["name", "size"])
        P.drop(columns=["dir"]).to_csv(OUT_DIR + r"\roadside_json.csv", index=False, encoding="utf-8-sig")
        out("  类型 x 年份(文件数 / GB / 覆盖小时):")
        for (ty, y), g in P.groupby(["typ", "year"]):
            out("     %-13s %d  文件=%4d  %7.2f GB  %6.1f h  目录=%d  %s ~ %s" % (ty, y, len(g), g["size"].sum() / 2**30, (g.s1 - g.s0).sum() / 3600,
                g.dir.nunique(), str(pd.to_datetime(g.s0.min(), unit="s"))[:16], str(pd.to_datetime(g.s1.max(), unit="s"))[:16]))
        for ty, g in P.groupby("typ"):
            smp = g.sort_values("size").iloc[len(g) // 2 if len(g) < 3 else 1]
            shape, keys, fr = json_schema(smp.path, smp["size"])
            out("  [%s] 样例文件 %s (%.1f MB)  结构=%s  %s" % (ty, smp["name"], smp["size"] / 2**20, shape, fr))
            out("     字段(%d): %s" % (len(keys), "  ".join("%s=%s" % (k, v) for k, v in keys[:40])))
            if ty == "participant":
                head = open(smp.path, "rb").read(4 * 1024 * 1024).decode("utf-8", "replace")
                pt = pd.Series(re.findall(r'"ptcType"\s*:\s*(\d+)', head)).value_counts()
                ids = len(set(re.findall(r'"ptcId"\s*:\s*"?(\w+)', head)))
                src = pd.Series(re.findall(r'"dataSource"\s*:\s*"?(\w+)', head)).value_counts()
                out("     前4MB: ptcType 分布 %s ; 不同 ptcId=%d ; dataSource %s" % (
                    dict(pt.head(6)), ids, dict(src.head(4))))
                conf = [k for k, _ in keys if re.search(r"conf|prob", k, re.I)]
                rs_conf = bool(conf)
                out("     置信度类字段: %s" % (conf or "无"))

    # ---- 1c 运行安全评价 / 地图 ----
    out("")
    out("################ 1c 运行安全评价 / 地图矢量 ################")
    if len(T):
        T["path"] = [os.path.join(a, b) for a, b in zip(T.dir, T.name)]
        for sub, g in T.groupby("sub"):
            smp = g.sort_values("size").iloc[len(g) // 2]
            try:
                h = pd.read_csv(smp.path, nrows=2, encoding="utf-8-sig") if smp.path.lower().endswith(".csv") else pd.read_excel(smp.path, nrows=2)
                cols = ",".join(map(str, h.columns))[:300]
            except Exception as e:
                cols = "读失败 %s" % type(e).__name__
            out("  %-14s 文件=%5d  %.2f GB  列: %s" % (sub[:14], len(g), g["size"].sum() / 2**30, cols))
    if len(M):
        out("  地图矢量: " + "  ".join("%s:%d" % (a, b) for a, b in M.ext.value_counts().items()) + "  目录: " +
            "  ".join("%s:%d" % (a[-40:], b) for a, b in M.dir.value_counts().head(4).items()))

    # ---- 1d 自车视频是否带音轨(接管提示音) ----
    out("")
    out("################ 1d 自车视频音轨 ################")
    for c in "123":
        col = "ch%s_原始路径" % c
        E["ch%s_audio" % c] = False
        if col in E.columns:
            ps = E[col].fillna("").astype(str).str.split(";").str[0]
            au = {p: has_audio(p) for p in set(ps) if p and os.path.exists(p)}
            E["ch%s_audio" % c] = ps.map(lambda p: au.get(p, 0) == 1)
            out("  ch%s: 检查文件=%d  有音轨=%d  无=%d  读失败=%d" % (c, len(au), sum(v == 1 for v in au.values()),
                sum(v == 0 for v in au.values()), sum(v == -1 for v in au.values())))

    # ================= 2. 事件层面: 各等级有哪些路侧 =================
    out("")
    out("################ 2 各等级事件的路侧数据 ################")
    E["有龙门架(同VIN)"] = E["路侧_龙门架(同VIN)"] != ""
    E["同时段有龙门架(任意车)"] = E["路侧_同时段龙门架路口"].str.strip().ne("") & E["路侧_同时段龙门架路口"].ne("nan")
    for k, c in RS_COLS.items():
        E["json_" + k] = E[c].str.strip().ne("") & E[c].ne("nan")
    E["有json"] = E[["json_" + k for k in RS_COLS]].any(axis=1)
    out("  等级    事件  龙门架同VIN  同时段有龙门架  json任一  participant  vehicle_track  traffic_flow  signal  event")
    for lv, g in E.groupby("等级"):
        out("  %-7s %5d  %10d  %13d  %8d  %11d  %13d  %12d  %6d  %5d" % (lv, len(g), g["有龙门架(同VIN)"].sum(), g["同时段有龙门架(任意车)"].sum(),
            g["有json"].sum(), *[g["json_" + k].sum() for k in RS_COLS]))
    rs = E[E["有龙门架(同VIN)"] | E["有json"]].sort_values(["表", "事件时间"])
    rs[["event_key", "表", "等级", "事件时间", "有龙门架(同VIN)", "路侧_龙门架路口(同VIN)", "有json"] + ["json_" + k for k in RS_COLS] +
       ["路侧_龙门架(同VIN)", RS_COLS["participant"]]].to_csv(OUT_DIR + r"\events_roadside.csv", index=False, encoding="utf-8-sig")
    out("  有路侧的事件=%d (清单: events_roadside.csv)" % len(rs))
    for _, r in rs.head(60).iterrows():
        out("    %s | %s | %-6s | 龙门架:%s | json:%s" % (r["vin"][-6:], str(r["事件时间"])[:19], r["等级"],
            (r["路侧_龙门架路口(同VIN)"] or "有")[:24] if r["有龙门架(同VIN)"] else "-",
            ",".join(k for k in RS_COLS if r["json_" + k]) or "-"))

    # ================= 3. 现有数据源列名 =================
    out("")
    out("################ 3 现有数据源的列名 ################")
    cat = pd.read_csv(CATALOG, dtype=str, keep_default_na=False)
    cat["fname"] = cat.path.str.replace("/", "\\").str.split("\\").str[-1]
    colmap = dict(zip(cat.path, cat.cols))
    groups = [("local_vehicle_info", r"local_vehicle_info"), ("all927", r"all927"), ("dis_joined1/2/3", r"dis_joined"),
              ("switch 平台表", r"switch"), ("运行安全评价 veh_origin", r"veh_origin"), ("运行安全评价 con_res", r"con_res"),
              ("0920", r"脱离事件汇总"), ("add_type/all_events(稀疏)", r"add_type|all_events_")]
    for lab, pat in groups:
        g = cat[cat.path.str.contains(pat, case=False, regex=True)]
        if not len(g):
            out("  %-24s 未找到" % lab); continue
        sig = g.cols.value_counts()
        out("  %-24s 文件=%d 表头种类=%d" % (lab, len(g), len(sig)))
        for s, n in sig.head(2).items():
            out("     (%d) %s" % (n, s[:400]))
    used = set(E.loc[E["有表格轨迹"], "轨迹_原始文件"])
    E["_cols"] = E["轨迹_原始文件"].map(lambda p: colmap.get(p, "")).str.lower()
    out("  事件所用表格轨迹文件=%d, 其中含 → " % len(used) + "  ".join(
        "%s:%d" % (k, sum(colhas(colmap.get(p, ""), v) for p in used)) for k, v in COLS.items()))

    # ================= 4. switch 平台表 + processing_data 表：按 VIN+时间匹配事件，合并可用列 =================
    win = {v: np.sort(g.sec.values.astype(np.int64)) for v, g in E.groupby("vin")}
    TCOL = ("time", "position_time", "positiontime", "position_time_sql", "dis_engage_time", "disengage_time", "gps_time",
            "timestamp", "switch_time", "create_time")

    def match_tables(files, extra=None, tol=60, tag=""):
        """读每个表的 vin/时间(和 extra 列)，按 0/±8h 取命中最多的偏移，返回 (命中表 DataFrame, 读失败数, 全表 extra 统计, 行数)"""
        hits, nerr, stat, nrows = [], 0, {}, 0
        for k, p in enumerate(files, 1):
            try:
                enc = "utf-8-sig"
                if p.lower().endswith(".csv"):
                    try:
                        hdr = pd.read_csv(p, nrows=0, encoding=enc).columns
                        pd.read_csv(p, nrows=2000, encoding=enc, dtype=str)
                    except UnicodeDecodeError:
                        enc = "gbk"; hdr = pd.read_csv(p, nrows=0, encoding=enc).columns
                else:
                    hdr = pd.read_excel(p, nrows=0).columns
                cv = next((c for c in hdr if str(c).strip().lower() in ("vin", "vin_x", "t2.vin")), None)
                ct = next((c for k2 in TCOL for c in hdr if str(c).strip().lower() == k2), None)
                ce = [c for c in hdr if extra and str(c).strip().lower() in extra]
                if not (cv and ct):
                    continue
                it = pd.read_csv(p, usecols=[cv, ct] + ce, dtype=str, chunksize=1_000_000, encoding=enc, encoding_errors="replace",
                                 on_bad_lines="skip") if p.lower().endswith(".csv") else [pd.read_excel(p, usecols=[cv, ct] + ce, dtype=str)]
                for ch in it:
                    nrows += len(ch)
                    for c in ce:
                        vc = ch[c].dropna().astype(str).str.strip()
                        for a, b in vc[vc != ""].value_counts().items():
                            stat.setdefault(str(c).lower(), {})[a] = stat.setdefault(str(c).lower(), {}).get(a, 0) + b
                    ch = ch[ch[cv].astype(str).str.upper().str.strip().isin(win.keys())]
                    if not len(ch):
                        continue
                    vv = ch[cv].astype(str).str.upper().str.strip().values
                    s = to_sec(ch[ct]).values
                    ex = ch[ce[0]].astype(str).values if ce else np.array([""] * len(ch))
                    for sh in SHIFTS:
                        tt = s + sh
                        for v in np.unique(vv):
                            idx = np.where(vv == v)[0]; a = win[v]; x = tt[idx]
                            ok0 = ~np.isnan(x)
                            idx, x = idx[ok0], x[ok0]
                            if not len(x):
                                continue
                            i = np.clip(np.searchsorted(a, x), 0, len(a) - 1)
                            i2 = np.clip(i - 1, 0, len(a) - 1)
                            near = np.where(np.abs(a[i] - x) <= np.abs(a[i2] - x), a[i], a[i2])
                            ok = np.abs(near - x) <= tol
                            for j in np.where(ok)[0]:
                                hits.append((v, int(near[j]), sh, p, ex[idx[j]], abs(near[j] - x[j])))
            except Exception as e:
                nerr += 1
                if nerr <= 3:
                    out("  读失败 %s %s" % (os.path.basename(p)[:40], type(e).__name__))
            if k % 50 == 0:
                print("  ... %s %d/%d %.0fs" % (tag, k, len(files), time.time() - t0))
        H = pd.DataFrame(hits, columns=["vin", "sec", "shift", "file", "extra", "dt"])
        if len(H):   # 每个文件取命中最多的偏移
            best = H.groupby(["file", "shift"]).size().reset_index(name="n").sort_values("n").drop_duplicates("file", keep="last")
            H = H.merge(best[["file", "shift"]], on=["file", "shift"]).sort_values("dt")
        return H, nerr, stat, nrows

    out("")
    out("################ 4 switch 平台表 ################")
    sw_files = cat[cat.cols.str.contains("drive_mode_switch|manual_reason", case=False) & cat.path.str.lower().str.endswith(".csv")] \
        .drop_duplicates(["fname", "size_mb"]).path.tolist()
    HS, nerr, st, nrow = match_tables(sw_files, extra=("manual_reason", "drive_mode_switch"), tag="switch")
    mr, dm = st.get("manual_reason", {}), st.get("drive_mode_switch", {})
    out("  文件=%d 读失败=%d 行=%d ; 全表 manual_reason 非空=%d ; drive_mode_switch 取值: %s" % (
        len(sw_files), nerr, nrow, sum(mr.values()), "  ".join("%s:%d" % (a, b) for a, b in sorted(dm.items(), key=lambda x: -x[1])[:5])))
    if mr:
        out("  manual_reason 取值(前10): " + "  ".join("%s:%d" % (a[:20], b) for a, b in sorted(mr.items(), key=lambda x: -x[1])[:10]))
    E["sw"] = False; E["swreason_ok"] = False; E["_swcols"] = ""
    if len(HS):
        g1 = HS.drop_duplicates(["vin", "sec"])
        key = set(zip(g1.vin, g1.sec))
        E["sw"] = [(v, int(s)) in key for v, s in zip(E.vin, E.sec)]
        rs_ = HS[HS.extra.str.strip().replace({"nan": ""}).ne("")].drop_duplicates(["vin", "sec"])
        key2 = set(zip(rs_.vin, rs_.sec))
        E["swreason_ok"] = [(v, int(s)) in key2 for v, s in zip(E.vin, E.sec)]
        out("  匹配事件=%d  其中 manual_reason 非空=%d ; 按等级: %s" % (E.sw.sum(), E.swreason_ok.sum(),
            "  ".join("%s:%d/%d" % (lv, g.sw.sum(), len(g)) for lv, g in E.groupby("等级"))))

    out("")
    out("################ 4b processing_data：表头与事件匹配 ################")
    pdt = cat[cat.path.str.contains("processing_data", case=False)].drop_duplicates(["fname", "size_mb"])
    out("  processing_data 下表格=%d  表头种类=%d" % (len(pdt), pdt.cols.nunique()))
    for sgn, n in pdt.cols.value_counts().head(8).items():
        d0 = pdt[pdt.cols == sgn].path.iloc[0]
        out("   (%d) %s" % (n, sgn[:300]))
        out("        例: %s" % d0[-90:])
    npys = [dict(path=p, **np_info(p)) for p in PDNPY]
    if npys:
        NP = pd.DataFrame(npys)
        out("  processing_data 下 npy=%d ; 形状(前8): %s" % (len(NP), "  ".join("%s%s" % (os.path.basename(a)[:28], b) for a, b in zip(NP.path.head(8), NP["shape"].head(8)))))
        NP.to_csv(OUT_DIR + r"\processing_data_npy.csv", index=False, encoding="utf-8-sig")
    HP, nerr, _, nrow = match_tables(pdt.path.tolist(), tol=30, tag="processing_data")
    pdcols = {}
    if len(HP):
        for (v, s_), g in HP.groupby(["vin", "sec"]):
            pdcols[(v, s_)] = ",".join(colmap.get(f, "") for f in g.file.unique())
    E["_pdcols"] = [pdcols.get((v, int(s)), "") for v, s in zip(E.vin, E.sec)]
    E["有processing_data表"] = E["_pdcols"] != ""
    out("  读失败=%d 行=%d ; 匹配事件(±30s)=%d ; 按等级: %s" % (nerr, nrow, E["有processing_data表"].sum(),
        "  ".join("%s:%d/%d" % (lv, g["有processing_data表"].sum(), len(g)) for lv, g in E.groupby("等级"))))
    if len(HP):
        out("  命中最多的 processing_data 表: " + "  ".join("%s:%d" % (os.path.basename(a)[:30], b) for a, b in
            HP.drop_duplicates(["vin", "sec", "file"]).file.value_counts().head(5).items()))
    E["_cols"] = (E["_cols"] + "," + E["_pdcols"]).str.lower()
    out("  合并 processing_data 后，事件可用列含 → " + "  ".join("%s:%d" % (k, E["_cols"].map(lambda x: colhas(x, v)).sum()) for k, v in COLS.items()))

    # ================= 5. VIN 是否有连续车端导出(运行里程/时长) =================
    lvi = cat[cat.path.str.contains("local_vehicle_info", case=False) & cat.path.str.lower().str.endswith(".csv")].drop_duplicates(["fname", "size_mb"]).path.tolist()
    lv_vins = {}
    for p in lvi:
        try:
            hdr = pd.read_csv(p, nrows=0, encoding="utf-8-sig").columns
            cv = next((c for c in hdr if c.lower() == "vin"), None)
            cd = next((c for c in hdr if re.search(COLS["drive_mode"], c, re.I)), None)
            if not cv:
                continue
            for ch in pd.read_csv(p, usecols=[c for c in (cv, cd) if c], dtype=str, chunksize=2_000_000, encoding="utf-8-sig", on_bad_lines="skip"):
                for v, n in ch[cv].value_counts().items():
                    a = lv_vins.setdefault(v, [0, 0]); a[0] += n
                if cd:
                    for v, n in ch[ch[cd].astype(str).str.strip().isin(["1", "1.0"])][cv].value_counts().items():
                        lv_vins[v][1] += n
        except Exception:
            pass
    E["lvi"] = E.vin.isin(lv_vins.keys())
    out("")
    out("[5] local_vehicle_info: 文件=%d VIN=%d 总点=%d 自动驾驶点=%d ; 事件的 VIN 在其中: " % (
        len(lvi), len(lv_vins), sum(a[0] for a in lv_vins.values()), sum(a[1] for a in lv_vins.values())) +
        "  ".join("%s:%d/%d" % (lv, g.lvi.sum(), len(g)) for lv, g in E.groupby("等级")))
    pd.DataFrame([(v, a[0], a[1]) for v, a in lv_vins.items()], columns=["vin", "点数", "自动驾驶点数"]).to_csv(
        OUT_DIR + r"\lvi_exposure.csv", index=False, encoding="utf-8-sig")

    # ================= 6. 字段映射与各等级覆盖 =================
    has = lambda k: E["_cols"].map(lambda x: colhas(x, COLS[k]))
    anytraj = E["有表格轨迹"] | E["有NPY轨迹"]
    rsp = E["json_participant"]
    tsa_ok = bool(len(T)) and bool(T.name.str.contains("vehicle_end|ttc", case=False).any())
    COND = {
        "all": pd.Series(True, index=E.index), "e9": E["在0920"], "traj": E["有表格轨迹"], "npy": E["有NPY轨迹"], "anytraj": anytraj,
        "dm_or_npy": (E["有表格轨迹"] & has("drive_mode")) | E["有NPY轨迹"] | E["在0920"],
        "anytraj_acc": anytraj,
        "ch1": E["ch1_可读"] > 0, "ch2": E["ch2_可读"] > 0, "ch3": E["ch3_可读"] > 0,
        "ch2a": (E["ch2_可读"] > 0) & E["ch2_audio"],
        "anyvid": (E["ch1_可读"] + E["ch2_可读"] + E["ch3_可读"]) > 0,
        "anyvid_ext": ((E["ch1_可读"] > 0) | E["有龙门架(同VIN)"]),
        "anytraj_or_e9": anytraj | E["在0920"],
        "ch1_ch2": (E["ch1_可读"] > 0) & ((E["ch2_可读"] > 0) | (E["ch3_可读"] > 0)),
        "gantry": E["有龙门架(同VIN)"], "rsp": rsp, "rsp_traj": rsp & anytraj, "rsp_conf": rsp & bool(rs_conf),
        "rsig": E["json_signal"], "revent": E["json_event"], "tsa": pd.Series(bool(tsa_ok), index=E.index) & E["轨迹_原始文件"].str.contains("运行安全评价", regex=False),
        "sw": E["sw"], "swreason": E["swreason_ok"], "lvi": E["lvi"],
    }
    for k in COLS:
        COND["col:" + k] = has(k)
    rows, per = [], {}
    for mod, f, pri in SPEC:
        rules = RULES[f]
        act = pd.Series("N", index=E.index); src = pd.Series("-", index=E.index); done = pd.Series(False, index=E.index)
        for a, cnd, s, how in rules:
            m = COND[cnd] & ~done
            act[m] = a; src[m] = s; done |= m
        per[f] = (act, src)
        rows.append(dict(模块=mod, 字段=f, 优先级=pri,
                         规定动作顺序=" → ".join("%s %s" % (a, ACT[a]) for a, *_ in rules),
                         数据来源与做法=" ; ".join("%s: %s(%s)" % (ACT[a], s, h) for a, _, s, h in rules)))
    MAP = pd.DataFrame(rows)
    levels = sorted(E["等级"].unique(), key=lambda x: (x.startswith("2025"), x))
    tables = {}
    for lv in levels:
        idx = E.index[E["等级"] == lv]
        recs = []
        for mod, f, pri in SPEC:
            act, src = per[f]
            vc = act[idx].value_counts()
            main_a = vc.index[0]
            recs.append(dict(模块=mod, 字段=f, 优先级=pri, 主要动作=ACT[main_a], 主要来源=src[idx][act[idx] == main_a].iloc[0],
                             现有即可=int(act[idx].isin(HAVE).sum()), 模型恢复=int((act[idx] == "M").sum()), 人工审计=int((act[idx] == "V").sum()),
                             外部地图=int((act[idx] == "X").sum()), 外部气象=int((act[idx] == "W").sum()), 无法补充=int((act[idx] == "N").sum()),
                             可覆盖率=round(act[idx].isin(ABLE).mean(), 3), 事件数=len(idx)))
        tables[lv] = pd.DataFrame(recs)
    xl = OUT_DIR + r"\字段映射表.xlsx"
    try:
        with pd.ExcelWriter(xl) as w:
            MAP.to_excel(w, sheet_name="字段与规定动作", index=False)
            for lv, t in tables.items():
                t.to_excel(w, sheet_name=("等级_" + lv)[:31], index=False)
    except Exception as e:
        xl = OUT_DIR + r"\字段映射表_%s.xlsx" % time.strftime("%H%M%S")
        with pd.ExcelWriter(xl) as w:
            MAP.to_excel(w, sheet_name="字段与规定动作", index=False)
            for lv, t in tables.items():
                t.to_excel(w, sheet_name=("等级_" + lv)[:31], index=False)
        out("xlsx 被占用(%r)，另存 %s" % (e, xl))
    MAP.to_csv(OUT_DIR + r"\field_rules.csv", index=False, encoding="utf-8-sig")
    pd.concat([t.assign(等级=lv) for lv, t in tables.items()]).to_csv(OUT_DIR + r"\field_coverage.csv", index=False, encoding="utf-8-sig")

    out("")
    out("################ 6 各等级: 110 个字段按主要动作计数 (P0 共 %d 个) ################" % sum(p == "P0" for _, _, p in SPEC))
    out("  等级     事件 | P0: 现有 模型 人工 地图 气象 无法 | 全部: 现有 模型 人工 地图 气象 无法")
    for lv, t in tables.items():
        c0 = t[t["优先级"] == "P0"]["主要动作"].value_counts(); ca = t["主要动作"].value_counts()
        cnt = lambda c: (sum(c.get(ACT[a], 0) for a in HAVE),) + tuple(c.get(ACT[a], 0) for a in ("M", "V", "X", "W", "N"))
        out("  %-7s %5d | %8d %4d %4d %4d %4d %4d | %10d %4d %4d %4d %4d %4d" % ((lv, t["事件数"].iloc[0]) + cnt(c0) + cnt(ca)))
    out("")
    out("  P0 字段在各等级的主要动作与可覆盖率(D/C/L/R=现有, M=模型, V=人工, X=地图, W=气象, N=无法):")
    inv = {v: k for k, v in ACT.items()}
    hdr = "  %-24s" % "字段" + "".join("%-8s" % lv for lv in levels)
    out(hdr)
    ti = {lv: t.set_index("字段") for lv, t in tables.items()}
    for mod, f, pri in SPEC:
        if pri != "P0":
            continue
        out("  %-24s" % f[:12] + "".join("%-8s" % ("%s%3.0f%%" % (inv[ti[lv].at[f, "主要动作"]], 100 * ti[lv].at[f, "可覆盖率"])) for lv in levels))
    out("")
    out("  输出: %s ; field_rules.csv ; field_coverage.csv ; gantry_videos.csv ; gantry_cases.csv ; roadside_json.csv ; events_roadside.csv" % xl)
    open(OUT_DIR + r"\summary.txt", "w", encoding="utf-8").write("\n".join(L))
    out("=== END %s %s  用时%.0fs ===" % (NAME, VERSION, time.time() - t0))


if __name__ == "__main__":
    main()
