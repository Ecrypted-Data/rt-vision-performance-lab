# 任务四｜视觉程序性能测量与单点优化

工作分支 `perf/vectorize-threshold`（fork 上），PR 目标 `Ecrypted-Data/rt-vision-performance-lab:main`。
评审期间的后续改动继续推送到本分支；验收后由组长关闭 PR，上游 `main` 保持为练习起始版本。

## 1. 对照条件

| 项 | 值 |
| --- | --- |
| 设备 | AMD Ryzen 5 5600U（12 线程），WSL2，内核 6.18.58.1-microsoft-standard-WSL2 |
| Runtime | Python 3.12.3 |
| 依赖 | numpy==2.2.6、opencv-python-headless==4.11.0.86（`requirements.txt` 固定） |
| 输入 | `runs/fixtures/vision-sample.png`，1280×720，2,111,609 B，固定随机种子 20261115 生成一次后复用 |
| 命令 | `.venv/bin/python -m vision --output-dir runs/<before\|after> --repeat 5` |
| 计时口径 | 程序内 `perf_counter_ns()`；预热 1 次 + 5 次取中位数；分段 load / grayscale / threshold / write / total；fixture 生成与 `timings.csv` 写出不计入 |
| 一致性判据 | `stats.json`（含掩膜原始字节 SHA-256）与 `mask.png` 的字节 SHA-256，前后必须相同 |

前后两轮同机、同 venv、同输入、同重复次数、同计时口径。

## 2. 基线（`runs/before`）

| 环节 | 中位数 | 5 次范围 | 占 total |
| --- | ---: | ---: | ---: |
| load | 11.240 ms | 8.990–11.743 | 7.1% |
| grayscale | 0.258 ms | 0.212–0.742 | 0.2% |
| **threshold** | **138.784 ms** | 135.629–141.799 | **87.8%** |
| write | 9.063 ms | 8.839–9.491 | 5.7% |
| total | 158.047 ms | 156.036–163.167 | 100% |

## 3. 瓶颈定位与选择依据

`vision/pipeline.py` 的 `threshold()` 用 Python 双重循环逐像素处理 1280×720 = 921,600 个像素，每次迭代都要做 numpy 标量索引与 `int()` 转换。该环节中位数 138.784 ms，占全流程 87.8%，比 load（11.240 ms）高一个数量级，比 grayscale（0.258 ms）高三个数量级。

因此唯一改动选在 threshold 环节；按基线估算，消除该环节可把 total 从 ~158 ms 压到 ~20 ms，而改动面只有一个函数体。

## 4. 唯一改动

`threshold()` 的逐像素循环替换为一次向量化比较：

- 语义保持 `gray >= cutoff → 255，否则 0`，函数签名与默认阈值 160 不变，返回 `uint8`；
- 用 `cv2.compare(gray, cutoff, cv2.CMP_GE)` 直接产出 `uint8` 掩膜，不产生 Python 层临时数组；
- 不选 `cv2.threshold(gray, cutoff - 1, 255, cv2.THRESH_BINARY)`：等价性依赖 off-by-one，语义不直观；
- 不选 `np.where(gray >= cutoff, 255, 0)`：会额外分配 int64 临时数组。

改动前后使用同一输入文件与同一计时命令复测，结果见下节。
