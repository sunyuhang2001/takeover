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
| 01_scan_files.py | v1 | d896f071 |

## 各脚本说明

- **00_probe.py**：检查环境（Python 版本、已装的包、内存、各盘容量）、测试粘贴时中文会不会乱码、确认已知目录是否存在、列出 D 盘一级目录。几秒钟就能跑完。
- **01_scan_files.py**：
  - 扫描所有本地盘（跳过系统目录和程序目录），生成 `file_index.csv`。
  - 把文件分成几类：自车视频 `ch{n}_{开始}_{结束}`、龙门架视频（文件名含 相机 / 摄像机 / 一体机）、participant json、表格、未识别视频等。
  - 耗时取决于文件数，可能需要几分钟到几十分钟，运行中每 5 万个文件打印一次进度。
