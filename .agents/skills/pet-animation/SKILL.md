---
name: pet-animation
description: 给 dsh-pet 仓库新增宠物动画（pet pack 动作素材）时使用：写 H3 提示词 → 生成绿幕成片 → 桥接/抠像/归一化/转码 → 门禁验收 → 装配进运行时。触发词：新增动画、生成动画、pet pack、H3、绿幕素材链、腊肠犬、dachshund、evaluate_dachshund。
---

# 新增宠物动画

把一个新动作从提示词做到运行时可见。全链六段，只有 ③ 花钱，其余都能从 `h3/` 重跑。

## 前置

- 仓库根 `/Volumes/LogicExt/Git/dsh-pet`，下文路径均相对它。
- `pixi run ...` 提供 numpy/scipy/pillow/ffmpeg（`.pixi/` 本机重建，不入库）。
- **③ 的生成器不在本仓库**：在 DSH-Novel。先确认：
  ```sh
  cd /Volumes/LogicExt/Git/DSH-Novel
  ls scripts/agentnovel_modal_h3.py .dsh-novel/modal-credentials.json
  ```
  凭据文件须权限 600。首次或换机先同步 profile，否则 `reserve_credential` 会拒绝：
  ```sh
  python scripts/agentnovel_modal_h3_accounts.py sync --profile logictan89
  ```
- **成本**：单段 10 秒实测 $0.055–0.128。**没有跨调用累计上限**（`BUDGET_USD` 只派生单次尝试上限），总花费自行控制。

## ① 写提示词

复制 `pets/<种类名>/prompts/` 里任一份改动作描述，编号递增。必须遵守：

- 16:9、背景纯 `#00FF00`、无阴影/杂物；角色居中，头顶 ~20%、脚底 ~85%；任意部位距画幅边 ≥10%。
- **零位移**：双脚落点恒定，只允许轴心旋转/原地跳跃。`moves` 类动画的位移由播放器叠加，不是画进视频。
- 道具「无 → 有 → 无」闭环：首帧干净，道具渐进凝聚、结束前消散。
- **首尾帧同姿态**：最后一秒回到与第一帧一致的标准正面站立。

H3 契约（违反即报错或白花钱）：

- 六个段名按序：`subject_definitions` → `summary` → `retention_analysis` → `detailed_description` → `overall_soundscape` → `non_diegetic_music`。
- 必须声明 `effective duration of N seconds`。
- `<Picture 1>` / `<Picture 2>` 首次出现顺序必须是 1,2。
- opening/ending frame 附近 160 字符内须有 `best-effort`。
- 禁用措辞：`T2VA`、`I2VA`、`FL2VA`、`L2VA`、`Hybrid`、`keyframe completion`。

## ② 首尾帧

- 除 `turn` 外，**首尾帧是同一张** `pets/<种类名>/frames/base-standing.png`——这样各动作的站立高度与中心一致，`normalize_step03.py` 的缩放才统一。首尾不一致 → 动作之间大小/位置跳动。
- `turn` 类豁免：需偏侧首帧 + 其水平镜像尾帧（正面对称姿态翻转后还是正面，转向不成立）。
- 趴卧类：尾帧必须起身回站姿，趴姿只出现在中段。否则 `standing["height"]` 被拉低 → 该动作被放大到畸形。

## ③ 生成 H3 成片（唯一付费）

```sh
cd /Volumes/LogicExt/Git/DSH-Novel
python scripts/agentnovel_modal_h3.py run \
  --prompt-file /Volumes/LogicExt/Git/dsh-pet/pets/<种类名>/prompts/NN-slug.txt \
  --duration-seconds 10 \
  --reference-image /Volumes/LogicExt/Git/dsh-pet/pets/<种类名>/frames/base-standing.png \
  --reference-image /Volumes/LogicExt/Git/dsh-pet/pets/<种类名>/frames/base-standing.png \
  --out-dir /tmp/h3-out \
  --modal-profile logictan89
```

两张参考图都传同一张首帧 = 首尾一致。产物固定 864×480 / 24fps / h264。

从 `--out-dir` 取出产物并按动作名落盘：成片 → `pets/<种类名>/h3/<动作名>.mp4`；成本记录 → `pets/<种类名>/reports/<动作名>.json`。

## ④ 桥接（必须先于 ⑤）

```sh
cd /Volumes/LogicExt/Git/dsh-pet
pixi run python scripts/bridge_step00.py --src pets/<种类名>/h3 --out step01
```

这一步**不能跳**：下游抠像与归一化都硬编码 1280×720，直接喂 864×480 会**静默错位**（不报错）。
成因与门禁见 `AGENTS.md`「硬门禁」。

## ⑤ 抠像 → 归一化 → 转码

```sh
pixi run chroma     # step01/ → step02/（唯一产生 alpha 的环节）
pixi run normalize  # step02/ → step03/（站立高度 900、居中）
pixi run thumbs     # step03/ → step04/（640×360 VP9-alpha CRF40）
```

`step01/`~`step04/` 是中间产物，已被 `.gitignore` 忽略，随时可从 `h3/` 重跑。

## ⑥ 装配

```sh
cp step04/<动作名>.webm ~/.dsh/dsh-pet/pet/<种类名>-animation/
```

再把动作名加进 `~/.dsh/dsh-pet/pet/<种类名>-config.json` 的某个池。宿主每次读配置，**刷新页面即生效**。

**命名不变量**：`h3/`、`reports/`、`step04/`、`<种类名>-animation/` 四处同名（`<动作名>`）；配置里的动画名就是文件名。

## 验收

```sh
# 成片（H3 原始）
pixi run python pets/<种类名>/evaluate_dachshund.py video pets/<种类名>/h3/<动作名>.mp4 --seconds 10
# 交付物（装配用 webm）——必须带 --keyed
pixi run python pets/<种类名>/evaluate_dachshund.py video step04/<动作名>.webm --keyed --seconds 10
# 首尾帧
pixi run python pets/<种类名>/evaluate_dachshund.py frames pets/<种类名>/frames/base-standing.png
```

口径：raw（`.mp4`）门禁 864×480 / 24fps / 10±0.05s / h264；keyed（`.webm`）门禁 640×360 / 24fps / VP9+alpha，绿溢 ≤2%、站立采样点前景 ≥0.15。退出码 0 = PASS。

单测（腊肠犬 5 个文件 / 34 项；把 `<种类名>` 换掉即可）：

```sh
pixi run python pets/<种类名>/test_frame_plate.py
pixi run python pets/<种类名>/test_scripts_tools.py
pixi run python pets/<种类名>/test_bridge_step00.py
pixi run python pets/<种类名>/test_resume_truncation.py
pixi run python pets/<种类名>/test_evaluate_dachshund.py
```

## 边界

- 仓库内可复现的只有 ④→⑥。重新生成 H3 **无法仅凭本仓库复现**（生成器在 DSH-Novel），这也是 `h3/` 成片入库的理由。
- 门禁不降级：缺依赖时显式报错，不静默通过。
- 装配目标**不是**仓库根的 `pet/`，是 `$DSH_HOME/dsh-pet/pet/`。放错位置宿主不扫描，动画全部 404。
