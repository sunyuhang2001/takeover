# 第 1 轮回传（2026-09-30，00_probe + 01_scan_files v1）

只记聚合结论，不记 VIN 和坐标明细。

## 环境

- **Python**：`D:\miniconda3\envs\process\python.exe`，版本 3.10.9。
- **已装的包**：pandas 1.5.3、numpy 1.23.5、openpyxl 3.0.10、cv2 4.7.0、matplotlib 3.7.0、psutil、chardet。
- **没装的**：xlrd、xlsxwriter、ffprobe。
- **硬件**：内存 16 GB，8 核。C 盘 499 GB，D 盘 800 GB（已用 486 GB）。
- **粘贴通道**：中文和缩进都正常，校验码一致。

## 全盘文件（C 盘和 D 盘，125,267 个文件，449 GB，扫描用时 3 秒）

| 类别 | 文件数 | GB | 修改时间 | 主要位置 |
|---|---|---|---|---|
| participant json | 1,126 | 229.5 | 2024-01 ~ 2025-05 | `D:\code`（868 个）、`D:\250408提供最新`（179 个）、`C:\Users\...\Desktop\250315-0709`（28 个）、`D:\新建文件夹`（18 个） |
| 表格 | 9,601 | 114.8 | | `D:\运行安全评价`（3,405 个）、`D:\andy_workspace`（2,548 个）、`D:\code`（2,178 个） |
| 自车视频 | 1,424 | 29.0 | 2024-01 ~ 2024-07 | `video2` 406、`video0719` 344、`video5` 255、`VIDEO` 141、`video4` 118、`堡垒机数据筛选` 105（是拷贝）、`video3` 42、`D:\code` 8、`D:\case` 3、D 盘根目录 2 |
| 龙门架视频 | 394 | 21.3 | 2024-07 ~ 2025-04 | `D:\code`（178 个）、`D:\新建文件夹`（159 个）、`D:\chenming_backup`（57 个） |

- 被判为"未识别视频"的主要是 `.ts` 代码文件（TypeScript），01 v2 已经修正。
- D 盘还有这些目录值得关注：`250408提供最新`、`case`、`case关系审计结果`、`ArcGIS`、`DBeaver`。
- D 盘根目录下有 2 分钟长的自车视频片段。

## 0920 表（`脱离事件汇总-0920`，sheet 名为 `0401-0409`）

- 约 1,925 行，时间一直延续到 2024-09。
- 列：`disengage_time`、`vin`、`acc_long_min`、`acc_lat_abs_max`、`acc_long`、`acc_lat`、`acc_lat_abs_m…`、`有效视频`、`是否紧急接管`、`道路类型`、`交通灯`、`天气`、`光线`、`主车行为`、`目标物`、`目标物行为`、`与目标物相对关系`、`描述`、`distance`、`cross_name1`。
- `有效视频`（是/否）很可能就是前人筛掉视频的依据；`cross_name1` 是路口名。

## 路侧数据（RoadsideData 样例，2024-01-02）

- **文件组织**：每 5 分钟一组文件，包括 `participant_`、`vehicle_track_`、`traffic_flow_`、`signal_`、`event_`、`camera_url_` 等 json，外加一个 mp4。
- **participant 的字段**：`timestamp`（毫秒 epoch）、`ptcId`、`ptcType`、`speed`、`heading`、`ptcPosLat`/`ptcPosLon`（整数，单位 1e-7 度）、`mapLocationLinkName`（如"墨玉南路"、"博园路-墨玉南路"）、`mapLocationNodeId`、`ptcSizeWidth`/`Length`/`Height`、`vehicleType`、`polygon`、`mapDeviceId`、`mapNodeId`、`sceneType`、`dataSource` 等。
- **文件格式**：单个文件最大约 347 MB，整个文件是一行 JSON 数组。所以只能流式读取或只读开头做抽样，不能整体加载。

## 前人 README

- 分四步：`vin_scan.py` → `vin_time_refine.py` → `vin_channel_coordinate.py` → `export_disengagement_trajectory_data.py`。
- 每一步各有一个 README_*.md 说明。
