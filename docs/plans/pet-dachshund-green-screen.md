# 腊肠犬宠物素材生产计划（绿幕路线）

> 状态：**已定稿，P0a–P2 已实施并通过门禁，待放量（P3–P6）**（§11 的 7 项未决问题已由用户全部裁定；
> remote 切换已完成，见 §11 前置；实施记录见 **§14**）
> 范围：以 `test/pet1/reference.jpg` 左下方长毛腊肠犬为角色，产出 **20 个动作**的可装配素材
> 路线：**绿幕**（已实测可行）——不是透明背景路线
> 时长：**10 秒/动作**；产物格式：**仅 VP9-Alpha `.webm`**（不做 `.mov`）

---

## 1. 预期结果

产出 **20 个动作**（每段 **10 秒**）的 VP9-Alpha `.webm`，装配成 `dsh-pet` 的一个**独立 pet pack**
（`$DSH_HOME/dsh-pet/pet/dachshund-config.json` + `dsh-pet/pet/dachshund-animation/`），
在 DSH Web 界面里作为一只可交互宠物运行：待机、转向、被拖拽、点击回应、随机动作、屏幕漫游、余额档位动画全部可用。

**验收的最终形态**：Chrome / Firefox 里看到腊肠犬在右上角待机呼吸，点击有回应，拖拽会悬空，抛掷有物理反馈，右键菜单能点播任意动作。

**不含**：Safari 兼容（需 `.mov`，已裁定不做）、CI 接入、`test/pet1/` 入库。

## 2. 为什么是绿幕路线

透明背景路线**技术上可行但工程上不通**。两个来源分别支撑不同结论：

| 结论 | 来源 | 具体证据 |
| --- | --- | --- |
| 透明**静帧**可行 | `test/pet1/ACTION-DESIGN.md`（该文件 §「透明背景」小节） | gpt-image-2 经网关能返回真 alpha PNG（36/36 简洁提示词） |
| 透明**视频**不可行 | **本次核验**（本会话对 HuggingFace `Comfy-Org/MiniMax-H3` 的 `vae/minimax_h3_video_vae_fp16.safetensors` 做 range request 读 safetensors header） | VAE `encoder.conv_in.weight [128,3,3,3,3]` 是 3 通道 RGB；562 个张量**无任何 4 通道卷积**；H3 产物实测 `h264/yuv420p`（`ffprobe h3-out/output.mp4`） |
| 透明参考图对 H3 无效 | **本次核验**（读 pinned ComfyUI commit `62b3c94` 的 `nodes.py`） | `LoadImage` 返回 `(IMAGE, MASK)`，alpha 被拆到独立 MASK；图里节点 10 只接 slot 0（`ref_images.ref_image_0: ["6", 0]`） |

> **两份来源的边界**：`ACTION-DESIGN.md` 记录的是**生图接口探测**（透明 PNG 能否拿到），
> 它**不涉及** VAE 架构与 ComfyUI 节点接线。后者是本计划新增的核验，不归该文件。

**结论**：绿幕是唯一能同时覆盖「静帧参考」与「视频产物」两个环节的路线。

## 3. 角色定义（唯一真源）

- **来源**：`test/pet1/reference.jpg`（853×1137）**左下方**那只，已裁切为 `test/pet1/target-dog.png`（390×520）
- **身份锚点**（用于每张首帧的身份一致性校验）：长毛腊肠犬；金红/浅棕羽状被毛；长而下垂的羽状耳；深色圆眼；黑鼻；胸口与前爪偏奶油白；**吐舌**
- **姿态基准**：**四足站姿**（四肢着地、正面、居中）——**这是全库首尾帧的统一姿态**，理由见下

> ⚠️ **一处必须解决的姿态冲突**：参考图 `target-dog.png` 是**坐姿**（前肢撑地、后躯坐地），
> 而原提示词库的「标准正面站立」是**双足直立**。腊肠犬是四足动物，「站立」有两种解释：
> ① **四足站姿**（四肢着地）；② **坐姿**。
> **本计划选 ①四足站姿**作为首尾帧基准，理由：`turn`/`moves` 类动作需要行走与转向，坐姿无法行走；
> 且 `normalize_step03.py` 按首尾帧测量站立高度来统一缩放，四足站姿的高度定义更稳定。
> **故参考图不能直接当首帧用**——第一批必须先用图像模型生成一张「四足站姿、正面、居中」的
> 标准首帧作为新的身份基准图（见 §8 P1）。
> 这一条是**本计划最大的未验证假设**——见 §9 风险 R1。

## 4. 全链路（六段）

```
① 标准首帧（身份基准图，四足站姿）
      ↓  dsh-imagegen (gpt-image-2, 以 target-dog.png 为参考图)
② 每动作首尾帧（绿幕，两帧）
      ↓  agentnovel_modal_h3.py（Ref2VA，6 步 Turbo，864×480）
③ H3 视频（绿幕，h264/yuv420p）
      ↓  【桥接脚本，待写】scale=1280:720:flags=lanczos
④ 1280×720 绿幕 mp4 → step01/          ← 跳过 step01，直落 chroma 的 SRC
      ↓  chroma_step02.py（HSV 抠像）→ step02/
⑤ step02/*.webm → normalize_step03.py → step03/
      ↓  encode_thumbs.py（640×360 VP9-alpha CRF40）→ step04/
⑥ step04/*.webm → $DSH_HOME/dsh-pet/pet/dachshund-animation/
```

> **④ 的目录是 `step01/`，不是 `video/`**：`video/` 是 `watermark_step01.py` 的**输入**（供它去即梦/豆包水印），
> H3 产物无水印故跳过该步；而 `chroma_step02.py` 的 SRC 是 `step01/`（`chroma_step02.py:14`）。
> 把桥接产物直接写进 `step01/` 即可，**`video/` 全程不参与**。详见 §5.1。
>
> **⑥ 是绝对路径**：pet pack 必须落在 `$DSH_HOME/dsh-pet/pet/` 下
> （`host/index.ts:178-181` `userRoot = join(resolveDshHome(), 'dsh-pet')`），
> **不是** git 仓库根目录的 `pet/`——放错位置宿主不会扫描，动画全部 404。详见 §5.3。

**与上游 README 的差异**：上游配方第 1 步是「提示词 → 源视频」（用可灵/豆包等直接出 10 秒绿幕视频），**没有首尾帧这一环**。
本计划改为「首尾帧 → H3」，因为 H3 是 Ref2VA（参考图生视频），无法纯文生视频。这是**路线差异，不是缺陷**，但意味着动作可控性依赖首尾帧质量。

## 5. 硬约束（每条都已亲验）

### 5.1 管线约束

| 约束 | 证据 | 后果 |
| --- | --- | --- |
| H3 固定输出 **864×480** | `modal_h3_contract.py:88` `WIDTH, HEIGHT = 864, 480` | 必须桥接到 1280×720 |
| 桥接**必须在 step02 之前**（且在 step03 之前） | **两处**都写死 1280×720：`chroma_step02.py:21` `W, H, FPS = 1280, 720, 24` + `:162` `frame_size = W*H*3`；`normalize_step03.py:33-34` `SRC_W, SRC_H = 1280, 720` + `:68` `frame_size = SRC_W*SRC_H*4`。864×480 一帧仅 1244160 字节，而 step02 期望 2764800 → **会把 2.22 帧当一帧解释**（静默错位，不是缩放） | 桥接脚本是**必需**组件 |
| step01 可跳过（有条件） | `watermark_step01.py` 专为**去即梦/豆包水印**而写（mask `watermark_mask_v5.mkv` 是 1280×720） | H3 无水印 → 桥接产物**直接放 `video/`** 不行，见下 |
| 首尾帧必须同姿态 | `normalize_step03.py:91` 取首尾各 5 帧测 `height`/`center_x`/`max_y`，据此 `scale = TARGET_HEIGHT / standing["height"]` 与 overlay 对齐 | 首尾姿态不一致 → **各动作之间大小/位置跳动** |

> **桥接为何必须在 step02 之前（而不是 step03 之前）**：虽然 step02 与 step03 都写死 1280×720，
> 但 step02 是**唯一产生 alpha 的环节**，它按 3 字节/像素读 RGB。
> 若把 864×480 直接喂给它，字节流会错位；若先补 alpha 再缩放则会引入二次编码。
> 故正确顺序是：**H3 原始 mp4 → 桥接（lanczos 到 1280×720）→ step02**。

> **step01 的处置**：`watermark_step01.py` 的输入是 `video/*.mp4`、输出 `step01/*.mp4`。
> H3 产物无水印，理论上可跳过 step01，**直接把桥接产物写进 `step01/`**（因为 `chroma_step02.py` 的 SRC 就是 `step01/`）。
> 本次核验：H3 输出边框环非绿像素仅 1.39%–2.77%，且**空间分布集中在中列上/下**（狗头与尾部伸入），
> **四角均为纯绿 `(1,243,0)`**——**不是水印**。故确认可跳过 step01。
> **但这需要把桥接产物落到 `step01/`**，而 `step01/` 在 `.gitignore` 中——符合上游「中间产物不入库」的约定。

### 5.2 H3 契约约束

| 约束 | 值 | 来源 |
| --- | --- | --- |
| 时长范围 | **4–15 秒** | `modal_h3_contract.py:89` |
| 10 秒 → 帧数 | output 240 / generation 243 | `duration_frame_contract()` 实算 |
| 分辨率 | 864×480（不可调） | `:88` |
| 帧率 | 24 fps | `:88` |
| 参考图上限 | **9 张** | `:90` `MAX_REFERENCE_IMAGES` |
| 提示词上限 | 32000 字符 | `:98` |
| 六个段名与顺序 | `subject_definitions` → `summary` → `retention_analysis` → `detailed_description` → `overall_soundscape` → `non_diegetic_music` | `:109-112`，顺序错即报错 |
| 必须声明时长 | `effective duration of N seconds` | `:145-153` |
| 图片标签必须**按序**出现 | `<Picture 1>`, `<Picture 2>` 首次出现顺序必须 = 1,2 | `:170-177` |
| 首尾帧必须标 `best effort` | 出现 `opening/ending frame` 附近 160 字符内必须有 `best-effort` | `:179-183` |
| 禁用措辞 | `T2VA`/`I2VA`/`FL2VA`/`L2VA`/`Hybrid`/`keyframe completion` | `:114-118` |
| 成本 | 预算 $3.00，单次尝试上限 $1.40（`(3.00-0.20)/2`），每次调用最多 2 次尝试 | `:81-84` |

> ⚠️ **`BUDGET_USD` 的作用域**：它**只用于派生单次尝试的上限**
> （`MAX_COST_USD_PER_ATTEMPT = (BUDGET_USD - 0.20) / 2 = 1.40`，再由 `ADMISSION_RATE_USD_PER_HOUR=8.00`
> 换算出 `MAX_EXECUTION_SECONDS_PER_ATTEMPT`）。
> 全仓库**没有跨调用累计检查**（`grep cumulative|total_cost|spent` 无命中）——
> 所以 20 次调用是 20 次各自独立的预算约束，**总花费不受 $3.00 保护**，需自行控制。

**实测成本基准**：5 秒视频 = **$0.0777**、92.2 秒墙钟（RTX PRO 6000，`$3.0312/h`）。
其中 ComfyUI 启动 14.0 s 与模型加载是**固定开销**，采样 26.4 s 随时长近似线性增长。
**时长已裁定为 10 秒**（第 2 条），故 10 秒 ≈ **$0.12–0.16**（**线性外推，未实测**，P2 将实测校准）。

### 5.3 动画池契约（`dsh-pet` 侧，硬校验）

`animationsValid()`（`dsh-pet/src/host/config.ts:103-142`）要求：

- `idle` / `turn` / `drag` / `clicks` 必须是数组（**校验层允许空数组**）
- `moves` 必须有 `default` 对象 + `actions` 数组
- `categories` 必须是数组
- `events` 必须是对象，**每个 pool 非空**，且 `events.balance` 必须存在且非空
- `animationWeights` 必须有 `idle`/`turn`/`move` 三个非负有限数

**pet pack 不回落**：`animations` / `animationWeights` **必须写全**，缺失即配置错误。

> ⚠️ **「校验通过」≠「功能可用」**——三处易踩的坑：
> 1. **`idle` 空数组能通过校验，但功能上是坏的**：`pick()`（`shared/pickers.ts:5-10`）对空池返回
>    `src[Math.floor(Math.random()*0)]` = `undefined`；而分类池为空时 `pickCategoryAction()`
>    （`:86-98`）会回退到 `pick(idlePool, current)` → **拿到 `undefined` 动画名**。
>    故 `idle` **必须非空**。
> 2. **权重合计 = 100 只是注释约定，代码并不校验**。`weightsValid()`（`config.ts:145-153`）只检查
>    三个值是非负有限数；`rollKind()`（`pickers.ts:79-81`）用 `/100` 归一化，
>    所以合计 < 100 时剩余概率全归 `action`，合计 > 100 时 `turn`/`move` 可能永远抽不到。
>    **写错不报错，只是行为静默偏移**——必须自行保证
>    `animationWeights.idle + .turn + .move + Σ(categories[].weight) = 100`。
> 3. **`categories` 不是字符串数组**，是 `Category[]` 对象数组：
>    `{ id: string, weight: number, noMirror?: boolean, actions: string[] }`
>    （`shared/types.ts:41-46`）。写成平铺字符串数组会在 `pickWeightedCategory()`
>    （`pickers.ts:57-68` `categories.filter((c) => c.actions.length > 0)`）与
>    `buildMenuTree()`（`menu.ts:72-74`）处**抛 `TypeError`**。
>
> **完整配置骨架**（pet pack 必填字段，缺一即加载失败）：
>
> ```jsonc
> {
>   "pets": [                       // 必须有；每只实例必填 id/size/balanceEnabled/display/position
>     { "id": "dachshund1", "name": "腊肠犬", "size": 420, "balanceEnabled": true, "display": "both",
>       "position": { "corner": "top-right", "marginX": 24, "marginY": 100 } }
>   ],
>   "animations": {
>     "idle": ["待机呼吸"], "turn": ["原地轴转张望"], "drag": ["悬空提溜反馈"],
>     "clicks": ["欢快蹦跳", "受惊炸毛后缩", "单爪抬起招手"],
>     "moves": {                    // default 必填对象；actions 是 MoveSpec[]（{name, params?}）
>       "default": { "minDist": 60, "maxDist": 240, "margin": 20, "leadSec": 2, "tailSec": 2 },
>       "actions": [ { "name": "原地倒步踱行" }, { "name": "横向侧步滑行" } ]
>     },
>     "categories": [               // Category[]，不是字符串数组
>       { "id": "小动作", "weight": 40, "actions": ["犬式伸懒腰", "哈欠连天甩头"] },
>       { "id": "玩耍", "weight": 40, "actions": ["爪拨玩具小车", "兴奋拍打尾巴"] }
>     ],
>     "events": {
>       "balance": ["余额-满溢欢腾", "余额-鼻顶叮当", "余额-寻常轻嗅",
>                   "余额-缩水爪扒", "余额-见底流汗", "余额-瘫趴叹气"],
>       "whisper": ["待机呼吸"]      // 必填！见 §9 R10：右键「碎碎念」硬编码，缺失即报错
>     }
>   },
>   "animationWeights": { "idle": 10, "turn": 5, "move": 5 }   // 10+5+5+40+40 = 100
> }
> ```
>
> 字段约束来源：`config.ts:276-372`（`mergePets` 逐字段合并与 `petNumber`/`petBool`/`petEnum` 校验）
> 与 `README.md:193-202`（pet pack 示例）。
> `notificationsEnabled` / `eventsRefreshSec` 是**全局属性，不归 pet 文件管**（写了忽略）。
>
> **关于 `whisper` 填什么**：`whisper` 池只要求「非空且动画名真实存在」（`animationsValid` 只对
> `Object.values(events)` 逐池查非空）。本计划**不新增第 21 个动作**，而是**复用 `待机呼吸`**
> ——代价是碎碎念时外观与待机一致（头顶气泡文字仍正常显示），换来动作数锁定在 20。
> 若后续希望碎碎念有专属动作，可从库中 `碎碎念-发呆碎碎念` 改写一个 `低哼碎碎念` 作为第 21 个。

**余额档位**：`balanceEventIndex(p)`（`shared/balance.ts:159-163`）→ `p===100 ? 5 : min(floor(p/20), 4)`。
即 `events.balance` **需要 6 个槽位**才能覆盖全部档位；不足时 `pool[idx]` 为 `undefined` → 控制台报「档位索引越界」并跳过（**不崩，但功能残缺**）。

**素材解析规则**：pet pack 的素材目录名 = 配置文件前缀，且**必须落在 `$DSH_HOME` 下**：

```
$DSH_HOME/dsh-pet/pet/dachshund-config.json      ← 配置
$DSH_HOME/dsh-pet/pet/dachshund-animation/*.webm ← 素材（直接平铺）
```

依据：`host/index.ts:178-181` `userRoot = join(resolveDshHome(), 'dsh-pet')`、
`petConfigDir = join(userRoot, 'pet')`，`README.md:176-186` 同述。

> ⚠️ **不是** git 仓库根目录的 `pet/`——放错位置宿主不扫描，动画全部 404。
> 本机 `$DSH_HOME` = `/Users/logictan/.dsh`（实测），故完整路径是
> `/Users/logictan/.dsh/dsh-pet/pet/dachshund-config.json`。

**不要套 `webm/` 子目录**——那是主宠物 `main-animation/webm/` 的规则（`host/index.ts:567-574` 的 `animSubdirFor`）。
pet pack 的 `-animation/` 目录下**直接平铺** `.webm`。
URL 形如 `/thumb/dachshund/<动画名>.webm`，**查不到即 404，绝不回落**到主宠物素材。

### 5.4 提示词库约束（通用前缀）

`prompts/桌面宠物 10 秒动作提示词.md` 的通用前缀规定（**全库共享，不可逐条推翻**）：

- 16:9、背景**纯 #00FF00**、无阴影/杂物/渐变
- 角色**绝对居中**，头顶 ~20%、脚底 ~85%
- **安全红线**：任意部位距画幅任意边 **≥10%**
- **零位移**：双脚落点恒定，不允许 X/Y 平移（仅允许轴心旋转、原地跳跃）
- **道具「无→有→无」闭环**：首帧必须干净无道具，道具需由角色「渐进凝聚」生成、结束前消散
- **首尾帧一致**：最后一秒必须恢复到与第一帧完全一致的标准正面站立

> ⚠️ **「零位移」与 `moves` 池冲突**：`moves` 类动作在运行时由 `dsh-pet` 真实平移宠物窗口
> （`moves.default.minDist/maxDist`，`leadSec`/`tailSec` 首尾原地不动）。
> 所以 `moves` 动画本身**也必须零位移**——位移由播放器叠加，不是画在视频里。
> 提示词库的「螃蟹走路」「原地漂浮踏步」正是这个设计（原文明确写「全程 X 轴坐标不偏移，仅通过姿态表现」）。

## 6. 动作清单（20 个，已定稿）

### 6.1 池分配与数量

| 池 | 数量 | 说明 |
| --- | --- | --- |
| `idle` | 1 | 待机呼吸 |
| `turn` | 1 | 必须首尾严格镜像 |
| `drag` | 1 | 被抓起悬空、四肢下垂 |
| `clicks` | 3 | 点击回应，随机抽 1 |
| `moves` | 2 | 起步→行进→停稳 |
| `categories` | 6 | 随机动作池（可分批追加） |
| `events.balance` | 6 | 余额档位，**必须恰好 6 个** |
| **合计** | **20** | 用户裁定值（远超「≥10 个动作」的原始要求） |

> **为什么是 20**：用户原始要求是「至少 10 个动作」，第 1 条裁定取 **20 个**（含 6 个余额档位，
> 该池是**契约要求**必须恰好 6 个，不足会报越界）。20 也是留出失败重做余量、把 `categories` 做得像样的取值。
>
> **契约下界（仅供参考，非本计划取值依据）**：`turn`/`drag`/`clicks`/`moves`/`categories`
> 的空数组都能通过校验，故「配置能加载」的下限是 **7 个**（`idle` 1 + `balance` 6）；
> 「功能可用」的下限是 **11 个**。**这两个数字不影响本计划——已定稿 20 个。**
>
> ⚠️ **20 条是「已定稿清单」**（用户第 1 条裁定）。但生产起点仍是 **§8 P2 的 1 个动作**，
> P2 通过后才按 §8 逐阶段放量。
> **P1/P2 失败时不裁剪、不回退**（第 6 条裁定）——**暂停并上报**，由用户决定下一步。

### 6.2 逐条定义

以下「犬版名」是**新建的动画名**（不复用女仆动作名，避免语义污染）。
每条的提示词以库中原动作为**蓝本改写**（改写要点见「改写要点」列）。
犬版命名与「能否迁移」的判定来自**对全库 106 条动作的逐条分类**
（结论：**直接可用 1 / 改写后可用 55 / 不适用 50**；不适用者主要是依赖双手持物、
拟人服饰（裙摆/围裙）、双足直立或人类餐具的动作）。

| # | 犬版动画名 | 池 | 蓝本（库中原文） | 改写要点 |
| --- | --- | --- | --- | --- |
| 1 | `待机呼吸` | idle | 待机呼吸休闲 | 「呆毛/鲸鱼尾巴」→「垂耳与尾巴极微摆动」；「眨眼」→「狗眨眼/耳朵抽动」 |
| 2 | `原地轴转张望` | turn | 东张西望 | 四足原地小步轴转，结尾严格定格为首帧的左右镜像；**首帧必须是偏侧姿态**（见 §6.3） |
| 3 | `悬空提溜反馈` | drag | 被鼠标拖拽悬空反馈 | 像被提起后颈皮：四肢离地自然下垂、长身微弓；去掉「双脚离地」的双足语义 |
| 4 | `欢快蹦跳` | clicks | 点击回应-开心跃动 | 「双手高举欢呼」→「前肢腾空轻跃 + 垂耳扬起 + 尾巴快摇」；保留头顶爱心 |
| 5 | `受惊炸毛后缩` | clicks | 被吓一跳 | 「双手抬胸」→「前爪后撤缩身 + 被毛与尾巴微炸」；随后尴尬吐舌放松 |
| 6 | `单爪抬起招手` | clicks | 点击回应-元气挥手 | 「双手过头挥手」→「单前爪高抬轻挥（招财犬式）」+ 尾巴欢快摇 |
| 7 | `原地倒步踱行` | moves | 原地漂浮踏步 | 四肢原地高频倒换小碎步；**零位移**（位移由播放器叠加） |
| 8 | `横向侧步滑行` | moves | 螃蟹走路 | 四足原地侧向交替倒脚横踱；同样零位移 |
| 9 | `犬式伸懒腰` | categories | 超大伸懒腰 | 「双臂上举」→ 前胸贴地、前肢前伸、臀部翘起的经典犬式拉伸 |
| 10 | `哈欠连天甩头` | categories | 哈欠连天 | 「双手揉眼」→ 张嘴大哈欠 + 用力左右甩头晃动垂耳 |
| 11 | `兴奋拍打尾巴` | categories | 用鲸鱼尾巴拍打地面 | 「鲸鱼尾巴」→ 毛茸长尾在地面左右兴奋扫动拍打 |
| 12 | `爪拨玩具小车` | categories | 原地蹲下玩玩具汽车 | 「双手推车」→ 单前爪轻按拨弄滑行的小玩具车，低头歪脑打量 |
| 13 | `凌空接吞零食` | categories | 吃Token | 「双手捧送入口」→ 空中漂浮的发光物落向嘴边，轻跳叼住吞下舔鼻 |
| 14 | `爪嘴并用拆礼物` | categories | 拆礼物 | 「双手拆丝带」→ 前爪按住礼盒、用牙齿撕咬扯开缎带并探头叼出玩具 |
| 15 | `余额-满溢欢腾` | events.balance[0] | 余额-钱袋满溢 | 身前浮现装满肉干的大袋，绕袋踏步狂摇尾巴 |
| 16 | `余额-鼻顶叮当` | events.balance[1] | 余额-金袋叮当 | 用湿润鼻尖顶弄饱满的袋子使其叮当作响 |
| 17 | `余额-寻常轻嗅` | events.balance[2] | 余额-钱袋如常 | 中性：淡定低头嗅嗅、从容摇两下尾巴 |
| 18 | `余额-缩水爪扒` | events.balance[3] | 余额-数金皱眉 | 前爪扒拉变瘪的小袋，垂耳耷拉，委屈叹息 |
| 19 | `余额-见底流汗` | events.balance[4] | 余额-袋空如洗 | 空袋倒扣只落出孤零硬币，歪头冒汗、委屈缩爪垂尾 |
| 20 | `余额-瘫趴叹气` | events.balance[5] | 余额-分文不剩 | 四肢无力就地趴下贴地、下巴搁前爪间、眼神放空叹气；**尾帧必须起身回站姿**（见下） |

> **道具类动作的取舍**：`凌空接吞零食` / `爪嘴并用拆礼物` / `爪拨玩具小车` 都涉及**爪嘴精细交互**，
> 在写实四足动物上属高难度镜头（易穿模、面部畸变、道具黏连）。
> 分类时已判定它们「改写后可用」，但**建议排在 P4 之后**，先用低风险动作（1/7/9/10/11）验证端到端。

### 6.3 首尾帧设计原则

每个动作需要**两张绿幕首尾帧**：

- **首帧**：四足站姿、正面、居中、无道具、纯绿幕
- **尾帧**：动作结束时的姿态，**必须回到与首帧一致的站姿**

**代价**：**首尾帧不必逐动作各出一张**——除 `turn` 外的 19 个动作**首尾帧是同一张** `base-standing.png`
（§5.4 要求末帧完全回到首帧姿态），`turn` 另需 1 张偏侧首帧 + 其水平镜像尾帧。
**即整包只需 2 张生成的图**（口径修正见 §14.6 A2；本段原先写「20 × 2 = 40 张」是算术失误，
「18 个动作」同属算术失误，2026-09-15 一并改为 19——与下方「19 个动作的 `standing["height"]`」对齐）。
每张都需验证绿幕纯度（它是 `normalize_step03.py` 测站立高度的唯一输入）。

#### 三类例外（必须单独处理，否则破坏下游假设）

| 例外 | 问题 | 处置 |
| --- | --- | --- |
| **`turn` 类** | 其**语义**要求尾帧是首帧的**严格左右镜像**（`dsh-pet` 靠它翻转朝向）；若首帧是正面对称姿态，水平翻转后**还是正面**，转向动作不成立 | 首帧必须是**偏侧姿态**（如库中原文「偏左站立」）。**这与「所有动作首帧统一正面」相冲突**，故 `turn` 类**豁免**该统一性，单独生成一组偏侧首帧 |
| **趴卧类**（#20，及任何尾帧趴地的动作） | `normalize_step03.py:91` 用**首尾各 5 帧**测站立高度；若尾帧是趴姿，`standing["height"]` 会被拉低，导致该动作被**放大到畸形** | 尾帧**必须起身回到四足站姿**；趴卧只出现在**中段**，最后一秒起身 |
| **`moves` 类** | 需「起步→行进→停稳」三段，且 `moves.default.leadSec/tailSec` 要求首尾各若干秒**原地不动** | 首尾帧都是站姿（首=起步前，尾=停稳后），中间才是步态 |

> **「所有动作首帧尽量相同」的准确含义**：除 `turn` 类外，首帧都应是**同一张四足站姿基准图**
> （或由它派生的微调版）。这样 19 个动作的 `standing["height"]` 与 `center_x` 才一致，
> `normalize_step03.py` 的缩放才统一。**这是 §7.3「缩放一致性」检查的前提。**

## 7. 验收检查

### 7.1 每张首尾帧（图像级）

| 检查 | 阈值 | 方法 |
| --- | --- | --- |
| 绿幕纯度 | 背景占比 ≥ 0.70 | 复用 `evaluate_h3_pet1.py` 的 `silhouette_profile` 思路 |
| 绿幕均值 | 接近 `(0,255,0)`，各通道偏差 ≤ 25 | 纯 PIL 逐像素 |
| 绿幕平坦度 | 标准差 ≤ 15 | 同上 |
| 构图 | 主体水平中心 ∈ [0.40, 0.60]；高度占比 ∈ [0.70, 0.90] | 同上 |
| 身份一致 | 毛色/耳型/体型与 `target-dog.png` 相符 | **人工目视**（不做直方图） |
| 无道具 | 首帧无任何非狗非绿幕物体 | **人工目视**（不做连通域计数） |

> **为何只保留四项定量**：这些图是 H3 的 `<Picture 1>`/`<Picture 2>` 锚点，
> 也是 `normalize_step03.py` 测量站立高度的**唯一输入**——所以绿幕纯度与构图必须定量把关（不达标则 2 张图全返工）。
> 而「身份是否像同一只狗」「有没有多出道具」用眼睛判断更快更准，
> 为其写直方图/连通域脚手架属**过早工程化**，故降级为目视。

### 7.2 每段视频（视频级）

| 检查 | 阈值 | 方法 |
| --- | --- | --- |
| 容器契约 | 864×480 / 24fps / 时长 = 请求值 ±0.05s / h264 | ffprobe |
| 绿幕占比 | 每个采样点 ≥ 0.70 | 5 点采样（0/25/50/75/95%） |
| 抠像可用 | 用 `chroma_step02.py` 精确阈值：背景 ≥ 0.70、前景 ≥ 0.15 | 本次已实测该法可行 |
| 绿溢 | 前景中绿溢像素 ≤ 2% | 已实测为 **0%** |
| 首尾一致 | 首帧 vs 尾帧的站立高度差 ≤ 5%、水平中心差 ≤ 0.05 | 这是 `normalize_step03` 的输入前提 |
| 零位移 | 主体水平中心全程极差 ≤ 0.08 | 5 点采样 |

> **测量口径（2026-09-02 用户裁定，见 §16.9）**：
> 1. **绿溢以交付物为准**。表里的「绿溢 ≤2%」若量在**原始 h264 成片**上，会系统性高估用户可见的绿边
>    （抠像会把偏绿的边缘像素判成半透明/透明）。**判定标准是抠像后的交付物**（`step04/*.webm`）：
>    在 alpha>128 的像素中，偏绿像素占比必须 ≤2%。原始成片的数值仅作趋势观察，不作判定。
> 2. **抠像前景 ≥0.15 只对站立采样点生效**。该阈值取自站立基线（21–25%），
>    对趴卧/贴地伸展/悬空等**投影面积天生偏小**的姿态结构性不可达。
>    对低位段改判两项：绿幕占比 ≥0.70、无穿模（贴边像素为 0）。

> **已实测的基准值**（`test/pet1/h3-out/output.mp4`，5 秒版）：
> 绿幕占比 0.7387–0.7830、绿幕均值 ≈ (2–4, 243, 1–2)、绿幕标准差 ≤ 12.3、
> 主体高度占比 0.8542–0.8812、主体水平中心 0.4502–0.5000、绿溢 ≤ 0.01846。
> 抠像实测（本次）：背景 **74.26%–78.62%**、前景 **21.30%–25.57%**、绿溢 **0%**。

### 7.3 整链（集成级）

| 检查 | 方法 |
| --- | --- |
| 每个 `.webm` 可被浏览器透明渲染 | 人工在 **Chrome / Firefox** 查看（**Safari 不在范围**，第 7 条裁定） |
| 动画池配置通过校验 | 加载时不出现 `[dsh-pet] 配置缺少 animations...` 报错 |
| 每个池的动画都实际可播（非 404） | 右键菜单逐个点播 |
| 待机循环自然 | 观察 idle 首尾衔接无跳变 |
| `turn` 真的翻转朝向 | 观察转向后朝向改变 |
| 余额档位不报越界 | 控制台无「档位索引越界」 |
| 缩放一致性 | 20 个动作并排对比，狗的大小/脚底线一致 |
| **右键「碎碎念」不报错** | 控制台不出现 `[dsh-pet] 配置缺少 animations.events.whisper`（见 §9 R10） |

### 7.4 门禁（fail-closed）

**必须有**：一个 pet pack 目录下的评估脚本 + 单元测试（现位于 `pets/dachshund/`，见 §19），
对「无狗纯绿幕视频」**必须判 REVIEW**（沿用 `test/pet1/evaluate_h3_pet1.py` 已修的 fail-closed 设计，
该缺陷已固化为 `FailClosedGateTests`）。

## 8. 分阶段执行

| 阶段 | 内容 | 产出 | 验收 | 预估成本 |
| --- | --- | --- | --- | --- |
| **P0a** | **建 pixi 环境**（numpy/scipy）〔已授权，第 4 条〕 | `pixi.toml` + `.pixi/` | 三个管线脚本可 `import numpy` | $0 |
| **P0b** | 写桥接脚本 + 修 ffmpeg 路径 + 修常量双份〔已授权，第 3 条〕 | `bridge_step00.py`（864×480→1280×720 写 `step01/`） | 用现有 `h3-out/output.mp4` **跑通全链到 `step04/*.webm`**（step01→02→03→04） | $0 |
| **P1** | 生成标准首帧（四足站姿） | 1 张基准图 | §7.1 全过 | 未计价（见下） |
| **P2** | 试制 1 个动作（`待机呼吸`）端到端，**10 秒** | 1 个 `.webm` + 装配 | §7.2 + §7.3 全过 | ~$0.12 |
| **P3** | `turn` 专属偏侧首帧 + 镜像尾帧 | 1 张生成 + 1 张镜像 | §7.1 全过 | 未计价（见下） |
| **P4** | 批量 H3 生成 18 段视频（P2 出 `idle`、P3 出 `turn`，余下 18 条归此），**各 10 秒** | 18 段 mp4 | §7.2 全过 | ~$2.3–3.0 |
| **P5** | 跑管线 + 装配 pet pack | `$DSH_HOME/dsh-pet/pet/dachshund-animation/*.webm` + config | §7.3 全过 | $0 |
| **P6** | 集成验收 | Chrome/Firefox 实测 | §7.3 全过 | $0 |

> **P1 / P2 是硬门禁，失败即暂停**（用户第 6 条裁定，见 R1）：
> 四足站姿不达标 → **停止，上报用户**，不自动改走坐姿方案、不裁剪动作清单。
> P2 未通过前**禁止进入 P3/P4**（AGENTS.md §2「在产出首个可用结果前禁止批量」）。

> **P0a 是硬前置**：`chroma_step02.py:10` `import numpy`、`normalize_step03.py` 依赖 numpy，
> `watermark_step01.py:32` `from fill_nn import fill_nn`（后者用 scipy）。
> 本机**三个解释器都没有 numpy/scipy**（实测 `/opt/homebrew/bin/python3`、`/usr/bin/python3`、
> DSH-Novel 的 pixi python 全部 `ModuleNotFoundError`），**不建环境则 P0b 无法验收**。
> 按 AGENTS.md §2：用 `pixi`，**禁止系统全局安装**。

> **图像生成成本无法预估**：`~/.dsh/dsh-imagegen/index.json` 的条目字段是
> `id/createdAt/mode/model/prompt/size/quality/detail/n/images/refName/channelId/channel`，
> **不含任何费用或用量字段**（实测 4 条记录，无 `cost`/`usage`/`price`/`billing`）。
> 故 P1/P3 那几张图的**成本未知**，需查网关账单或按上游定价自行换算。
> 先前草稿写的「~$0.02/张、合计 ~$0.9」**没有依据，已删除**。
>
> **H3 部分**：20 次调用 × 10 秒（≈$0.12–0.16/次）≈ **$2.4–3.2**，
> 但这是**每次独立**受 $3.00 预算约束，无累计保护（见 §5.2 注）。

> **P2 是强制门禁**：必须先用 1 个动作验证端到端（含桥接、抠像、归一化、装配、界面显示），
> 再批量生产。这是 AGENTS.md §2「MVP 导向」的直接应用——**在产出首个可用结果前禁止批量**。

## 9. 风险与未验证假设

| # | 风险 | 等级 | 现状 | 缓解 |
| --- | --- | --- | --- | --- |
| **R1** | **参考图是坐姿，计划假设四足站姿** | **高（硬门禁）** | **未验证**——尚未生成过四足站姿的基准图 | **无回退**（用户裁定第 6 条）：P1 若站姿不达标 → **立即暂停并上报**，不得改走坐姿方案 |
| **R2** | 20 个动作的**大小/位置一致性** | 中 | `normalize_step03` 靠首尾帧测量统一缩放，但每个动作的首帧是**独立生成**的，站立高度会有差异 | §7.2 的「首尾一致」检查；必要时统一裁切 |
| **R3** | 腊肠犬**矮脚长身**，四足站姿的「站立高度」定义易受姿态影响 | 中 | 未实测 | P2 单动作验证时测量 |
| **R4** | H3 的**首尾帧只是 best-effort**，不锁定 | 中 | 已实测：开头锚点由归一化比较支持（margin +0.0456），结尾锚点由吐舌特征支持 | 每段视频都做 §7.2 首尾检查，不达标则重做 |
| **R5** | 10 秒时长**未实测**（5 秒已 PASS） | 中 | 未实测 | P2 用 10 秒跑第一个动作 |
| **R6** | `events.balance` 的 6 个动作**语义可能太细**（狗难以表现 6 档富足度差异） | 低 | 未验证 | 允许降级为「6 个槽位复用较少动画名」（契约只要求非空）——**此项降级不需要用户再确认**（第 1 条已定 20 个动作，但槽位复用不改变动作总数） |
| **R7** | 生成图的**绿幕纯度成功率**（gpt-image-2 不稳定；本包只需 2 张） | 中 | 已实测 2 张均达标（本会话按「g>100 且 g-max(r,b)>40」重测：**0.7771 / 0.7412**） | 逐张验证，失败重生成 |
| **R8** | `turn` 类的**严格镜像**在四足上很难保证 | 中 | 未实测 | 可用图像工具对首帧做水平翻转生成尾帧，而非让模型自由生成 |
| **R9** | **macOS Safari / WKWebView 不认 webm alpha**（渲染为黑底） | 低（已接受） | README 已述（`:94`「不支持 Safari」），本机是 macOS | **用户裁定第 7 条：本轮只做 webm，接受此限制**。`.mov` 链路（`encode_hevc_alpha.sh` + `assets-mov`）**不投入**；验收仅在 Chrome / Firefox 进行 |
| **R10** | 右键菜单**硬编码**「碎碎念」项（`client/pet.ts:1288-1289`，**不受 `whisperEnabled` 门控**）；而 pet pack 配置里没有 `events.whisper` → 点击即报 `[dsh-pet] 配置缺少 animations.events.whisper`（`pet.ts:537-541`） | 低 | 已亲验代码 | 在 pet pack 的 `events` 里**补 `whisper` 池**，填**已存在**的动画名 `待机呼吸`（见 §5.3 骨架）——**不得填清单外的名字** |

## 10. 已知集成缺口（需先修，非本计划新增）

| # | 缺口 | 影响 | 处置 |
| --- | --- | --- | --- |
| **G1** | **8 个脚本硬编码 Windows ffmpeg 路径** `.tools/ffmpeg-9.0.1-essentials_build/bin/*.exe` | 本机（macOS）全部跑不了 | P0b 修全部 8 个（含 step03/step04 用的 `normalize_step03.py`、`encode_thumbs.py`）：改为环境变量或 PATH 探测。**已授权**（第 3 条），但**只留本地** |
| **G2** | `chroma_step02.py` **同名常量双份定义**（`:25-28` 与 `:38-41`），两套互不引用 | 调参时易只改一半 | P0b 修：合并为单一来源。**已授权**，只留本地 |
| **G3** | **缺 864×480 → 1280×720 桥接** | 不修则 `chroma_step02` 静默错位 | **P0b 核心任务**。已授权，只留本地 |
| **G4** | `test/pet1/` **未纳入 git 跟踪**，未接入 CI | 测试资产无版本管理 | **已裁定：不纳入**（第 5 条）→ 关闭。需补 `.gitignore` 条目防止误提交 |
| **G5** | 本机**无 numpy/scipy**（三个解释器都没有） | 管线脚本依赖 numpy | **已裁定：建 pixi 环境**（第 4 条）→ 转为 P0a 正式任务 |
| **G6** | ~~fork 未建立 / 本地 remote 未切换~~ | — | **✅ 已解决**：`origin` → `dale0525/dsh-pet`，`upstream` → `PC2005-cloud/dsh-pet`，`main` 跟踪 `origin/main`（见 §11「前置」）。默认 push 只写 fork |

> **G1/G2/G3 已获授权修改**（用户第 3 条），但改动**只留本地、不提交上游**；
> 长期维护走「fork 到自有仓库」路线。**remote 已完成切换**（见 §11 前置）：`origin` = 自有 fork，
> `upstream` = 上游；`git push` 只写 fork。**但本计划仍不主动 push 任何东西**。
>
> **`.gitignore` 待补条目**（本轮只落盘计划，未执行）：**只补 `.pixi/`**（pixi 的环境目录）。
> `pixi.toml` **应当入库**——它是环境定义（依赖清单），不是本地产物；忽略它会让环境不可复现。
> `test/pet1/` 按第 5 条裁定**不纳入 git**，需补 `test/` 忽略条目。
> 另：工作区已有前序「透明背景探测」遗留的未跟踪目录 `dsh-image-gen/`（3 张 PNG，时间戳 Sep 13），
> 与本次计划无关，后续一并忽略或清理。
>
> **2026-09-15 已执行（见 §19）**：`.pixi/` 与 `test/pet1/` 的忽略条目已补；
> `pixi.toml` 已入库；`dsh-image-gen/` 已**删除**（不再是「忽略」而是「清理」）；
> pet pack 的资产与工具已迁至 `pets/dachshund/` 并入库。

## 11. 用户裁定（已冻结，2026-09 定稿）

| # | 问题 | **裁定** | 对本计划的影响 |
| --- | --- | --- | --- |
| 1 | 动作数量 | **20 个**（含 6 个余额档位） | §6 清单全量保留，不再考虑最小集 11 个 |
| 2 | 时长 | **10 秒** | 全部 20 段按 10 秒生成（`generation_frames=243`）；§5.2 的成本按 10 秒估 |
| 3 | 是否授权改上游 `scripts/` | **授权，但改动只留本地，不提交上游**；改为 **fork 上游后在自有仓库维护** | fork `dale0525/dsh-pet` 已建立、本地 remote **已切换完成**（见下方「前置」）。`git push` 只写 fork；**本计划不主动 push** |
| 4 | 是否建 pixi 环境 | **建** | P0a 转为正式任务。**`pixi.toml` 入库、`.pixi/` 忽略**（与 §10 一致） |
| 5 | `test/pet1/` 是否纳入 git | **不纳入** | G4 关闭为「按裁定不纳入」；需补 `.gitignore` 条目以免误提交 |
| 6 | R1 失败时的回退方案 | **不接受回退**——若四足站姿不达标就**暂停** | R1 的缓解由「回退到坐姿」改为「**停止并上报**」。**无 fallback**，P1 是硬门禁 |
| 7 | 是否产出 Safari 用 `.mov` | **只做 webm** | R9 保留为「已知限制」，不投入 mov 链路；`.mov` 链路（`encode_hevc_alpha.sh` 等）本轮不碰 |

### 前置：remote 切换**已完成**（第 3 条已落地）

裁定要求「fork 上游后改为在自己仓库维护」。fork 由用户 2026-09 建立，本地 remote 切换随后执行完毕。

**fork 的已核实事实**：

| 项 | 值 | 来源 |
| --- | --- | --- |
| fork 仓库 | `dale0525/dsh-pet` | 用户提供 + GitHub API |
| `fork` 标志 | **`true`** | `api.github.com/repos/dale0525/dsh-pet` |
| fork 的 parent / source | `PC2005-cloud/dsh-pet` | 同上（确认是上游的 fork，非新建仓库） |
| fork 默认分支 | `main`，且**公开**（`private: false`） | 同上 |
| fork `main` 的 sha | `6180c8ad28c8e36fd97880b719167657a21c805e` | `api.github.com/.../commits/main` |

> **三方同一 commit**（`6180c8a`）：本地 HEAD、`origin/main`（fork）、`upstream/main` 全部相同，
> 领先 0 / 落后 0——fork 是上游的干净镜像。**切换不涉及任何提交或推送，不会丢任何东西。**

**执行前基线**（回滚基准）：

```
$ git remote -v
origin  https://github.com/PC2005-cloud/dsh-pet.git (fetch)     ← 仍是上游
origin  https://github.com/PC2005-cloud/dsh-pet.git (push)
$ git branch -vv
* main 6180c8a [origin/main] fix(notify): ...                  ← 仍跟踪上游
```

**执行的 3 步**：

```sh
git remote rename origin upstream                                  # 1. 上游改名，保留拉取能力
git remote add origin https://github.com/dale0525/dsh-pet.git      # 2. origin 指向自己的 fork
git fetch origin                                                   # 3. 取回 fork 引用（origin/main 此前不存在）
git branch --set-upstream-to=origin/main main                      # 4. 跟踪切到 fork
git remote set-head origin -a                                      # 5. 补 origin/HEAD → main
```

> 第 3 步是必要的：`git remote add` **不会**自动创建 `refs/remotes/origin/*`，
> 不先 fetch 就执行 `--set-upstream-to=origin/main` 会报 unknown branch。

**切换后状态（已核实）**：

| 项 | 值 |
| --- | --- |
| `git remote -v` | `origin` → `dale0525/dsh-pet`；`upstream` → `PC2005-cloud/dsh-pet` |
| **默认 push 目标** | **`origin` = `https://github.com/dale0525/dsh-pet.git`** ✅ |
| `main` 跟踪 | `[origin/main]` |
| `git rev-parse --abbrev-ref main@{upstream}` | `origin/main` |
| 本地 HEAD / `origin/main` / `upstream/main` | 三者同为 `6180c8ad28c8e36fd97880b719167657a21c805e` |
| upstream 拉取能力 | `git fetch upstream --dry-run` 退出码 0（保留） |

**安全结论**：`git push` 现在**只会写 `dale0525/dsh-pet`**；上游只能通过显式
`git push upstream ...` 触达（不应使用）。**上游更新**走 `git fetch upstream && git merge upstream/main`。

> **仍然不做的事**：本计划**不主动 push 任何东西**。切换只解除了「误推上游」的风险，
> 不等于授权推送——是否提交、何时提交到 fork，仍由用户决定。

### 二创署名义务（fork 后仍然适用）

README 第 512 行明确：**「基于本项目的衍生 / 改版 / 换皮作品，在任何介绍、展示、分发该作品的地方，
须附上原作者 GitHub 地址」**（`https://github.com/PC2005-cloud/dsh-pet`）。
fork 与自有仓库维护**不豁免**该义务——后续若公开分发 pet pack，须保留署名。

## 12. 复现方式

> **2026-09-15 路径变更**：pet pack 的源资产与工具已从 `test/pet-dachshund/` 迁到
> **`pets/dachshund/`**（`pets/<种类名>/` 与运行时 `$DSH_HOME/dsh-pet/pet/<种类名>-{config.json,animation/}`
> 一一对应）。目录深度不变，各脚本的 `REPO_ROOT = parents[2]` 仍解析正确。
> H3 成片由 `p2/p3/p4-h3-out/<动作>/output.mp4` 三级嵌套**扁平化**为 `pets/dachshund/h3/<动作>.mp4`，
> 成本溯源记录同步为 `pets/dachshund/reports/<动作>.json`。见 §19。

```sh
# 本仓库自带 pixi 环境（P0a 建；numpy/scipy/pillow/ffmpeg 都在里面），不再依赖外部工程的解释器
cd /Volumes/LogicExt/Git/dsh-pet

# 现有 5 秒验证产物（test/pet1/ 按 §11 裁定 5 不入 git，需先放回）
pixi run python -m unittest discover -s test/pet1 -t test/pet1              # 29 项
pixi run python test/pet1/evaluate_h3_pet1.py test/pet1/h3-out/output.mp4   # 退出码 0 = PASS

# 腊肠犬绿幕链（P1/P2 验收）——pet pack 源资产与工具都在 pets/dachshund/
pixi run python pets/dachshund/test_bridge_step00.py
pixi run python pets/dachshund/test_scripts_tools.py
pixi run python pets/dachshund/test_frame_plate.py
pixi run python pets/dachshund/test_resume_truncation.py
pixi run python pets/dachshund/test_evaluate_dachshund.py
pixi run python pets/dachshund/evaluate_dachshund.py frames pets/dachshund/frames/base-standing.png
pixi run python pets/dachshund/evaluate_dachshund.py video pets/dachshund/h3/待机呼吸.mp4 --seconds 10
```

---

## 13. 评审记录（AGENTS.md §3）

**里程碑**：本设计文档初稿完成。

### 13.1 Root 自审（先于盲审）

自审按「重复/冲突/矛盾/遗漏/过度设计」五维进行，**发现并就地修正 4 处自身缺陷**：

| # | 缺陷 | 修正 |
| --- | --- | --- |
| S1 | 动作总数写作「107 条」，实为 **106**（107 个 `##` 标题含 1 个 `通用前缀`） | 改为 106 并注明口径 |
| S2 | 称 `idle` 为「必填」，但校验层允许空数组 | 改为「校验通过≠功能可用」：空 `idle` 池会使 `pick()` 返回 `undefined` |
| S3 | 称「权重合计=100 是硬约束」 | 实测 `weightsValid()` 只查非负有限数，**不校验合计**；改为「注释约定，写错静默偏移」 |
| S4 | 图像生成成本写「~$0.02/张、合计 ~$0.9」 | `index.json` 无任何费用字段 → **无依据，已删除**，改为「未计价」 |

另修正引用口径：两张首尾帧绿幕占比由引用旧文档的 `0.7759/0.7396` 改为**本会话重测**的 `0.7771/0.7412`（阈值口径不同）。

### 13.2 子代理盲审

- **席位**：`antigravity/gemini-3.8-flash`（AGENTS.md §3 唯一真源）
- **首轮**：返回空白 → **按规则向同一席位重试一次**（第 2 次成功）
- **发现总数**：**17 条**（严重 3 / 中等 8 / 轻微 6）

### 13.3 逐条裁定

| 发现 | 维度 | 裁定 | 处置 |
| --- | --- | --- | --- |
| 2.1 | 冲突（严重） | **采纳** | §3「姿态基准」由「坐姿」改为「四足站姿」，与下文一致 |
| 2.2 | 冲突（严重） | **采纳** | §4 链路图 ④ 由 `video/` 改为 `step01/`，并加注 `video/` 全程不参与 |
| 3.1 | 矛盾（严重） | **部分采纳** → 辩论 → **让步** | 采纳「权重表述有歧义」与「`categories` 结构遗漏」；驳回「文档把 categories 当平铺数组」 |
| 3.2 | 矛盾（中等） | **采纳** | 补 `normalize_step03.py:33-34` 同样硬编码 1280×720，并说明桥接为何仍须在 step02 前 |
| 3.3 | 矛盾（中等） | **采纳** | pet pack 路径改为 `$DSH_HOME/dsh-pet/pet/` 绝对路径，补 `host/index.ts:178-181` 依据 |
| 3.4 | 矛盾（中等） | **部分采纳** → 辩论 → **让步** | §2 改为双来源表格，明确区分「ACTION-DESIGN.md 记生图探测」与「本次核验记 VAE/ComfyUI」 |
| 2.3 | 冲突（中等） | **采纳** | §6.3 新增「三类例外」：`turn` 类首帧必须偏侧，**豁免**首帧统一性 |
| 2.4 | 冲突（中等） | **采纳** | §6.3 明确趴卧类尾帧必须起身回站姿（否则 `standing["height"]` 被拉低致畸形放大） |
| 4.1 | 遗漏（中等） | **采纳** | §5.3 补完整配置骨架（`pets` 必填字段、`moves.default`、`Category[]` 结构） |
| 4.2 | 遗漏（中等） | **采纳** | 新增 **R9**（Safari webm alpha 黑底 → `.mov` 方案），§7.3 验收注明浏览器范围 |
| 4.3 | 遗漏（中等） | **采纳** | §8 拆出 **P0a 建 pixi 环境**，并说明为何是硬前置 |
| 5.1 | 过度设计（中等） | **部分采纳** → 辩论 → **让步** | 保留清单（用户明确要求「≥10 个动作的完整计划」）；补「20 条是已定稿清单」并指向 P2 门禁 |
| 1.1 / 1.2 / 1.3 | 重复（轻微） | **部分采纳** → 辩论 → **让步** | 保留「正文 + §12 证据索引 + §9 风险 + §11 未决」的结构分工，正文去重 |
| 4.4 | 遗漏（轻微） | **采纳** | 新增 **R10**（右键硬编码「碎碎念」→ 缺 `events.whisper` 会报错），§7.3 加验收项 |
| 5.2 | 过度设计（轻微） | **部分采纳** → 辩论 → **让步** | §7.1 保留 4 项定量（纯度/均值/平坦度/构图），毛色直方图与连通域检测**降级为人工目视** |

**裁定统计**：采纳 11 条、部分采纳 6 条。

### 13.4 辩论轮（AGENTS.md §3 强制）

凡判「不采纳/部分采纳」的 5 组条目（3.1、3.4、5.1、5.2、1.x），均向**同一审查席位**提交原判、Root 反驳与证据，要求逐条以「让步」或「坚持 + 具体证据」作答。

**结果**：`共识状态：全部让步`（5/5）。

| 条目 | 审查席位结论 | 关键理由 |
| --- | --- | --- |
| 3.1 | 让步 | §6.1 表列名确为「数量」，正文未将 `categories` 描述为平铺数组 |
| 3.4 | 让步 | §2 原文为「ACTION-DESIGN.md **与本次核验**」并列结构，非单一引证 |
| 5.1 | 让步 | §8 P2 强制门禁 + §6.2「不视为冻结」已构成防过早批量 |
| 5.2 | 让步 | 首尾帧是 `normalize_step03` 唯一输入，输入缺陷致全量返工；已采纳精简 |
| 1.x | 让步 | 属规格文档「契约分析/风险登记/待决决策/证据索引」的标准分工 |

**无共识破裂**，无需上报用户裁定。

### 13.5 定稿裁定（2026-09，用户对 §11 的 7 项逐条裁定）

盲审与辩论闭环后，文档以「未决问题」形式向用户提交 7 项待裁定项。用户**全部裁定**，本计划据此定稿：

| # | 裁定 | 落地位置 |
| --- | --- | --- |
| 1 | 20 个动作 | §1、§6.1（「蓝本清单」→「已定稿清单」） |
| 2 | 10 秒 | §1、§5.2、§8 P2/P4 |
| 3 | 授权改 `scripts/`，但**只留本地不提交上游**，改走 fork 自有仓库维护 | §10 G1/G2/G3、§11 前置、新增 **G6** |
| 4 | 建 pixi 环境 | §8 P0a 转为正式任务、§10 G5 关闭 |
| 5 | `test/pet1/` **不纳入** git | §10 G4 关闭 |
| 6 | R1 失败**不回退，暂停** | §9 R1（缓解改为「无回退」）、§8 P1/P2 门禁 |
| 7 | 只做 webm，不做 `.mov` | §9 R9 降级为「已接受限制」、§7.3 验收限 Chrome/Firefox |

**本轮新发现的障碍（Root 自审，非盲审提出）**：

| # | 发现 | 证据 | 处置 |
| --- | --- | --- | --- |
| N1 | **fork 尚未建立，`origin` 直指上游本体**——第 3 条裁定要防的风险此刻是**实时存在**的 | `git remote -v` → `origin https://github.com/PC2005-cloud/dsh-pet.git`；`git branch -vv` → `main [origin/main]`；`git log` 作者统计 95/100 为上游 `pc2005` | 新增 **G6** 与 §11「前置」处置；**完成前禁止 push** |
| N1′ | **N1 的后续：fork 已由用户建立**（`dale0525/dsh-pet`，`fork:true`，parent 与 source 均为 `PC2005-cloud/dsh-pet`）；但**本地 remote 仍未切换**，push 风险**依旧存在** | `api.github.com/repos/dale0525/dsh-pet` → `fork:true`、`default_branch:main`、`private:false`；fork/本地/上游三者 main 同为 `6180c8ad28c8e36fd97880b719167657a21c805e`；`git remote -v` 仍显示上游 | G6 改为「本地待切换」；§11 前置缩为 **3 步**（`remote rename` → `remote add` → `set-upstream-to`） |

> ⚠️ **N1 / N1′ 是当时的快照，均已被取代**：本轮（§13.8）remote 切换已执行完毕，
> G6 **已关闭**。此处保留原文仅为留下裁定轨迹，**不代表当前状态**——以 §11 前置与 §13.8 为准。

> **本轮为「只落盘计划」**（用户明示「继续落盘计划文档，暂时不开工」）：
> 仅修改本文档，**未创建** `pixi.toml`、**未修改** `scripts/`、**未动** `.gitignore`、**未执行**任何 `git push`。
> §11 前置的 **3 步 remote 切换亦未执行**——本地 `origin` 仍指向上游，待用户确认后另行开工。
>
> 工作区另有前序遗留的未跟踪目录 `dsh-image-gen/`（3 张 PNG，时间戳 Sep 13 21:42–21:47，
> 属更早的「透明背景探测」产物）与 `test/`——与本次计划的生产工作无关。

### 13.6 第二轮盲审（fork 状态与裁定落地后）

**触发**：§11 的 7 项裁定落地 + fork 状态更新后，文档实质变更，按 §3 重新盲审。

- **席位**：`antigravity/gemini-3.8-flash`（首次调用被中断、结果未知；核查无遗留运行代理后重试）
- **发现总数**：**12 条**（严重 2 / 中等 4 / 轻微 6）

**Root 自审先发现的缺陷**（本轮 Root 自己改文档时引入）：

| # | 缺陷 | 修正 |
| --- | --- | --- |
| T1 | 编辑残留：旧小节标题「⚠️ 前置：fork 尚未建立」未被删除，与新增小节并存 → **文档出现两个并列前置节** | 删除旧节，仅保留「fork 已建立，但本地 remote 尚未切换」 |
| T2 | `§6` 标题仍写「≥12 个」，与第 1 条裁定的 20 个不符 | 改为「20 个，已定稿」 |

**逐条裁定**：

| 发现 | 维度 | 裁定 | 处置 |
| --- | --- | --- | --- |
| 2.1 | 冲突（严重） | **采纳** | §11 裁定 4 与 §10 注直接对立 → 统一为「`pixi.toml` 入库、`.pixi/` 忽略」，并澄清「只落本地」≠「不入 git」 |
| 2.2 + 4.1 | 遗漏+冲突（严重） | **采纳** | R10 建议复用的 `发呆放空轻哼` **不在 20 条清单内**（会 404）→ 改为复用清单内真实存在的 `待机呼吸`；§5.3 骨架补 `events.whisper` |
| 3.1 | 矛盾（中等） | **部分采纳** → 辩论 → **让步** | 接受修正措辞：写权限**未验证**，故「push 目标仍是上游；被拒或写入均不可接受」（而非断言「会写入」） |
| 3.2 | 矛盾（中等） | **部分采纳** → 辩论 → **让步** | 接受补充澄清：遗留的 `dsh-image-gen/`（Sep 13）属前序探测，与「本轮只改文档」不冲突 |
| 4.2 | 遗漏（中等） | **采纳** | P0b 验收由「到 step02」扩为「**跑通全链到 step04**」，覆盖 `normalize_step03.py`/`encode_thumbs.py` 的 Windows 路径修复 |
| 5.1 | 过度设计（中等） | **采纳** | `test/pet-dachshund/` 从零重写单测属过早工程化 → 改为**复用/扩展现有 `test/pet1/` 的评估器** |
| 3.3 | 矛盾（轻微） | **采纳** | `config.ts:49-98` 实为 `stripJsonc`/`readJsonc`/`scanPetFiles`（**行号错误**）→ 改为 `:276-372`（`mergePets` + `petNumber`/`petBool`/`petEnum`） |
| 2.3 | 冲突（轻微） | **采纳** | 「≥12」与「≥10」基准冲突 → 统一为「原始要求 ≥10，裁定取 20」；废弃的最小集推导降级为标注「仅供参考」 |
| 1.1 / 1.2 / 1.3 | 重复（轻微） | **部分采纳** → 辩论 → **让步** | 精简正文散论，保留 §4/§5/§9/§11/§13 的结构性分工 |
| 5.2 | 过度设计（轻微） | **部分采纳** → 辩论 → **让步** | 保留「片内水平漂移」门禁（`normalize_step03.py:126` 的 `overlay_x` 是**全局单值**，不逐帧居中，故该检查不可省）；非关键项标 advisory |

**裁定统计**：采纳 6 条、部分采纳 4 条（2 组独立）、轻微重复 3 条合并为 1 组。

### 13.7 第二轮辩论

对判为「部分采纳」的 4 组（3.1、3.2、5.2、1.x）向**同一审查席位**提交原判、Root 反驳与源码证据。

**结果**：`共识状态：全部让步`（4/4）。

| 条目 | 审查席位结论 | 关键理由 |
| --- | --- | --- |
| 3.1 | 让步 | 作者已把未经测试的「确称」改为「目标指向上游、写权限未验证」，核心约束不变 |
| 3.2 | 让步 | `dsh-image-gen/` 时间戳早于本次规划，属前序遗留；生产资产零改动 |
| 5.2 | 让步 | `normalize_step03.py:126,131` 证实 `overlay_x` 是**全局单值常量**，无法校正片内漂移 |
| 1.x | 让步 | 流程图/契约分析/风险登记/裁定跟踪属规格文档标准分工，承载不同追溯职责 |

**无共识破裂**，无需上报用户裁定。

### 13.8 remote 切换执行记录（用户授权后）

**授权**：用户 2026-09 建立 fork `dale0525/dsh-pet` 后，指令「执行 remote 切换，完成后暂时不开工」。

**执行的 4 步**（比原计划的 3 步多一步，原因见下）：

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `git remote rename origin upstream` | ✓ 上游改名；`branch.main.remote` 自动变为 `upstream` |
| 2 | `git remote add origin https://github.com/dale0525/dsh-pet.git` | ✓ `origin` 指向 fork |
| 3 | `git fetch origin` | ✓ 新建 `refs/remotes/origin/main` |
| 4 | `git branch --set-upstream-to=origin/main main` | ✓ `main` 跟踪 `origin/main` |
| 5 | `git remote set-head origin -a` | ✓ `origin/HEAD` → `main` |

> **第 3 步是原计划遗漏的必要步骤**：`git remote add` **不会**自动创建 `refs/remotes/origin/*`，
> 若直接执行第 4 步会报 `unknown branch`。已写入 §11 前置的步骤清单。

**切换后验证**（全部亲验）：

| 校验项 | 结果 |
| --- | --- |
| `git remote get-url --push origin` | `https://github.com/dale0525/dsh-pet.git` ✅ **默认 push 目标是 fork** |
| `git remote get-url --push upstream` | `https://github.com/PC2005-cloud/dsh-pet.git`（需显式指定才触达） |
| `git config branch.main.remote` | `origin` |
| `git rev-parse --abbrev-ref main@{upstream}` | `origin/main` |
| 本地 HEAD / `origin/main` / `upstream/main` | 三者同为 `6180c8ad28c8e36fd97880b719167657a21c805e` |
| `git fetch upstream --dry-run` | 退出码 0（上游拉取能力保留） |
| 工作区 | `?? docs/`、`?? dsh-image-gen/`、`?? test/`（与切换前一致，未受影响） |

**Root 自审发现的本轮缺陷**：

| # | 缺陷 | 修正 |
| --- | --- | --- |
| U1 | 重写 §11 前置时，**又出现双标题 + 旧代码块残骸**（与 13.6 的 T1 同类错误重犯） | 合并为单一小节，删除残骸 |

> **本轮仍为「不开工」**：只改文档 + 执行用户明确授权的 remote 配置。
> 未创建 `pixi.toml`、未修改 `scripts/`、未动 `.gitignore`、**未执行任何 `git push`**。

| 断言 | 来源（本会话亲验） |
| --- | --- |
| H3 输出 864×480/h264/yuv420p | `ffprobe h3-out/output.mp4` |
| H3 常量（4–15s、9 图、32000 字符） | `modal_h3_contract.py:88-98` |
| 提示词六段与校验规则 | `modal_h3_contract.py:109-183` |
| 桥接必需性（2764800 vs 1244160 字节） | `chroma_step02.py:21,162` + `normalize_step03.py:33-34,68` + 帧字节数计算 |
| 抠像可用（背景 74–79%、绿溢 0%） | 逐行复刻 `chroma_step02.py` 阈值跑 H3 实际帧 |
| H3 无角落水印 | 边框环 3×3 网格分布（非绿集中在中列上/下，四角纯绿） |
| 动画池校验规则 | `dsh-pet/src/host/config.ts:103-153` |
| `categories` 为 `Category[]` | `dsh-pet/src/shared/types.ts:41-46` |
| 空 `idle` 池 → `undefined` | `dsh-pet/src/shared/pickers.ts:5-10, 86-98` |
| 余额档位索引 | `dsh-pet/src/shared/balance.ts:159-163` |
| pet pack 素材解析与绝对路径 | `dsh-pet/src/host/index.ts:178-181, 567-574` + README「方式四」 |
| 右键硬编码「碎碎念」 | `dsh-pet/src/client/pet.ts:1288-1289` |
| normalize 的缩放逻辑 | `normalize_step03.py:85-106, 122-132, 196` |
| 8 个脚本硬编码 Windows ffmpeg | `grep -c` 逐个统计 |
| 本机无 numpy/scipy | 三个解释器逐个 `import` 测试 |
| 全库 106 条动作的四足适配分类 | 只读子代理逐条判定（1 直接可用 / 55 改写后可用 / 50 不适用） |

---

## 14. 实施记录（P0a–P2，2026-09）

> 本节只记录**已亲验**的事实（每条都有本会话实际执行的命令输出）。
> 未做：P3/P4/P5/P6（放量、装配 20 个动作、整链验收）。**未 git commit / 未 push**。

### 14.1 阶段状态

| 阶段 | 状态 | 产物 | 验收证据 |
| --- | --- | --- | --- |
| **P0a** 建 pixi 环境 | ✅ 完成 | `pixi.toml` | `pixi run python` 实测 python 3.12.14 / numpy 2.5.3 / scipy 1.18.1 / pillow 12.3.0；`ffmpeg`/`ffprobe` 解析到 `.pixi/envs/default/bin/` |
| **P0b** 桥接 + 修路径 + 去重 | ✅ 完成 | `scripts/_tools.py`（新）、`scripts/bridge_step00.py`（新）、8 个脚本改走 `_tools`、`chroma_step02.py` 常量合并 | 用 `test/pet1/h3-out/output.mp4` 跑通 step01→02→03→04：step01 h264 1280×720 → step02 vp9 1280×720 → step03 vp9 2160×1215 → step04 vp9 640×360，alpha 实测 min 0 / max 255 / 透明像素 83.77% |
| **P1** 标准首帧 | ✅ 通过 | `test/pet-dachshund/frames/base-standing.png`（1672×941） | §7.1 四项定量全过：背景 0.8305、均值 (3.8, 248.9, 7.1)、标准差 (8.2, 3.2, 3.3)、水平中心 0.4856、高度占比 0.8151 |
| **P2** 单动作端到端（10 秒） | ✅ 通过（2 项 §7.3 行不可判，见 14.4） | `test/pet-dachshund/p2-h3-out/output.mp4`、`$DSH_HOME/dsh-pet/pet/dachshund-{config.json,animation/待机呼吸.webm}` | §7.2 九项全过（见 14.3）；§7.3 见 14.4 |
| §7.4 评估器门禁 | ✅ 完成 | `test/pet-dachshund/evaluate_dachshund.py` + `test_evaluate_dachshund.py` | 8 项单测通过；`test/pet-dachshund/` 全量 discover 15 项通过；`test/pet1/` 29 项回归通过 |

### 14.2 P1 的路线偏离（新事实，需登记）

图像生成网关的**图生图保持输入宽高比**：输入 `test/pet1/target-dog.png` 是 390×520（0.75），
请求里写 `size=16:9` **被忽略**，产出仍是 1086×1448（0.75）。而 H3 与下游链路全是 16:9。

处置：新增 `scripts/frame_plate.py`，**不触碰主体像素**，只按实测背景中位色（`#03F907`）在左右补纯色凑成 16:9，
再 lanczos 缩放到 1672×941（与已验证的 `test/pet1/frames/` 同尺寸）。补色取中位色而非写死 `#00FF00`，
是为避免底板出现两种绿导致「绿幕平坦度」不达标——实测补白后标准差 17.2 → 8.2（阈值 ≤15）。

> 这条偏离**不改动作清单、不改契约**，只是在「生成」与「H3 参考帧」之间插一步确定性装配。
> P3 的偏侧首帧将复用同一脚本（整包只需 2 张图，其余复用 `base-standing.png`）。

### 14.3 P2 的 H3 与视频级验收

- 请求：`agentnovel_modal_h3.py run --duration-seconds 10`，两张参考图（同一张基准图 = 首尾帧一致），
  `generation_frames=243` / `output_frames=240`（与 §5.2 契约一致）。
- 实测成本 **$0.128303**（预估区间 $0.12–0.16 命中）；worker 73.9s / modal 85.3s。
- §7.2 九项全过：容器 864×480 / 24fps / 10.000s / h264；5 点绿幕占比 0.8242–0.8359；
  抠像背景 0.8277 / 前景 0.1615；绿溢 1.618%；首尾高度差 0.21%、水平中心差 0.12%；零位移极差 0.029。

### 14.4 §7.3 逐行结论（P2 单动作 pack）

| 行 | 结论 | 证据 |
| --- | --- | --- |
| 每个 `.webm` 可被浏览器透明渲染 | ✅ | Chromium 内取像素：角落 `(0,0,0,0)`、狗身 `(193,98,42,255)`；拼色棋盘背景透出；DSH Web GUI 内实测无黑底/绿底 |
| 动画池配置通过校验 | ✅ | 宿主 `GET /dsh-pet-7340/config` 返回含 `dachshund` 条目；交互全程控制台异常/警告 **0** |
| 每个池的动画可播（非 404） | ✅ | `GET /dsh-pet-7340/thumb/dachshund/待机呼吸.webm` → 200 video/webm；不存在名 → 404（无回落）；右键菜单各池子项均可点播 |
| 待机循环自然 | ✅ | 对 `step04/待机呼吸.webm` 首帧(0s) vs 尾帧(9.9s) 逐像素实测：轮廓 IoU **0.9856**、共同主体区 RGB 平均绝对差 **6.68/255**、脚底线 328→328（完全一致）、水平中心 312.0→312.5（0.5px）——循环无跳变 |
| `turn` 真的翻转朝向 | ⛔ 不可判 | 需偏侧首帧（§6.3 例外），属 P3/P4 |
| 余额档位不报越界 | ✅ | 余额触发路径无控制台错误，气泡正常渲染 |
| 缩放一致性 | ⛔ 不可判 | 需 20 个动作并排，属 P5/P6 |
| 右键「碎碎念」不报错 | ✅ | 点击后 0 异常/警告（R10 缓解生效：pack 的 `events.whisper` 非空） |

**P2 的 pack 是临时装配**：单动作阶段把 `idle/turn/drag/clicks/moves/categories/events.balance(×6)/events.whisper`
全部指向 `待机呼吸`（契约要求每池非空），P5 会整体替换为 20 动作的正式配置。

### 14.5 与 §10 的两处口径修正

| 项 | §10 原文 | 实施 | 理由 |
| --- | --- | --- | --- |
| `.gitignore` | 「需补 `test/` 忽略条目」 | 补的是 `test/pet1/` | 第 5 条裁定的对象是 `test/pet1/`；而 §7.4 的评估器落在 `test/pet-dachshund/`，忽略整个 `test/` 会让该门禁产物不可追踪 |
| 桥接的 16:9 校验 | 我最初的派单要求「偏差 > 0.01 即报错」 | 实现为：`(864,480)` 显式放行 + 其余容差 0.03 | H3 契约输出 864×480 实为 **1.8:1**，与 16/9 差 0.0222——按 0.01 报错会把唯一合法输入拒掉（派单口径自相矛盾，实现按事实修正并写进 docstring） |

### 14.6 P5 装配待办（本轮发现，尚未处置）

| # | 项 | 现状（亲验） | 处置方向 |
| --- | --- | --- | --- |
| A1 | pack **继承了主宠物的拟人化文案** | `GET /dsh-pet-7340/config` 的 `dachshund` 条目里 `whisperPrompt` 仍是「你是主人桌面上的Q版蓝发小女仆…」、`workStatusTexts` 6 组也全是女仆台词（`mergeEntry` 用 base 兜底） | P5 在 `dachshund-config.json` 里**显式写**犬向 `whisperPrompt` 与 `workStatusTexts` |
| A2 | 首尾帧数量口径 | §6.3 自身写「除 `turn` 类外，首帧都应是**同一张**四足站姿基准图」，而 §5.4 通用前缀又要求「最后一秒必须恢复到与第一帧**完全一致**」——两条合起来 ⇒ 18 个动作的**首尾帧是同一张图**；§6.3 的「20 × 2 = 40 张」是算术口径失误 | **P3 实际需要生成的图：`turn` 专属偏侧首帧 1 张 + 其水平镜像尾帧（PIL 翻转，非生成）**；其余 18 个动作直接复用 `base-standing.png`。这样同时把 §7.3「缩放一致性」（`normalize_step03` 按首尾帧测站立高度统一缩放）的风险降到最低 |
| A3 | `physics.petCollision` 默认 false | 实测两只宠物（主宠物 462px、腊肠犬 420px）都停在右上角同一位置，**画面重叠** | 与素材无关，属宿主物理设置；P6 验收前决定是否开启 |

---

## 15. 评审记录（P0a–P2 里程碑，2026-09）

### 15.1 Root 自审（先自审、就地修正）

| # | 自审发现 | 处置 |
| --- | --- | --- |
| S1 | 派单给桥接脚本的口径**自相矛盾**：「偏差 > 0.01 即报错」与「H3 输出 864×480 是唯一合法输入」不能同时成立（864/480 = 1.8，差 0.0222） | 实现按实测事实修正为 `(864,480)` 显式放行 + 其余容差 0.03，并写进 docstring 与报错文案（§14.5、`scripts/bridge_step00.py:10-12`） |
| S2 | P1 生成出的底板是 3:4 而非 16:9——网关对图生图**保持输入宽高比**，`size=16:9` 被静默忽略 | 新增 `scripts/frame_plate.py`：只补背景色不碰主体，装配成 16:9（§14.2） |
| S3 | §14.4 初稿把「待机循环自然」判为「单动作不可判」——这是**该判而未判** | 补做首/尾帧逐像素实测（IoU 0.9856、RGB 差 6.68/255、脚底线一致），改判 ✅ |
| S4 | 装好 pack 后发现两只宠物都停在右上角**画面重叠** | 记为待办 A3（属宿主 `physics.petCollision=false`，与素材无关） |
| S5 | pack 经 `mergeEntry` 兜底后**继承了主宠物的女仆文案**（`whisperPrompt`/`workStatusTexts`） | 记为待办 A1（P5 显式覆盖） |

### 15.2 盲审（独立席位，只给路径与维度）

- 审查席位：独立子代理（`antigravity/gemini-3.8-flash`），仅提供产物路径清单与五个维度（重复/冲突/矛盾/遗漏/过度设计），未提供任何背景、限制或额外指令。
- **盲审条目数：10**（2 项另附「经审查无缺陷」声明：H3 提示词、运行时 pack 产物）。

### 15.3 逐条裁定

| # | 盲审原判（维度） | 裁定 | 落地 |
| --- | --- | --- | --- |
| 1 | 【严重】门禁依赖未入库的 `test/pet1/`，干净克隆必崩（矛盾/遗漏） | **部分采纳** | 结论上不采纳「把 pet1 入库」或「复制一份度量」（§13.6 5.1 正是要避免重复）；采纳其可操作部分：两处依赖改为**显式报错 + 补救指引**，且保持 fail-closed 不 Skip（`evaluate_dachshund.py:31-44`、`test_bridge_step00.py:60-67`） |
| 2 | 【中】桥接容差与 docstring/报错文案脱节（矛盾） | **采纳** | `bridge_step00.py:10-12` 说明阈值来由；`:87` 报错文案改 `> 0.03` |
| 3 | 【中】`.gitignore` 漏 `step00/`；`pixi.lock` 未决（遗漏） | **部分采纳** | `step00/` 已忽略（`.gitignore:4`）；`pixi.lock` 判为**应入库**（可复现性真源），不忽略 |
| 4 | 【中】`_tools.py` 兜底硬编码外部工程私有路径（过度设计/冲突） | **采纳** | 删除 `DSH-Novel` 兜底目录（`scripts/_tools.py:26-30`） |
| 5 | 【中】`encode_thumbs.py` docstring 滞留旧版 1:1 规范（矛盾/重复） | **采纳** | 重写为 2160×1215 → 640×360 的真实现状，去掉不存在的 `crop_step01.py` 与 `assets/thumb/`（实为 `assets/webm/`，README:466 佐证） |
| 6 | 【中】`chroma_step02.py` 背景色采样无效 + 别名未清（过度设计） | **部分采纳** | 采纳：删掉未用的 `color` 形参、`bg` 死变量、`SATURATION_MIN`/`VALUE_MIN` 别名，单测改为断言旧别名**必须不存在**。不采纳删掉采样调用本身——它同时是 `:96-97` 的 fail-closed 前置门禁 |
| 7 | 【轻】`fill_nn.py` 无用 `dur` 形参 + `watermark_step01.py` 无意义时长探测（过度设计） | **不采纳**（本轮范围外） | 本轮对 `scripts/` 的授权仅 §10 的 G1/G2；该步在 H3 路线全程跳过（§5.1），无验收契约覆盖。可另开独立切片 |
| 8 | 【轻】`make_mask_black.py` 硬编码 Windows 绝对路径（冲突/遗漏） | **采纳** | 改为「命令行 → `DSH_PET_BLACK_VIDEO` → 历史默认」三级解析，取不到即报错（`make_mask_black.py:27-38`） |
| 9 | 【轻】§5.3 配置骨架漏 `name`（遗漏） | **采纳** | 骨架补 `"name": "腊肠犬"`（`types.ts:87` 佐证：缺 name 会告警并按 id 处理） |
| 10 | 【轻】§12 复现方式硬编码外部工程解释器（冲突/过时） | **采纳** | 改成 `pixi run python …`（本仓库 P0a 自建环境），并补齐 P1/P2 验收命令 |

**统计**：采纳 6 条（2、4、5、8、9、10）、部分采纳 3 条（1、3、6）、不采纳 1 条（7）。

### 15.4 辩论与共识（回合制）

对判为「部分采纳/不采纳」的 4 条（1、3、6、7），向**同一盲审席位**提交原判、Root 反驳与当时按规则未提供的事实（§1/§10/§11/§13.6 的既定裁定、采样函数的门禁职责、改动授权边界），要求逐条以「让步」或「坚持 + 具体证据」作答。

**结果**：`全部让步（4/4）`，无坚持、无共识破裂，无需上报用户裁定。

| 条目 | 审查席位结论 | 关键理由 |
| --- | --- | --- |
| 1 | 让步 | 复用 pet1 是 §13.6 5.1 的明文裁定，且 §1 排除 CI；防御指引与 fail-closed 已到位 |
| 3 | 让步 | `pixi.lock` 是跨机可复现的唯一真源，规则只要求忽略 `.pixi/` |
| 6 | 让步 | `chroma_step02.py:96-97` 证实该函数承担 fail-closed 门禁，删除会导致静默产出全不透明 webm |
| 7 | 让步 | 本轮改动严格限于 §10 授权；清上游非链路代码属超范围 |

### 15.5 评审后回归

- `pixi run python -m unittest discover -s test/pet-dachshund -t test/pet-dachshund` → **Ran 15 tests, OK**
- `pixi run python -m unittest discover -s test/pet1 -t test/pet1` → **Ran 29 tests, OK**
- 改动落地后**重跑整链**（chroma 签名已变）：bridge → chroma → normalize → thumbs 全过；
  `step04/待机呼吸.webm` alpha 实测 min 0 / max 255 / 透明占比 0.8608；重新装入 pack 后路由仍 **HTTP 200**（324262 字节）。

---

## 16. P3/P4 实施记录（2026-09）

### 16.1 P3：`turn` 的偏侧首尾帧（§6.3 唯一例外）

| 产物 | 内容 | §7.1 定量 |
| --- | --- | --- |
| `test/pet-dachshund/raw/base-standing-side-raw-1.png` | 图生图产出（1672×941，网关保持底板宽高比） | — |
| `test/pet-dachshund/frames/turn-side-left.png` | 偏侧首帧（身体朝自己的左转约 40°，四足站姿、头抬、吐舌、无道具） | bg 0.796→**0.8660**、std 9.4→…、cx 0.5000、h 0.8661，**PASS** |
| `test/pet-dachshund/frames/turn-side-right.png` | **严格水平镜像**尾帧（PIL 翻转，非生成） | 与首帧镜像**逐像素相等**（`reframe` 后仍成立） |

**为什么首帧要「偏侧」而不是正面**：`dsh-pet` 靠 `turn` 播完后翻转 `facing`（`dsh-pet/src/client/pet.ts:711-715`
+ `:273` `scaleX(-1)`）来换朝向。若首帧是正面对称姿态，镜像后还是正面，转向动作在语义上不成立（§6.3）。

**用库中原资产反证了这条约定**（实测，非推断）：对全库唯一 `turn` 资产 `dsh-pet/assets/webm/东张西望.webm`
取首/尾帧轮廓——**同向 IoU 0.8276、与尾帧镜像 IoU 0.9385**；非 turn 资产则是同向更高
（拖拽 0.9919、挥手 0.9575）。即「turn 尾帧 = 首帧镜像」是既有实现的事实约定，我们的产物遵守它。

### 16.2 P3 的 §7.2 结果（三次尝试，全部留痕）

| 尝试 | 改动 | 结果 | 成本 |
| --- | --- | --- | --- |
| v1 | 首版提示词（含「停顿回望」） | 零位移 **0.0903 > 0.08 不合格**（t=7.5s 尾巴甩出、抬爪使外接框左移） | $0.1240 |
| v2 | 收紧提示词：轮廓全程居中、头尾贴身、不甩出 | 零位移 **0.0729 合格**，但抠像前景 min **0.149 < 0.15 不合格** | $0.1340 |
| v3 | 底板 `reframe` 到 0.865（见 §16.3） | **§7.2 九项全过**：绿幕 0.774–0.829、抠像 bg 0.7788/fg 0.1676、绿溢 1.72%、首尾高度差 0.0021、中心差 0.0、零位移 0.0648 | $0.0758 |

**turn 专属收尾校验**（§6.3 要求尾帧 = 首帧镜像）：整链走完后在 `step04/原地轴转张望.webm` 实测
**首帧 vs 尾帧镜像 IoU 0.9411**（同向仅 0.5373），与库中原 turn 资产的 0.9385 同级 ✓。

### 16.3 系统性修正：底板主体放大到 0.865（`--fit-height`）

**发现**：H3 成片的「抠像前景占比」系统性**比底板低 20–26%**——h264 压缩把毛发边缘压成可判绿的像素。
实测映射（底板实测 → 成片实测）：P2 `0.1672 → 0.1615`、turn v2 `0.2009 → 0.149`。
而 §7.2 要求成片前景 **≥ 0.15**，于是所有动作都贴着阈值，turn/趴卧这类「投影面积更小」的姿态直接掉线。

**处置**：给 `scripts/frame_plate.py` 增加 `--fit-height`（`reframe()`），把主体放大到 0.865 高度占比后
再喂给 H3。实测底板高度 0.815→0.865 时前景占比 0.1672→0.1884、turn 0.2009→0.2244，
成片前景随之回到 0.1676（turn 实测）——**留出 ~12% 余量**。

> `reframe()` 有一个必须遵守的实现约束：**裁剪窗口只能由「外接框四周对称补 p 像素」构成，
> 不能写成「中心坐标 ± 半径」**。后者要做整数取整，而取整不是镜像对称的（差 1 像素），
> 会破坏 `turn` 首尾帧的严格镜像。这条由 `test/pet-dachshund/test_frame_plate.py::test_is_mirror_equivariant`
> 钉住（7 项单测，含 fail-closed 与「不切主体」）。

### 16.4 §5.4 与 §7.1 的构图口径冲突（记录，不擅自推翻）

- §5.4 要求「任意部位距画幅任意边 ≥10%」，同时又说「头顶 ~20%、脚底 ~85%」；
- §7.1 的门禁是「主体高度占比 ∈ [0.70, 0.90]」。

这三者互不相容：16:9 画幅里「四边各留 ≥10%」⇒ 高度占比 ≤ 0.80；而「头顶 20%/脚底 85%」⇒ 0.65，
**落在 §7.1 自己的 [0.70,0.90] 之外**。而 §7.2 记录的项目**实测基线**是高度占比 **0.8542–0.8812**
（即上下留白仅 6–7%）——说明本项目实际按「§7.1 的 [0.70,0.90] + 实测基线」执行，§5.4 的百分比是软措辞。

**本轮取值**：底板主体高度 **0.865**，落在 §7.1 门禁内、与实测基线同区间，且让 §7.2 的前景门禁有余量。
左右留白仍充裕（腊肠犬体宽约占画幅 40–50%，两侧各留 25%+），安全红线在水平方向完全满足。
若用户认为必须死守「四边 10%」，则高度上限 0.80，此时 §7.2 前景门禁对 turn/趴卧类会**结构性失败**——
需要用户裁定优先哪一条。

### 16.5 P4 放量的派单与复验

18 条提示词由 3 个只读范围受限的子代理分批撰写（每条各自独立，见 §3 派单口径），
Root 对 18 个文件逐个**重跑契约校验**（`dry-run`，$0）——**18/18 PASS**，无复验不通过项。
H3 生成与验收留 Root（共享 Modal 配额与预算，属共享可变状态），按 §6.2 建议**低风险优先**排序，
高风险的道具精细交互（#12/#13/#14）排最后。

### 16.6 P4 结果：18 条 H3 成片与 §7.2 门禁（逐条实测值）

> **读表须知（避免与 §16.9 的最终判定混淆）**：下表「判定」列的 ✅/⚠/❌ 是**按 §7.2 字面指标**逐条判的——
> ⚠ 表示未过的项全部落在「原始成片绿溢 / 抠像前景下限」这两条**后来由用户裁定改了口径**的指标上，
> ❌ 表示当时存在真实缺陷。**最终判定以 §16.9 的裁定为准（20/20 通过）**，
> 两个 ❌ 已按 §16.7 修复并复验，9 个 ⚠ 按 §16.8/§16.9 的证据放行。

全部 18 条一次生成成功（无 API 失败），均价 **$0.0639**；含 3 次返工共 **$1.1664**。

| 动作 | min 前景 | 位移 | 首尾高度差 | 绿溢 | 判定 |
| --- | --- | --- | --- | --- | --- |
| 兴奋拍打尾巴 | 0.1842 | 0.0740 | 0.0062 | 0.0184 | ✅ PASS |
| 凌空接吞零食 | 0.1791 | 0.0173 | 0.0062 | 0.0184 | ✅ PASS |
| 余额-鼻顶叮当 | 0.1777 | 0.0648 | 0.0021 | 0.0165 | ✅ PASS |
| 欢快蹦跳 | 0.1776 | 0.0498 | 0.0062 | 0.0197 | ✅ PASS |
| 余额-见底流汗 | 0.1736 | 0.0243 | 0.0042 | 0.0160 | ✅ PASS |
| 余额-缩水爪扒 | 0.1712 | 0.0162 | 0.0021 | 0.0184 | ✅ PASS |
| 受惊炸毛后缩 | 0.1548 | 0.0428 | 0.0062 | 0.0161 | ✅ PASS |
| 原地倒步踱行 | 0.1542 | 0.0567 | 0.0042 | 0.0184 | ✅ PASS |
| 余额-寻常轻嗅 | 0.1528 | 0.0671 | 0.0063 | 0.0175 | ✅ PASS |
| 爪拨玩具小车 | 0.1538 | 0.0278 | 0.0000 | **0.0219** | ⚠ 仅绿溢 |
| 哈欠连天甩头 | 0.1739 | 0.0394 | 0.0000 | **0.0201** | ⚠ 仅绿溢 |
| 单爪抬起招手 | 0.1770 | 0.0289 | 0.0021 | **0.0215** | ⚠ 仅绿溢 |
| 余额-满溢欢腾 | 0.1603 | 0.0058 | 0.0062 | **0.0475** | ⚠ 仅绿溢（横移已修） |
| 横向侧步滑行 | **0.1474** | 0.0440 | 0.0083 | **0.0202** | ⚠ 前景+绿溢 |
| 爪嘴并用拆礼物 | **0.1445** | 0.0625 | 0.0062 | **0.0238** | ⚠ 前景+绿溢 |
| 悬空提溜反馈 | **0.1384** | 0.0116 | 0.0062 | 0.0168 | ⚠ 仅前景 |
| 犬式伸懒腰 | **0.1308** | 0.0359 | 0.0146 | 0.0154 | ⚠ 仅前景（出框已修） |
| 余额-瘫趴叹气 | **0.1032** | 0.0625 | 0.0083 | 0.0183 | ⚠ 仅前景（趴卧） |

**结论：18 条里已无「几何/构图/穿模」类真实缺陷**（两个真实缺陷见 §16.7，均已修复并复验）。
余下 9 条的未过项全部落在 §7.2 的两条**代理指标**上（前景下限、原始成片绿溢），见 §16.8/§16.9。

### 16.7 两个真实缺陷：已修提示词 + 重跑 + 复验

1. **余额-满溢欢腾：主体横移 0.1400**（门禁 ≤0.08）。逐帧水平中心
   `0.498→0.499→0.503→0.388→0.374→…→0.364→…→0.504`——狗真的**绕过袋子走到画面左侧再走回来**。
   **根因在派单说明书本身**：我写给子代理的动作设定是「绕袋踏步狂摇尾巴」，模型忠实执行了「绕」。
   → 修：明确「始终面向袋子站在正前方、不绕行、不左右走动、回到画幅水平中心」。
   → 复验：位移 **0.0058** ✓，20 帧水平中心极差 **0.0752** ✓，贴边像素 0 ✓。
2. **犬式伸懒腰：中段出框**。t=4.5s 高度占比 0.960、**首行 46 个主体像素被画幅切掉**（上边距 0.0%），
   违反 §5.4 安全红线。第一次修（「镜头不推近、大小不变」）**未奏效**——出框源于「深弓背翘臀」把轮廓抬高。
   → 第二次修（改动作幅度）：把姿态从「深弓背翘臀」改为**受控幅度的地面伸展**，
   并给出可测上界「轮廓顶不得高过 <Picture 1> 的站姿头顶」。
   → 复验：最小边距 **5.0%**、贴边像素 **0**、高度占比 0.621–0.848 ✓，
   且这一次原始绿溢也从 0.0259 降到 **0.0154（通过）**。

   *教训（写给后续动作设计）*：腊肠犬身长腿短，任何「抬高后躯」的姿态都容易顶破画幅，
   动作设计必须给轮廓**高度上界**，而不只是给「边距 ≥10%」这种抽象约束。

### 16.8 交付物实测：§7.2 的绿溢门禁对本犬种是**代理偏高**

§7.2 的 `green_spill` 在**原始 h264 成片**上算「主体像素里偏绿的比例」。真正交付给 `dsh-pet` 的是
抠像后的 VP9-alpha 视频——偏绿的边缘像素在抠像时被判成半透明/透明，所以原始成片会**高估**用户可见绿边。

对全部 21 个 `step04/*.webm` 逐帧实测（alpha>128 的像素中「g−r>25 且 g−b>25」的比例，5 个采样点取最大）：

| 口径 | 范围 | 相对 §7.2 门禁 |
| --- | --- | --- |
| 原始成片绿溢 | 0.0160 – **0.0475** | 部分超标（9 条） |
| **交付物可见绿边** | **0.00055 – 0.00205** | **仅为门禁（2%）的 1/10 – 1/34** |

最差的两条：原始绿溢 0.0475 的「余额-满溢欢腾」，交付物绿边 **0.00145**；
原始 0.0351 的对照组同样 ≤0.0015。即 **7 条「绿溢超标」在交付物上没有可见绿边**。
同时注意**通过**的动作也都贴在上限边缘（0.0160–0.0197，最高达上限的 98.5%）——
2% 这条线本就压在本犬种分布的上沿（腊肠犬羽状长毛边缘比 `test/pet1` 基线主体更易被压成偏绿像素）。

### 16.9 两处口径冲突：已由用户裁定（2026-09-02）

**(A) 绿溢量在原始成片还是交付物 → 裁定：以交付物为准。**
用户选择「认定交付物无可见绿边即可，按证据放行」。
依据：21 个 `step04/*.webm` 实测可见绿边 **0.00055–0.00205**（门禁 2% 的 1/10–1/34），
最差的「余额-满溢欢腾」（原始 0.0475）在交付物上只有 **0.00145**。
→ §7.2 的「绿溢」判定口径改为**交付物**（见 §7.2 备注），**数值门槛 2% 不变**。
→ 受影响 **6 条**（爪拨玩具小车 0.0219、哈欠连天甩头 0.0201、单爪抬起招手 0.0215、
   余额-满溢欢腾 0.0475、横向侧步滑行 0.0202、爪嘴并用拆礼物 0.0238）**按交付物证据放行**，
   不重跑，零额外花费。
   （**不计** `犬式伸懒腰`：它返工后原始绿溢已降到 **0.0154**，本就通过；早期清单里把它算进去是
   沿用了返工前的 0.0259，属清单失误，已更正。）

**(B) 低位姿态的「抠像前景 ≥0.15」→ 裁定：该指标只对站立采样点生效。**
用户选择「低位段免测，只量站立采样点」，**数值门槛 0.15 不变**。
低位段（趴卧 / 贴地伸展 / 悬空）改判两项：**绿幕占比 ≥0.70、无穿模（贴边像素 = 0）**。
实测这 3 条低位段的两项均达标（见 §16.7 的几何复验：伸懒腰最小边距 5.0%、贴边像素 0）。

**"站立采样点"的可执行定义**：首帧（t=0）与末帧（t=9.9）——§5.4 要求末帧必须完全回到首帧姿态，
所以这两点必然是最无争议的四足站姿。裁定后逐条实测（本轮补测，见 §17.6）：

| 动作 | 5 点采样最小前景 | 首/末（站立）前景 |
| --- | --- | --- |
| 余额-瘫趴叹气 | 0.1032 | **0.1844 / 0.1858** |
| 犬式伸懒腰 | 0.1308 | **0.1829 / 0.1836** |
| 悬空提溜反馈 | 0.1384 | **0.1831 / 0.1823** |
| 横向侧步滑行 | 0.1474 | **0.1843 / 0.1853** |
| 爪嘴并用拆礼物 | 0.1445 | **0.1846 / 0.1849** |

→ 受影响 **5 条**全部放行：它们的低谷只出现在**非站立**的中段，站立采样点前景 0.1823–0.1858，
   **全部高于 0.15**（且高于 20 条全局最小值 0.1528）。
   注意 `横向侧步滑行` 与 `爪嘴并用拆礼物` 是**站姿但细长/俯身**的动作：它们不在"低位段"之列，
   但也不需要那条豁免——**在站立采样点上它们本来就达标**，这正是本条裁定能覆盖它们的原因。

**裁定后 §7.2 的 20 条最终判定：20/20 通过**（`待机呼吸`+`原地轴转张望` 原本全项通过，
18 条 P4 动作中 9 条全项通过 + 9 条按上述两条口径判定通过）。

> 记录口径：以上两条是**用户明确授权的口径澄清**，不是 Root 单方面放宽；
> 两条数值门槛（2%、0.15）原样保留，改动的是「量在哪个产物上」与「对哪类姿态生效」。
> 若日后要把它们写进自动化门禁，需同步改 `evaluate_dachshund.py` 的对应分支（本轮未改）。

---

## 17. P5 装配与 P6 验收（2026-09-02）

### 17.1 P5：真包已装配（20 个动作全部就位）

产物：`$DSH_HOME/dsh-pet/pet/dachshund-config.json` + `$DSH_HOME/dsh-pet/pet/dachshund-animation/*.webm`（20 个，扁平存放，无 `webm/` 子目录）。

池分配严格按 §6.1/§6.2，权重合计 = 100（`idle 10 + turn 5 + move 5 + categories 40 + 40`）：

| 池 | 动画 |
| --- | --- |
| `idle` | 待机呼吸 |
| `turn` | 原地轴转张望 |
| `drag` | 悬空提溜反馈 |
| `clicks` | 欢快蹦跳 / 受惊炸毛后缩 / 单爪抬起招手 |
| `moves` | 原地倒步踱行（40–140px）/ 横向侧步滑行（40–140px） |
| `categories[小动作]`（weight 40） | 犬式伸懒腰 / 哈欠连天甩头 / 兴奋拍打尾巴 |
| `categories[玩耍]`（weight 40） | 爪拨玩具小车 / 凌空接吞零食 / 爪嘴并用拆礼物 |
| `events.balance`（恰好 6） | 余额-满溢欢腾 → 余额-瘫趴叹气 |
| `events.whisper` | 待机呼吸 |
| `events.workStatus`（6 档） | 见 §17.3（本次新增，理由见下） |

**A1 已处置**：`dachshund-config.json` 顶层显式写入犬向 `whisperPrompt` 与 `workStatusTexts`（6 档），
覆盖从内置默认（`dsh-pet/assets/config.jsonc`）继承来的女仆文案。
**A3 已处置**：把腊肠犬放到 `bottom-right`（主宠在 `top-right`）。
依据：`physics.petCollision` 是**飞行中互撞**的动量碰撞（`README.md:52`），
**不解决静止时同角落的重叠**——A3 原判「决定是否开启 petCollision」对症状无效；
改为四角分离，既不动宿主代码也不影响用户主宠。实测两只宠物矩形 `y 100–360` 与 `y 582.75–819`，无重叠。

**新增 `events.workStatus` 的理由**：`pet.ts:399-402` 在该池缺失时会打印
`配置缺少 animations.events.workStatus`，而 `WORK_STATUS_INDEX`（`shared/work-status.ts:13-20`）
固定为 0..5——本 pack 原本没有这个池（`workStatusEnabled` 默认 false 所以没暴露）。
按 §5.3「pet pack 不回落，animations 必须写全」补上 6 档，使该开关一旦打开即可用。

**清理**：删除了 `step00..step04` 里 P2 时代的过期重名产物 `output.*`（与 canonical `待机呼吸.*` 字节不同、
且不被任何配置引用），确保 20 个素材是唯一事实来源。

### 17.2 过程中发现并修复的真实缺陷：断点续跑发现不了**截断**产物

**症状**：`step02/爪拨玩具小车.webm` 只有 **147/240 帧（6.125s）**，而它在最终 pack 里被当作 10 秒素材。
**根因**：第一次整链运行超时被 SIGTERM 打断，留下一个**可解码的完整前缀**；
三个步骤脚本的 `_is_valid` 只查「存在 + 够大 + 不比源旧 + 能解码」——四项全过，于是**后续所有重跑都 SKIP 它**。
**次生危害**（说明它为什么严重）：`normalize_step03` 从这个残缺片段里测「站立高度」，
量到 556.9（其余 ≈610），于是把它放大 **1.616 倍**（其余 1.456–1.554），
**这条动作的狗会比别的大 10%**——正是 §9 R2 预警的「缩放一致性」风险，且很难靠肉眼在大盘里发现。

**修复**（测试先行）：`test/pet-dachshund/test_resume_truncation.py`（4 项）
→ 3 个脚本统一改用 `_tools.same_duration(dst, src, tolerance=0.2)`——
时长是最便宜且直接反映「有没有写完」的判据。
容差取 0.2s 而非 0：实测 VP9/webm 常比源 mp4 少报 1 帧（240 帧：mp4 = 10.000s、webm = 9.959s，差 0.041s）。
**复验**：重跑该动作后缩放系数回到 **1.473263**，全部 20 条时长均 ≈10s。

### 17.3 P6 浏览器验收（`ego-browser`，Chrome，真实 GUI `http://127.0.0.1:10000`）

§7.3 八行逐行结论：

| §7.3 检查 | 结论 | 证据（本轮亲验） |
| --- | --- | --- |
| 每个 `.webm` 可被浏览器透明渲染 | ✅ | 页面内把正在播的腊肠犬视频画进 canvas：四角 `(0,0,0,0)`、中心 `(173,98,44,255)`、透明像素 86.16%；截图确认**无绿底** |
| 动画池配置通过校验 | ✅ | 刷新后 `console` 捕获 **0 条 ERROR/WARN**，无「配置缺少 animations…」 |
| 每个池的动画都实际可播（非 404） | ✅ | **20/20** 个唯一动画全部通过真实右键菜单逐个点播成功（`src` 与菜单名一致）；另 20 个 URL 全部 HTTP 200 且 >50KB；负向对照「不存在的名称」→ 404（不回落）；目录穿越 `../`、`%2e%2e/`、绝对路径 → 全部 404 |
| 待机循环自然 | ✅ | 交付物首尾帧：轮廓 IoU **0.9856**、共有主体像素 RGB 平均差 6.68/255、脚底线 328→328（无跳变） |
| `turn` 真的翻转朝向 | ✅ | 转向**前**在播的待机层 `style.transform = scaleX(-1)`（= 朝右）；播完 `原地轴转张望` 后**新动画层**的 `transform = ""`（= 朝左）。与 `pet.ts:273`（按 `facing` 设镜像）+ `pet.ts:711-715`（`turn` 播完翻转 `facing`）逐字吻合 |
| 余额档位不报越界 | ✅ | 6 档全部点播成功（`余额-满溢欢腾`…`余额-瘫趴叹气`），控制台无「档位索引越界」 |
| 缩放一致性 | ✅ | 20 条交付物在首/尾站立帧量高度：**263.5–266.5px（相对散布 1.1%）**、脚底线极差 ≤2px、水平中心极差 ≤0.0266 |
| 右键「碎碎念」不报错 | ✅ | 无报错，并实际生成一句**犬向人设**的台词「肚子有点饿，想吃小饼干。」——同时反证 A1 的覆盖生效（此前会说女仆台词） |

**附加验收（本轮新增配置项）**：`工作状态` 子菜单展开为 **12 个叶子**（6 档 × 2 候选），
顺序与配置逐字一致；点播成功（`爪拨玩具小车.webm`），无越界。路径 / 动作菜单结构与配置完全对应。

### 17.4 §8 阶段表收口

P0a–P6 全部完成。最终花钱：

| 阶段 | 内容 | 成本 |
| --- | --- | --- |
| P2 | 待机呼吸 首片 | $0.1283 |
| P3 | turn 三次（含两次返工） | $0.0758 + $0.1240 + $0.1340 |
| P4 | 18 条 + 3 次返工 | $1.1664 |
| **合计** | | **≈ $1.63**（预算 §8 估 $2.3–3.2，实际更低） |

**残留项**：无阻塞项。§11 的 `remote` 切换（fork `dale0525/dsh-pet`）仍是**用户侧动作**，
未经授权不做；本轮未提交、未推送任何内容。

### 17.5 里程碑评审（P5/P6）驱动的修正

按 §3 的双重盲审流程执行：Root 自审 → 子代理盲审（`antigravity/gemini-3.8-flash`，只给路径与审查维度）
→ 逐条亲验 → 辩论轮。以下为本轮**已落地**的修正与依据。

| # | 发现（盲审条目） | 裁定 | 证据与处置 |
| --- | --- | --- | --- |
| 1 | `reframe()` 的水平留白被夹时**只夹 `pad_x` 不改 `crop_h`**，裁剪框宽高比 <16:9，再 resize 会把画面**横向拉伸** | **采纳** | 测试先复现：主体内 120×120 的正方形标记被拉成 **134×195（宽高比 0.687，压扁 31%）**。改为在 `[lo, hi]` 可行区间内取裁剪高（`lo = max(bh, bw/A)`、`hi = min(期望高, bh+2·max_py, (bw+2·max_px)/A)`），始终保证 `crop_w ≈ A·crop_h`；不可行时退到画幅内最大的 16:9 窗口。**等比是硬约束：宁可不放大，也绝不拉伸、绝不切主体。** 120 例随机（宽 60–1400、位置随机）复算：镜像等变 0 例失败、正方形失真 >5% 0 例 |
| 1b | 同一处 docstring 写「四周对称各留 **p** 像素」并出现**不存在的变量 `q`** | **采纳** | 改为「每个轴上左右/上下对称补留白，`pad_x ≠ pad_y`（前者由 16:9 反推）」，删掉 `q`，并新增测试 `test_symmetric_pads_are_not_equal_by_construction` 把该事实钉住 |
| 2 | **已交付的 3 张底板是否也被拉伸？** | 亲验：**未受影响** | 逐条复算旧代码的夹取条件：`base-standing`（主体 468×766、左右可用留白 581、需 554）与 `turn-side-left`（652×770、可用 505、需 465）**都没有触发夹取**，裁剪框严格 16:9。故无需重生成任何底板或素材 |
| 3 | `same_duration()` 容差 **0.2s = 4.8 帧**过宽，会放过几帧级截断 | **采纳** | 实测全链 20 条的自然量化差**最大仅 0.0410s（0.98 帧）**。测试先复现：0.2s 下**4 帧（0.167s）截断被判为有效**。收紧为 `MAX_DURATION_DRIFT = 0.09`（≈2.2 帧）：1 帧自然差放行、4 帧截断拒绝；三条真实链复验 **20/20 仍全部 SKIP**（无误判为截断） |
| 3b | `video_duration()` 传了 `-select_streams v:0` 却查 `format=duration`，该参数对容器级时长**无作用** | **采纳** | 删除该参数，并在代码注释里写明「别再加回来」 |
| 4 | §6.3/§7.1/§8/§9 R7/§14.2 仍留有「40 张 / 39 张 / 38 张」的旧口径，与 §14.6 A2 的更正冲突 | **采纳** | 全部改为「整包只需 2 张生成的图（`base-standing.png` + `turn` 偏侧首帧）」；P3 行改为「1 张生成 + 1 张镜像」，P4 行改为「18 段」。保留 §14.6 A2 里对历史失误的说明（那是更正记录本身，不是残留） |
| 5 | `encode_thumbs.py` 的 docstring 仍把「主宠物 `dsh-pet/assets/webm/`」列为去向之一，与本链（pet pack）不符 | **采纳** | 改为只写 pet pack 去向，并注明主宠物那条属于另一条线、别把本链产物放进去 |
| 6 | §16.9 的放行清单把 `犬式伸懒腰` 算进「绿溢超标 7 条」，且只列了 3 条低位段受影响动作，导致 `横向侧步滑行`/`爪嘴并用拆礼物` 看似**未被裁定覆盖** | **部分采纳** | 计数确实错：`犬式伸懒腰` 返工后原始绿溢 **0.0154** 本就通过（早期清单沿用了返工前的 0.0259），已更正为 **6 条**。覆盖性经**补测证实成立**（见下）：两条动作在**站立采样点**前景为 0.1843 / 0.1846，本来就 ≥0.15，其 <0.15 的低谷只出现在非站立中段。§16.9 已补「站立采样点的可执行定义 + 逐条实测表」，把「为什么它们被覆盖」写成可复核的证据而不是断言 |
| 6b | 规格宣称 20/20，但 `evaluate_dachshund.py` 仍按原始口径硬编码（5 点最小前景 ≥0.15、原始绿溢 ≤2%），去评测交付物会把 9 条判 FAIL——**文档与自带工具长期冲突** | **采纳** | 外派实现（验收契约=§16.9、触点仅该文件）：脚本增加「交付物（keyed webm）模式」，判定改用裁定后口径，同时**保留并报告**原始绿溢与 5 点最小前景作为参考值，`threshold` 字段显式标注「裁定后口径」，避免被误读成移动门禁 |
| 7 | `normalize_step03` 的 SKIP 分支仍全量解码测量，「断点续跑失去意义」 | **不采纳**（转辩论） | 代码注释写明这是**有意行为**：`params.json` 必须对每条都完整（它是缩放一致性的唯一真源），跳过的是**转码**。实测：完整转码 **26.80s/条** vs 仅测量 **1.20s/条**，相差 **22.3 倍**；20 条全 SKIP 省下约 8.9 分钟，只付出 24 秒测量。故「失去意义」与事实不符 |

**关于第 6 条的补测**（本轮新做的测量，脚本见下）：

| 动作 | 5 点采样最小前景 | 首帧/末帧（站立）前景 | 站立点是否 ≥0.15 |
| --- | --- | --- | --- |
| 余额-瘫趴叹气 | 0.1032 | 0.1844 / 0.1858 | ✅ |
| 犬式伸懒腰 | 0.1308 | 0.1829 / 0.1836 | ✅ |
| 悬空提溜反馈 | 0.1384 | 0.1831 / 0.1823 | ✅ |
| 横向侧步滑行 | 0.1474 | 0.1843 / 0.1853 | ✅ |
| 爪嘴并用拆礼物 | 0.1445 | 0.1846 / 0.1849 | ✅ |

结论：5 条低谷动作在站立采样点上**全部 ≥0.18**（≥0.15 门槛的 1.2 倍以上），裁定 (B) 完整覆盖。

### 17.6 辩论轮记录（回合制，终止条件满足）

盲审 6 条 + 1 条 Root 自审中，**全盘采纳 5 条**；判为「部分采纳」1 条（条目 6）、
「不采纳」1 条（条目 7）。按 §3 规则，这两条**必须再开一轮**，向**同一审查席位**提交
「原判 + Root 反证 + 盲审当时按规则未获得的事实」（用户裁定原话与授权范围、
§7.2/§7.3 的验收分层、以及用户已明确否决重跑付费动作这一约束）。

| 条目 | 原判 | Root 裁定 | 辩论轮结论 |
| --- | --- | --- | --- |
| 6 | §16.9 逻辑断层，2 条动作未被裁定覆盖；放行名单误计 `犬式伸懒腰` | 部分采纳（计数确错；覆盖性成立） | **让步**——审查席位接受站立采样点实测（`横向侧步滑行` 0.1843/0.1853、`爪嘴并用拆礼物` 0.1846/0.1849），并认可计数更正 |
| 7 | `normalize_step03` SKIP 分支仍全量解码，「失去断点续跑的意义」 | 不采纳 | **让步**——审查席位自行复测得「纯测量 1.16s vs 完整转码 26.8s，降幅 95.7%」，承认原判把瓶颈判成了 `scan_bbox` 帧扫描而非 VP9 编码，属误判与夸大 |

两条均以**具体实测证据**收束，无「未给出证据的坚持」，故 **共识达成，无分歧需上报裁定**。
辩论同时暴露了 Root 侧一处待办（已闭环）：条目 6 的裁定口径当时只写进文档，
`evaluate_dachshund.py` 仍是原始口径——已按 §17.5 条目 6b 改造为可复现。

### 17.7 门禁可复现性：`evaluate_dachshund.py` 已按裁定口径改造（§17.5 条目 6b 的落地）

**改造前的问题**：规格宣告 20/20，但自带门禁脚本仍按**原始口径**硬编码
（`min_chroma_fg >= 0.15` 取自 5 点采样最小、`max_spill <= 0.02` 取自原始 h264），
拿它去评测交付物会把 9 条判 FAIL——**文档与工具长期互相矛盾**，"20/20" 只是文档里的一句话。

**改造后**（`--keyed` / `--raw`，或按扩展名自动判定；两种模式的契约写在模块 docstring 里）：

| 模式 | 容器门禁 | 决定性的两条 | 仅供参考 |
| --- | --- | --- | --- |
| raw（H3 原始成片） | 864×480 / 24fps / 10±0.05s / **h264** | 同下（自动关联 `step04` 对应交付物） | — |
| keyed（已抠像交付物） | 640×360 / 24fps / 10±0.05s / **vp9+alpha** | ① 交付物可见绿边 ≤2% ② 站立采样点前景 ≥0.15 | 原始绿溢、5 点最小前景 |

实测字段名把「判定」与「参考」分开：`deliverable_spill_decision` / `standing_foreground_decision`
（决定）对 `raw_spill_reference` / `min_5point_foreground_reference`（参考），
且 `threshold` 字段原文即为 `deliverable spill <= 0.02 (ruled 2026-09-02)` 与
`bg >= 0.70 and standing foreground >= 0.15 at t=0 and t=9.9 (ruled 2026-09-02)`——
**读者不会把它误当成原始门禁**。

**Root 亲验（不依赖实施者转述）**：对 `step04/*.webm` 20 条逐条跑 `--seconds 10`，
**20/20 PASS**，失败项为空；交付物绿溢 **0.00071–0.00205**（门槛 0.02，最差仅占 **10.2%**）、
站立采样点前景 **0.1607–0.2156**（门槛 0.15）。新增 4 项单测覆盖两条裁定
（构造「5 点最小 <0.15 但首末 ≥0.15」与「原始绿溢超标但交付物 ≤2%」的用例，都必须 PASS）。

> 诚实标注：`evaluate_dachshund.py` 是**验证工具**，本轮改的是它对新裁定的**编码方式**，
> 不是放宽判据本身——两条数值门槛（2%、0.15）与它们的量法定义都原样保留，
> 且原始口径的数值仍然逐条打印为参考。

---

## 18. 部署态：当前 DSH 的生效配置（2026-09-02）

pack 已装入运行中的 DSH，**数据目录 `$DSH_HOME/dsh-pet/`**（与插件代码分离；
当前运行的插件是安装版 `$DSH_HOME/profiles/web/node_modules/dsh-pet@0.2.8`，非工作区 checkout）。

| 项 | 值 |
| --- | --- |
| 条目 key（= 素材根） | `dachshund` |
| 宠物 | `dachshund1` / 腊肠犬 / size 420 / `display: both`（网页悬浮 + 桌面窗口） |
| 位置 | `bottom-right`、marginX 24、marginY 100（主宠 `main` 在 `top-right`，实测两矩形不重叠） |
| 功能开关 | `balanceEnabled` / **`whisperEnabled`** / **`workStatusEnabled`** 全为 `true` |
| 主宠 | `main` / 蓝毛小女仆 / 462 / top-right（**未改动**） |

**开关写在 pack 自己的文件里**（`pet/dachshund-config.json` 的 `pets[0]`），**不是** `main-config.json`。
依据：`readAllConfig`（`config.ts:386-400`）把 `pet/<名>-config.json` 独立合并成自己的条目，
而 `seenIds` 是**跨条目全局**去重（`main` 先处理，会把该 id 占掉）——把 pack 的实例写进
`main-config.json` 会让 pack 文件里那只被静默丢弃。所以 pack 自己的字段只能写在自己的文件里。

> **2026-09-14 更新（本条原先的理由已作废）**：原文写「设置页只编辑 `main` 条目，所以开关只能手改文件」。
> 该限制已解除——设置页现在列出全部宠物，保存时 host 按 id 归属把每个实例**分流回写各自的文件**
> （`planConfigSave`，commit `8ecd631`）。因此上表的配置**现在也可以直接在设置页改**；
> 文件宠物的条目级精调字段（`whisperPrompt` / `workStatusTexts` / `animations` / `animationWeights`）
> 在保存时从磁盘原文透传保留，不会被设置页抹掉。**文件宠物不能在设置页删除**（删它自己的文件才有效）。

### 18.1 打开两个开关后的实测

| 功能 | 机制（本会话复验的源码位置） | 实测证据 |
| --- | --- | --- |
| 工作状态联动 | `whisperEnabled` 之外独立：气泡取 `workStatus.task ?? workStatusTexts[档位] 随机一句`（`pet.ts:427-432`） | 浏览器实测：端点 `/work-status` 回报本会话 `state="working"`，腊肠犬随即播 **`原地倒步踱行`**（= `workStatus[1]` 池成员）并弹出气泡，内容为宿主上报的任务详情。**0 条 console 报错** |
| 碎碎念 | `if (!cfg.whisperEnabled) return;`（未启用时该宠物对碎碎念事件**完全免疫**）；启用后轮询 `/whisper?pet=<id>`（`pet.ts:459`） | 端点实测返回**犬向人设**新台词：「肚肚好像饿了……主人有零食吗？」；对照主宠返回女仆台词「桌角的灰擦掉啦，亮晶晶的真好。」——两宠人设互不串味 |

**气泡文案优先级的含义**（值得记住，否则会误以为 `workStatusTexts` 没生效）：
宿主能提供任务详情时（如 todo/write 的「正在做 X」）气泡显示**任务详情**；
只有在没有任务详情时才回落到条目级 `workStatusTexts[档位]`。所以那 6 档犬向台词
（「小短腿想想办法~」「埋头干活中，别打扰汪~」等）是**兜底**，不是主显。

**成本提示**：`whisperEnabled` 打开后，`eventsRefreshSec.whisper = 300`（内置默认，
5 分钟一次）会周期性调用聊天模型生成台词；本项目未改这个周期。
`workStatusEnabled` 仅监听状态、不调用模型，无 token 成本。

### 18.2 支持真正删光宠物（2026-09-15）

**用户报告**：试图在设置页删除「蓝毛小女仆」时被拦下，提示「至少保留 1 个宠物」。

**根因（两处，读写各一，实测确认）**：

| 位置 | 旧行为 | 后果 |
| --- | --- | --- |
| 写路径 `planConfigSave`（`config.ts`，原 `else if (anySwitch) return null`） | 「带了全局开关却没有任何主条目实例」整份拒绝 → 400 | 设置页保存**总是**带三个全局开关，所以删掉唯一主宠后必然被拒 |
| 读路径 `mergePets`（`config.ts`，原 `!Array.isArray(raw) \|\| raw.length === 0`） | 把「显式空数组」与「字段缺失」当同一情形，回退内置默认宠物 | 即使放行写入，删除也会在下次加载时**复活**，形同虚设 |

守卫文案也误导：用户当时有 2 只宠物（主宠 + 腊肠犬），却被提示「至少保留一个宠物」——
因为该守卫统计的是**主条目**实例数，而文件宠物实例已并入设置页列表。

**决策**：支持真删除。`pets: []` 是合法提交（= 用户把宠物删光了），语义按条目类型区分：

- `main-config.json`：**没写** `pets` → 回退内置默认宠物（开箱即用）；写 `[]` → **真的零只**
- `pet/<名>-config.json`：**没写** `pets` 或写 `[]` → 该种类**零实例**。旧实现回退默认实例，
  而默认实例 id 恰是 `main`，与主宠重名——拍平后得到两只 id 相同的宠物（幽灵实例）。
  该回退分支同时是「实例全被跳过」的兜底，一并取消：塞回默认宠物只会掩盖配置错误。

**归属表简化**：`petOwners` 原先用一份「文件自己声明的 id」集合来识别读时回退的占位实例
（防止只有顶层人设的 pack 文件劫持主宠归属）。读路径改为 pack 不回退后，**条目里出现的 id
与该文件声明的 id 恒等**，这份集合成为死代码，按「激进清理」原则整体删除。

**客户端配套**：删掉最后一只主宠的守卫与 `atLeastOne` 文案；`doRemove` 的空列表崩溃
（`list[0].id`）改为 `list[0]?.id ?? ''`；「添加宠物」在 `petBridge.template` 为空时
（主条目已无实例）回退到内置默认宠物的同形状初值，不再静默无反应。

**盲审发现并修复的三处缺陷**（均为本次改动引入，已各自先用失败测试复现）：

| 缺陷 | 复现证据 | 修复 |
| --- | --- | --- |
| 只提交 `{ pets: [] }`（不带全局开关）时 `main = null` → 宿主不写盘却回 **200**（删除请求被静默吞掉；旧代码此时是 400 显式报错，属回归） | `planConfigSave(paths, {pets: []})` → `plan.main === null` | 落盘条件加 `arr.length === 0`：空 pets 本身即「清空主条目」的明确意图。同时保持「只提交文件宠物实例且不带开关 → main 仍为 null、不动该文件」 |
| 磁盘 pack 文件里 id 带首尾空格时，回写合并用未 trim 的磁盘 id 查提交表 → 查不中，原样吐出旧实例，**用户在设置页改的 size 等字段静默丢失** | 磁盘 `id: ' d1 '`、提交 `size: 430` → 写回仍是 `size: 300` | 磁盘 id 与 `cleanPet` 的 id 均 `trim()`，与读路径 `mergePet` 的 `p.id.trim()` 对齐 |
| 既有测试假阳性：只断言 `plan.entries.length === 1`（分流对了），未断言**合并结果**，掩盖了上一条 | 上述缺陷在 40/40 全绿时依然存在 | 补断言合并后的 `{id, size}` 与顶层 `whisperPrompt` |

**验收**：`npm test` 168/167/1（唯一失败为既有 Electron ENOENT，与本次无关）；
真实场景探针（1 主宠 + 腊肠犬 → 删主宠）确认落盘 `pets: []`、腊肠犬的
`whisperPrompt` / `workStatusTexts` 原样存活、拍平列表只剩 `dachshund1`；
零宠物终态下 `flattenPetList` 为空、`whisperPrompt` 保留，「恢复默认」可找回默认宠物。
运行态 HTTP 端到端：先写一只 `probe` 再发裸 `{pets:[]}` → 磁盘确变为 `pets: []`（旧代码此处会静默无操作）；
GUI 实测「添加宠物 → 删除 → 保存」全链路通过（保存后提示「已保存，桌宠即时生效。」，0 console 错误）。

---

## 19. 资产整理与清理（2026-09-15）

把 pet pack 的**可复用资产**从散落的 `test/pet-dachshund/` 收拢为正式目录，并删除已作废的中间产物与探测遗留。

### 19.1 目录变更

| 旧位置 | 新位置 | 说明 |
| --- | --- | --- |
| `test/pet-dachshund/prompts/` | `pets/dachshund/prompts/` | 20 个 H3 提示词 |
| `test/pet-dachshund/frames/` | `pets/dachshund/frames/` | 3 张身份基准首尾帧 |
| `test/pet-dachshund/raw/` | `pets/dachshund/raw/` | 2 张图生图原图 |
| `test/pet-dachshund/p{2,3,4}-h3-out/<动作>/output.mp4` | `pets/dachshund/h3/<动作>.mp4` | **三级嵌套扁平化**；20 段 H3 成片 |
| `test/pet-dachshund/p{2,3,4}-h3-out/<动作>/report.json` | `pets/dachshund/reports/<动作>.json` | 成本/溯源记录 |
| `test/pet-dachshund/evaluate_dachshund.py`、`test_*.py` | `pets/dachshund/` | 门禁与 5 个单测（共 34 项） |

**为什么用 `pets/<种类名>/`**：与运行时 `$DSH_HOME/dsh-pet/pet/<种类名>-{config.json,animation/}` 一一对应，
新增宠物时目录结构自解释。目录深度不变（都是仓库根的二级子目录），
故各脚本的 `REPO_ROOT = Path(__file__).resolve().parents[2]` **无需改动**。

### 19.2 代码与文档同步

| 文件 | 改动 |
| --- | --- |
| `pets/dachshund/evaluate_dachshund.py` | 新增 `PET_DIR`/`H3_DIR`；两个 resolver 去掉 `p2/p3/p4-h3-out` 的 parent 特例（扁平化后不需要），`resolve_raw_counterpart` 首选 `H3_DIR/<stem>.mp4` |
| `pets/dachshund/test_evaluate_dachshund.py` | `sys.path` 指向 `pets/dachshund` |
| `pets/dachshund/test_resume_truncation.py` | `TMP` 指向 `pets/dachshund/.tmp-truncation` |
| `pets/dachshund/README.md` | **新增**：目录说明、六段链路、新增动画步骤、从 `h3/` 重跑下游、门禁用法、装配位置、署名义务 |
| `README.md` | 「项目结构」新增 `pets/` 条目 |
| `.gitignore` | 删除已不存在的 `dsh-image-gen/`；注释更新（pet pack 资产在 `pets/`） |
| §6.3 | 「除 `turn` 外的 **18** 个动作」改为 **19**——这是与同段「20 × 2 = 40 张」同族的算术失误（20 − 1 = 19），且与 §6.3 末尾「19 个动作的 `standing["height"]`」自相矛盾。已逐条核对 20 份提示词的 `<Picture 1>`：只有 `02-turn-inplace` 是偏侧，其余 **19 份**均为正面站姿，实测支持 19 |

### 19.3 清理清单（释放 ≈343 MB）

| 路径 | 体积 | 判定依据（实测） |
| --- | --- | --- |
| `step00/` | 20 M | 20/20 与 `h3/` 成片 **md5 逐字节相同**，纯冗余 |
| `step01/` `step02/` `step03/` | 154 M | 桥接/抠像/归一化中间产物，可从 `h3/` 再生 |
| `step04/` | 7.2 M | 20/20 与已装 pack `$DSH_HOME/dsh-pet/pet/dachshund-animation/` 逐字节相同 |
| `p4-h3-out/*/generated-243-*.mp4` | 20 M | 243 帧预终稿；契约输入是 240 帧的 `output.mp4`（已入 `h3/`） |
| `p2/p3/p4-h3-out/stills/` | 1.9 M | 评审截图，可从视频重抽 |
| `test/pet1/transparent-probe/` | 135 M | 前序透明探测，仅 `ACTION-DESIGN.md` 引用 |
| `dsh-image-gen/` | 5.1 M | 前序失败尝试（RGB 画棋盘格冒充透明），已被 `raw/` 取代 |

> **`step00/` 保留 `.gitignore` 条目**：它仍是 `bridge_step00.py` 的默认输入目录，
> 只是本包的 H3 成片已入库到 `pets/dachshund/h3/`，从那里重跑需显式 `--src pets/dachshund/h3`。

### 19.4 入库范围与验收

入库 `pets/dachshund/` 下 **72 个文件 ≈ 27 MB**：20 H3 成片 + 20 报告 + 20 提示词 + 3 首尾帧 + 2 原图
+ README + 评估器 + 5 个单测。**`step01`–`step04` 不入库**（中间产物，可再生）。

**验收（全部本会话实测）**：

| 项 | 结果 |
| --- | --- |
| 资产完整性 | 71/71 条目（20 提示词 + 3 帧 + 2 原图 + 20 H3 + 20 报告）md5 **与搬迁前完全一致** |
| Python 单测 | **34/34 OK**（frame_plate 10 / scripts_tools 3 / bridge_step00 4 / evaluate_dachshund 12 / resume_truncation 5） |
| TS 套件 | `npm test` **168/167/1**（唯一失败为既有 Electron ENOENT，与本轮无关） |
| 静态检查 | `tsc --noEmit` 0 · `eslint` 0 · `prettier --check src/` 0 |
| 门禁实跑 | `evaluate_dachshund.py frames` 与 `video`（raw 模式）均正常，容器判据 864×480 / 24fps / 10.0s / h264 全部命中 |
| resolver 探针 | `resolve_raw_counterpart` 命中扁平 `h3/<动作>.mp4`；`resolve_keyed_counterpart` 在 `step04/` 缺失时返回 `None` 而非抛错 |

> **关于 20 段 H3 的 raw 模式判定**：逐段跑门禁时 14 段 PASS、6 段 REVIEW，
> 失败的 6 段**全部且仅仅**是「原始成片绿溢 > 2%」（`余额-满溢欢腾` 0.0475、`爪嘴并用拆礼物` 0.0238、
> `爪拨玩具小车` 0.0219、`单爪抬起招手` 0.0215、`横向侧步滑行` 0.0202、`哈欠连天甩头` 0.0201）。
> 这与 §16.6 表格**逐条吻合**，是**既有事实而非本轮引入**：`step04/` 按设计不入库，
> 故 raw 模式只能走「无交付物 → 用原始绿溢判」的降级分支（`evaluate_dachshund.py:14-15`）。
> 显式补上 `--deliverable`（用已装 pack 的 `.webm`）后，**这 6 段全部转 PASS**，与 §16.9 的 20/20 裁定一致。

> **`reports/*.json` 里的 `output_path` / `ffprobe.format.filename` 保留旧绝对路径**：
> 它们是**生成当时的不可变审计记录**（ffprobe 原始输出），改写会伪造溯源，故原样保留。
> 无任何代码消费这些字段（已 grep 确认）。
