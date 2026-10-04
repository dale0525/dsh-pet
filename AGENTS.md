# AGENTS.md — dsh-pet

改动前必知。产品是什么、怎么装怎么用见 [`README.md`](README.md)；插件包见 [`dsh-pet/README.md`](dsh-pet/README.md)；
腊肠犬 pet pack 见 [`pets/dachshund/README.md`](pets/dachshund/README.md)。

## 目录与归属

目录树与 ①②③ 分块见 [`README.md`](README.md)「项目结构」。以下只写归属判据：

- **不入库**（本地或生成产物，见 `.gitignore`）：`step00/`~`step04/`、`pr/`、`prproj/`、`.tools/`、
  `.pixi/`、`video/*.mp4`、`test/pet1/`、`dsh-pet/lib/`、`dsh-pet/runtime/electron-helper/shared-core.js`。
  改这些目录不会进版本库；要固化的产物必须落到 `pets/<种类名>/`（H3 成片、成本记录）或 `dsh-pet/assets/`。
- **`docs/`** 只承载「如何操作」的指南与 `docs/plans/`。禁止新建 `docs/specs/`、`docs/adr/`、
  `docs/decisions/`、`CONTEXT-MAP.md`。`docs/plans/` 是事前冻结的计划，实施中可能偏离，去留由用户决定。
- **新增文档**前先搜同主题既有文档，有则就地更新。命名用 `kebab-case.md`（资源目录内的 `README.md` 除外）；
  一个文档一种语言，禁止新增 `_CN` / `.zh` 译文副本。

## 改动生效路径

- **插件源码**（`dsh-pet/src/**`、`dsh-pet/runtime/**`）：改完必须 `cd dsh-pet && npm run prepare` 重建；
  `lib/` 是构建产物，**不要手改**。宿主进程改动需重启 `dsh web`，纯客户端改动刷新页面即可。
- **桌面端**（`dsh-pet/runtime/electron-helper/*.js`）：经典 `<script>` 全局脚本（由 `index.html` 顺序加载），
  **不得** `import` `src/shared`。与浏览器共享的纯逻辑只能走构建产物 `shared-core.js`（`window.PetShared`）。
  浏览器端（`src/client/`）与桌面端是同一套行为的两个外壳，改一处须核对另一处。
- **素材与配置**：宿主每次读配置，改配置或换素材后刷新页面即生效。
- **本机验证**：profile（`~/.dsh/profiles/web/node_modules/dsh-pet`）下是**拷贝**而非软链，重建后需同步 `lib/` 与 `runtime/`。

## 硬门禁

- **素材链顺序**：`chroma_step02.py` 与 `normalize_step03.py` 都硬编码 **1280×720**，
  因此桥接（`bridge_step00.py`，864×480 → 1280×720）必须排在它们之前。
  把 H3 原始的 864×480 直接喂给抠像不会报错，但会把 2.22 帧当成一帧读，**静默错位**。
- **H3 不可复现**：生成器 `agentnovel_modal_h3.py` 是外部工程的脚本，本仓库只引用。
  `h3/` 成片入库正是为了固化这一步——仓库内可复现的只有 ④→⑥，不是从零。
- **命名不变量**：`pets/<种类名>/` 下 `h3/`、`reports/`、`step04/` 与
  `$DSH_HOME/dsh-pet/pet/<种类名>-animation/` 四处**同名**（`<动作名>`）；配置里的动画名就是文件名。
- **首尾帧不变量**：除 `turn` 外，一个动作的首帧与尾帧是**同一张** `frames/base-standing.png`
  （身份与缩放一致），否则动画链首尾相接时会跳变。
- **门禁不降级**：`evaluate_dachshund.py` 缺依赖时显式报错并给出补救指引，不静默通过。

## 验收命令

```sh
# 插件单测（180 项；1 项 Electron 路径用例依赖本机安装，与本仓库改动无关）
cd dsh-pet && npm test
```

**素材链与动画生成**的完整流程、单测与门禁命令见项目技能 `pet-animation`（`.agents/skills/pet-animation/SKILL.md`）——
新增动画时加载它，不要在别处复述步骤。素材链脚本的 ffmpeg 走工作区 `.tools/`，不在系统 `PATH`。

## 提交

未获用户明确要求（「收尾」「提交吧」）不提交、不推送。素材与代码的许可约定见 `README.md`「许可」。
