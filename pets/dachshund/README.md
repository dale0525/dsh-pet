# 腊肠犬 pet pack —— 源资产与生成链

本目录是一只**额外宠物（pet pack）**的全部源资产与工具：腊肠犬「JJ」，20 个动作。
规格见 [`docs/plans/pet-dachshund-green-screen.md`](../../docs/plans/pet-dachshund-green-screen.md)。

目录布局与运行时一一对应：`pets/<种类名>/` ↔ `$DSH_HOME/dsh-pet/pet/<种类名>-{config.json,animation/}`。
本目录**不含**运行时配置与播放素材——那两样在 `$DSH_HOME` 下（见文末「装配」）。

## 目录内容

```
pets/dachshund/
├── prompts/    20 个 .txt   H3 提示词（含 §5.4 通用前缀 + 按秒分解）
├── frames/      3 张 PNG    身份基准首尾帧（1672×941）
├── raw/         2 张 PNG    图生图原图 —— frames/ 的上游
├── h3/         20 个 .mp4   H3 成片（864×480 h264，付费产物）
├── reports/    20 个 .json  每次生成的成本/溯源记录
├── evaluate_dachshund.py    门禁脚本（frames / video 两种模式）
└── test_*.py     5 个文件   管线与门禁的单测（共 34 项）
```

| 目录 | 内容 | 为什么留着 |
| --- | --- | --- |
| `prompts/` | 20 个动作的 H3 提示词 | **新增动画的起点**：改一份提示词即可生成新动作 |
| `frames/` | `base-standing.png`（身份基准）+ `turn-side-left/right.png` | **身份锚点**：除 `turn` 外的 19 个动作共用同一张首尾帧，保证形象与缩放一致 |
| `raw/` | `base-standing-raw-1.png`、`base-standing-side-raw-1.png` | `frames/` 的图生图原图；**换形象时从这里重跑** |
| `h3/` | 20 个 H3 成片（扁平、`<动作名>.mp4`） | **不必重复付费**：改抠像/归一化算法后可直接重跑下游 |
| `reports/` | 20 份 `report.json` | 成本与溯源；排查「哪次生成用了什么参数」 |

> **`h3/` 是省钱的资产**：本包 H3 含返工实测总花费 **≈ $1.63**（规格 §17.4）；
> `reports/` 里保留的是**每动作最终一次**的记录，合计 $1.20。
> 调下游（`chroma_step02` / `normalize_step03` / `encode_thumbs`）时**不需要**重新生成 H3，
> 从 `h3/` 直接跑 `bridge_step00.py` 即可。

## 六段链路

编号沿用规格 §4。

```
① 标准首帧   身份基准图（四足站姿、绿幕）        → frames/base-standing.png
     ↓  dsh-imagegen（gpt-image-2，以 raw/ 为参考图）
② 每动作首尾帧 除 turn 外复用 ①，首尾是同一张       → frames/turn-side-{left,right}.png
     ↓  agentnovel_modal_h3.py（Ref2VA，6 步 Turbo，864×480）★ 唯一付费步骤
③ H3 视频     每动作一段 10 秒绿幕 h264/yuv420p   → h3/<动作名>.mp4
     ↓  scripts/bridge_step00.py   scale=1280:720:flags=lanczos
④ 桥接产物    1280×720 绿幕 mp4（chroma 的输入）   → step01/
     ↓  scripts/chroma_step02.py   HSV 色相抠像
⑤ 透明视频    1280×720 → 归一化 2160×1215 → 转码  → step02/ → step03/ → step04/
     ↓  normalize_step03.py（站立高度 900、居中） / encode_thumbs.py（640×360 VP9-alpha CRF40）
⑥ 装配        $DSH_HOME/dsh-pet/pet/dachshund-animation/*.webm
```

**④ 必须在 ⑤ 之前**：`chroma_step02.py` 与 `normalize_step03.py` 都**硬编码 1280×720**。
把 H3 原始的 864×480 直接喂给 ⑤ 不会报错，但会把 2.22 帧当成一帧读，**静默错位**。

**`step01/`~`step04/` 是中间产物**，已被 `.gitignore` 忽略，随时可从 `h3/` 再生：

```sh
cd /Volumes/LogicExt/Git/dsh-pet
pixi run bridge     # → step01/   —— 默认读 step00/，从 h3/ 重跑见下节
pixi run chroma     # step01/ → step02/
pixi run normalize  # step02/ → step03/
pixi run thumbs     # step03/ → step04/
```

## 新增一个动画

1. **写提示词**：复制 `prompts/01-idle-breathing.txt` 改动作描述，编号递增（`21-....txt`）。
   首尾帧必须回到同一站姿——除 `turn` 外，首尾帧是**同一张** `frames/base-standing.png`。
2. **生成 H3**：用 `agentnovel_modal_h3.py run --duration-seconds 10`，两张参考图都传该首帧。
   **这是唯一花钱的一步**（本包 20 段实测单段 $0.055–0.107，见 `reports/*.json`）。
3. **落盘**：成片存为 `h3/<动作名>.mp4`，成本记录存为 `reports/<动作名>.json`。
4. **跑下游**：从 `h3/` 经 ④→⑥ 产出 `step04/<动作名>.webm`（③ 已完成，`h3/` 就是它的产物）。
5. **接进配置**：把动作名加进 `$DSH_HOME/dsh-pet/pet/dachshund-config.json` 的某个池，
   并把 `step04/*.webm` 拷进 `dachshund-animation/`。宿主每次读配置，**刷新页面即生效**，无需重启。

> **命名**：`h3/`、`reports/`、`step04/`、`dachshund-animation/` 四处**必须同名**（`<动作名>`），
> 配置里的动画名就是文件名。

## 从 `h3/` 重跑下游（不重新付费）

`bridge_step00.py` 默认读 `step00/`，而本目录的 H3 成片在 `h3/`，用 `--src` 指过去：

```sh
cd /Volumes/LogicExt/Git/dsh-pet
pixi run python scripts/bridge_step00.py --src pets/dachshund/h3 --out step01
pixi run chroma && pixi run normalize && pixi run thumbs
```

## 门禁与测试

```sh
cd /Volumes/LogicExt/Git/dsh-pet

# 34 项单测
pixi run python pets/dachshund/test_frame_plate.py
pixi run python pets/dachshund/test_scripts_tools.py
pixi run python pets/dachshund/test_bridge_step00.py
pixi run python pets/dachshund/test_resume_truncation.py
pixi run python pets/dachshund/test_evaluate_dachshund.py

# 门禁：首尾帧（图像级）与成片（视频级）
pixi run python pets/dachshund/evaluate_dachshund.py frames pets/dachshund/frames/base-standing.png
pixi run python pets/dachshund/evaluate_dachshund.py video pets/dachshund/h3/待机呼吸.mp4 --seconds 10
```

`evaluate_dachshund.py` 有两种模式（按扩展名自动判定，也可用 `--raw` / `--keyed` 显式指定）：
- **raw**（H3 成片 `.mp4`）：容器门禁 864×480 / 24fps / 10±0.05s / h264
- **keyed**（交付物 `.webm`）：容器门禁 640×360 / 24fps / VP9+alpha，判定改用 2026-09-02 裁定口径
  （交付物绿溢 ≤2%、站立采样点前景 ≥0.15），同时**保留并打印**原始口径数值作参考

## 依赖与边界

- **③ 的生成器不在本仓库**：`agentnovel_modal_h3.py` 是外部工程的脚本（本仓库只引用它）。
  即「重新生成 H3」这一步**无法仅凭本仓库复现**；能复现的是 **④→⑥**（从入库的 `h3/` 起跑）。
  这也是把 `h3/` 成片入库的核心理由——它把不可复现的付费步骤固化下来。
- **评估器依赖 `test/pet1/`**（未入 git，按规格 §11 裁定 5）。缺失时**显式报错并给出补救指引**，
  不静默降级——门禁宁可报错也不假装通过（实测：缺 `test/pet1/` 时 `evaluate_dachshund.py` 退出码 1）。
- **运行环境**：`pixi.toml`（仓库根）定义了 numpy/scipy/pillow/ffmpeg；`.pixi/` 本机重建，不入库。
- **`test/pet1/` 不随本目录走**：它是本 pack 之前的 5 秒验证产物，按裁定不入版本库。

## 装配（产物去向）

`step04/*.webm` 的最终去处是 **`$DSH_HOME/dsh-pet/pet/`**（**不是** git 仓库根的 `pet/`）：

```
$DSH_HOME/dsh-pet/pet/
├── dachshund-config.json          ← 动画池 / 权重 / 人设文案（含 whisperPrompt、workStatusTexts）
└── dachshund-animation/*.webm     ← 20 个播放素材，扁平存放
```

放错位置宿主不会扫描，动画全部 404。素材目录名 = 配置文件名前缀 = 种类名。

## 许可与署名

素材沿用仓库根 `README.md`「许可」一节的约定（`README.md:516-517`，注意不在 `LICENSE` 里——
`LICENSE` 是纯 MIT）：允许开源使用、**禁止商用**。
**二创署名义务**：基于本项目的衍生 / 改版 / 换皮作品，在任何介绍、展示、分发该作品的地方，
须附上原作者 GitHub 地址 <https://github.com/PC2005-cloud/dsh-pet>。fork 与自有仓库维护不豁免该义务。
