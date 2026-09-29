# 堡垒机脚本

按编号顺序运行，只用 Python 标准库，不依赖 pandas。

## 怎么用

1. 在堡垒机上新建目录 `D:\takeover_audit\scripts\`。
2. 用 VS Code 新建同名 .py 文件，把脚本全文粘贴进去，**以 UTF-8 编码保存**。
3. 在终端运行：`D:\miniconda3\python.exe 00_probe.py`（如果 python 已经在 PATH 里，直接 `python 00_probe.py` 也行）。
4. 对整屏输出截图发回来。结果文件也会写在 `D:\takeover_audit\<步骤>\` 下。

## 粘贴校验

运行后输出第一行会显示 `check=xxxxxxxx`。和下表一致，说明粘贴完整；不一致就重新粘贴。

| 脚本 | 版本 | check |
|---|---|---|
| 00_probe.py | v1 | 80f428ff |
| 01_scan_files.py | v2 | 5fef1edb（v1 为 d896f071，已在堡垒机跑过；v2 只修了 .ts 被误判为视频，不需要重跑） |
| 02_ego_video_events.py | v1 | 7ad669dd |
| 03_roadside.py | v1 | 4177224e |
| 04_table_catalog.py | v1 | 91a08f0e |

堡垒机上的 Python：`D:\miniconda3\envs\process\python.exe`（3.10.9，已装 pandas 1.5.3、openpyxl、cv2、matplotlib）。

## 各脚本说明

- **00_probe.py**：检查环境（Python 版本、已装的包、内存、各盘容量）、测试粘贴时中文会不会乱码、确认已知目录是否存在、列出 D 盘一级目录。几秒钟就能跑完。
- **01_scan_files.py**：
  - 扫描所有本地盘（跳过系统目录和程序目录），生成 `file_index.csv`。
  - 把文件分成几类：自车视频 `ch{n}_{开始}_{结束}`、龙门架视频（文件名含 相机 / 摄像机 / 一体机）、participant json、表格、未识别视频等。
  - 耗时取决于文件数，可能需要几分钟到几十分钟，运行中每 5 万个文件打印一次进度。
- **02_ego_video_events.py**：自车视频去重，聚合成视频事件；统计 0920 表（条数、描述填写率、有效视频、是否紧急接管）；把两者按 VIN 和时间（±60 秒）关联。会输出：0920 事件里有视频的有多少、清单外的视频事件有多少、各通道组合的分布。
- **03_roadside.py**：
  - 龙门架视频：解析路口、相机、起止时间、案例目录；
  - participant json：只读每个文件开头 512 KB 做抽样，统计设备、路名、坐标、时间覆盖段；
  - 顺带统计 vehicle_track、traffic_flow、signal 等同批次 json 的数量。
- **04_table_catalog.py**：所有 xlsx 和 csv 只读表头，按表结构分组，找出含 vin、时间和经纬度的轨迹表。大于 300 MB 的 xlsx 会跳过，并记录下来。
