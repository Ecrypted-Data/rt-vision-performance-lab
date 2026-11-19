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

## 5. 复测结果（`runs/after`）

| 环节 | 改动前（中位） | 改动后（中位） | 变化 |
| --- | ---: | ---: | --- |
| load | 11.240 ms | 11.119 ms | −1.1% |
| grayscale | 0.258 ms | 0.224 ms | 绝对值 0.03 ms，噪声级 |
| **threshold** | **138.784 ms** | **0.122 ms** | **≈1138×，−138.662 ms** |
| write | 9.063 ms | 9.050 ms | −0.1% |
| **total** | **158.047 ms** | **20.589 ms** | **7.68×，−137.458 ms** |

交替复测第二轮（`runs/before-2` / `runs/after-2`，同一命令与口径）：

| 环节 | 改动前 | 改动后 | 变化 |
| --- | ---: | ---: | --- |
| threshold | 135.521 ms | 0.140 ms | ≈968× |
| total | 155.522 ms | 20.499 ms | 7.59× |

未改动的 load / write 两轮间波动 <2%，说明计时口径稳定；threshold 的差距在两次复测中均为三个数量级，不是单次噪声。按中位数换算，全流程吞吐 6.3 fps → 48.6 fps；改动后剩余耗时集中在 I/O：load 54%、write 44%，threshold 降到 0.6%。

## 6. 输出核对

- `diff -u runs/before/stats.json runs/after/stats.json` 无输出：width=1280、height=720、selected_pixels=327335、`mask_pixels_sha256` 完全一致（两者均为 `f070746b…e909`）。
- `cmp runs/before/mask.png runs/after/mask.png` 通过，两文件 SHA-256 均为 `0aa71d55…ac75`（同一数组经同一 PNG 编码器输出确定字节）。
- 第二轮 `before-2` / `after-2` 的 `mask.png` 同样与基线逐字节相同。
- 语义核对：`cv2.compare(gray, cutoff, cv2.CMP_GE)` 与 `gray >= cutoff` 同义，包含「等于 cutoff」边界；`cutoff` 参数与默认值 160 未变，返回仍为 `uint8` 的 0/255 掩膜。

## 7. 保留结论

**保留该改动。** 依据：

1. 输出逐字节一致（掩膜原始字节 SHA-256、PNG 文件 SHA-256、统计数据全部相同），无行为风险；
2. 全流程 7.6–7.7×，目标环节约 1000×，改动只有一个函数体，无新增依赖，可读性不降（一行向量化比较）；
3. 完成后剩余瓶颈已是文件读写，继续在原环节优化没有收益。

局限：计时为 WSL2 / Ryzen 5 5600U 上的绝对值，不宜与其他机器横向比较；倍数在两次复测中一致，可作为本机结论。

