# Round 9：路侧统计、字段映射与补充方案（14 v3 结果 + 15 音轨检测，聚合数，不含 VIN）

- 龙门架：337 个 mp4、105 个案例、17 个路口，时间 2024-04 ~ 2025-03；25 个案例对上事件，67 个目录名无 VIN。
- 路侧 JSON：2024 年仅 2 天，含 5 类 + vehicle_track（自车 CAN 类字段）；2025 年只有 participant，52.5 h，137 GB。
- 有路侧数据的事件 42 个：E 22、A 1、H 1（龙门架）；2025-E 15、2025-H 1、B 2（participant）。
- switch 平台表 5000 万行，manual_reason 只有"手动人工驾驶"；能匹配 2566 个事件。
- 轨迹表都没有方向盘、制动、油门、档位列；processing_data 的 _local_road_segment 有限速和车道数。
- 音轨为 PCM 8 kHz；只有模式切换时的一声约 2 kHz 提示音，无请求序列 → 接管请求判为否（安全员主动接管）。
- 报告：docs/fields_report.md（规定动作 D/C/L/R/M/V/X/W/N，110 个字段的映射总表，各等级补充表）。
