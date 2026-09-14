/**
 * host 侧配置模块 —— 全项目唯一的配置读取入口与写盘出口。
 *
 * 角色：
 *   - readAllConfig()：读取 内置默认（assets/config.jsonc，绝对正确）+ 用户主配置
 *     （main-config.json）+ 文件宠物（pet/<名>-config.json，一个文件一个条目），
 *     逐字段合并后返回 **绝对正确** 的完成品聚合：
 *       { main: {...}, test1: {...}, ... }
 *     每个条目都是对应配置文件的原文结构（字段名/位置/嵌套一律不动），且所有字段已填满。
 *   - planConfigSave()：设置页写盘（PUT /config）的**保存计划**——把提交上来的完整宠物列表
 *     按 id 归属分流：主条目实例（含新建）→ main-config.json，文件宠物实例 →
 *     它自己那个 pet/<前缀>-config.json（顶层字段原样保留）。只返回计划，落盘由调用方执行。
 *
 * 合并规则（唯一规则）：
 *   - 内置默认配置是唯一默认值来源（「代码里的配置绝对正确」）；
 *   - 覆盖文件写了 → 用自己的值；**没写 → 静默填内置默认值**（结构性常态，不告警——
 *     设置页写的用户层本就只含 pets + notificationsEnabled；文件宠物也可以写得很短）；
 *   - **显式写了但非法**（类型/结构/白名单外）→ 告警 + 填内置默认值
 *     （同一 文件+字段 进程内只告警一次，避免每请求刷屏；保证返回绝不出现残缺/非法值）；
 *   - 身份字段例外（无默认可填）：id 必须存在、全局唯一（缺失/重复/非法/冲突 →
 *     跳过该实例并告警）；name 缺失/空 → 按该宠物 id 处理并告警（既定规则，不继承默认名字）。
 *
 * 消费端契约：其他代码（路由/命令/碎碎念/对话/桌面）只消费 readAllConfig 的返回值，
 * 不做任何校验/兜底；浏览器与桌面通过 GET /dsh-pet-7340/config 拿到同一份成品。
 *
 * 本模块是 host 自包含实现（不 import src/shared —— DSH 单文件加载约束）；
 * 浏览器/桌面侧的对应纯逻辑（把成品拍平成渲染列表）在 src/shared/config.ts。
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

/** 位置角落白名单 */
const CORNERS = ['top-left', 'top-right', 'bottom-left', 'bottom-right'] as const;
const CORNER_SET: ReadonlySet<string> = new Set(CORNERS);

/** display 白名单 */
const PET_DISPLAYS = ['web', 'desktop', 'both', 'none'] as const;
const PET_DISPLAY_SET: ReadonlySet<string> = new Set(PET_DISPLAYS);

/** id 禁用的字符（Windows 文件名保留符 + 控制字符，防配置值逃逸文件路径） */
// eslint-disable-next-line no-control-regex
const ID_FORBIDDEN = /[\\/:\x00-\x1f]/;

/** 已告警过的 文件:字段（进程内去重：同一问题只告警一次，避免每请求刷屏；重启重置） */
const warnedKeys = new Set<string>();

function warnOnce(key: string, message: string): void {
  if (warnedKeys.has(key)) return;
  warnedKeys.add(key);
  console.warn('dsh-pet: ' + message);
}

/** 剥除 JSONC 注释（行注释 // 与块注释）得到纯 JSON */
function stripJsonc(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^\\:])\/\/.*$/gm, '$1')
    .trim();
}

/** 读取并解析 JSONC 文件；不存在/解析失败 → undefined（调用方决定处理） */
function readJsonc(path: string): Record<string, unknown> | undefined {
  try {
    const raw = JSON.parse(stripJsonc(readFileSync(path, 'utf8'))) as unknown;
    return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : undefined;
  } catch {
    return undefined;
  }
}

/** 配置路径集（宿主组装好后传入，单一事实来源） */
export interface ConfigPaths {
  /** 包内 assets/config.jsonc（内置默认，绝对正确） */
  defaultFile: string;
  /** ~/.dsh/dsh-pet/main-config.json（用户主配置，可编辑层） */
  userFile: string;
  /** ~/.dsh/dsh-pet/pet（文件宠物目录） */
  petDir: string;
}

interface PetFileEntry {
  /** 文件名前缀 = 条目 key = 素材根 */
  prefix: string;
  path: string;
}

/** 扫描 pet/ 目录：<名>-config.(json|jsonc) → 条目（按文件名排序） */
function scanPetFiles(petDir: string): PetFileEntry[] {
  let entries;
  try {
    entries = readdirSync(petDir, { withFileTypes: true });
  } catch {
    return []; // pet/ 目录不存在 = 无文件宠物
  }
  return entries
    .filter((e) => e.isFile())
    .map((e) => e.name)
    .filter((name) => /^.+?-config\.(json|jsonc)$/.test(name))
    .sort()
    .map((name) => ({ prefix: name.replace(/-config\.(json|jsonc)$/, ''), path: join(petDir, name) }));
}

/** animations 段完整性校验（与旧 assertAnimationsHost 同一套规则；不 throw，非法返回 false） */
function animationsValid(a: unknown): boolean {
  if (!a || typeof a !== 'object') return false;
  const anims = a as Record<string, unknown>;
  for (const key of ['idle', 'turn', 'drag', 'clicks']) {
    if (!Array.isArray(anims[key])) return false;
  }
  const moves = anims.moves;
  if (
    !moves ||
    typeof moves !== 'object' ||
    typeof (moves as Record<string, unknown>).default !== 'object' ||
    (moves as Record<string, unknown>).default === null ||
    !Array.isArray((moves as Record<string, unknown>).actions)
  ) {
    return false;
  }
  if (!Array.isArray(anims.categories)) return false;
  const ev = anims.events;
  if (!ev || typeof ev !== 'object' || Array.isArray(ev)) return false;
  const evEntries = ev as Record<string, unknown>;
  for (const pool of Object.values(evEntries)) {
    if (!Array.isArray(pool) || pool.length === 0) return false;
    for (const slot of pool) {
      // 档位槽位：单个动画名（原行为）或候选数组（档内随机抽 1，见 shared/pickers pickSlot）；
      // 空字符串 / 空数组 / 成员为空串的数组均非法
      if (typeof slot === 'string') {
        if (slot.length === 0) return false;
      } else if (Array.isArray(slot)) {
        if (slot.length === 0) return false;
        for (const name of slot) {
          if (typeof name !== 'string' || name.length === 0) return false;
        }
      } else {
        return false;
      }
    }
  }
  const balance = evEntries.balance;
  return Array.isArray(balance) && balance.length > 0;
}

/** animationWeights 段校验（idle/turn/move 三个非负数字） */
function weightsValid(w: unknown): boolean {
  if (!w || typeof w !== 'object') return false;
  const weights = w as Record<string, unknown>;
  for (const key of ['idle', 'turn', 'move']) {
    const v = Number(weights[key]);
    if (!Number.isFinite(v) || v < 0) return false;
  }
  return true;
}

/** physics 段校验：gravity ≥ 0（0 = 无重力，合法）、restitution ∈ [0,1]、groundFriction ≥ 0（均为有限数字）、
 *  ceilingBounce 为布尔、throwPower > 0（有限数字）、petCollision 为布尔 */
function physicsValid(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  const p = value as Record<string, unknown>;
  const g = Number(p.gravity);
  const r = Number(p.restitution);
  const f = Number(p.groundFriction);
  const tp = Number(p.throwPower);
  return (
    Number.isFinite(g) &&
    g >= 0 &&
    Number.isFinite(r) &&
    r >= 0 &&
    r <= 1 &&
    Number.isFinite(f) &&
    f >= 0 &&
    typeof p.ceilingBounce === 'boolean' &&
    Number.isFinite(tp) &&
    tp > 0 &&
    typeof p.petCollision === 'boolean'
  );
}

/** workStatusTexts 段校验：二维数组——外层每项都是非空字符串数组（档位文案，每档可多句随机）；空数组不可用 */
function workStatusTextsValid(value: unknown): boolean {
  if (!Array.isArray(value) || value.length === 0) return false;
  for (const group of value) {
    if (!Array.isArray(group) || group.length === 0) return false;
    for (const text of group) {
      if (typeof text !== 'string' || text.length === 0) return false;
    }
  }
  return true;
}

/** 顶层标量字段的合法性（非法与缺失同处理：取默认值 + 告警） */
function topFieldValid(key: string, value: unknown): boolean {
  switch (key) {
    case 'whisperPrompt':
      return typeof value === 'string' && value.length > 0;
    case 'chatMemoryRounds': {
      const n = Number(value);
      return Number.isFinite(n) && n >= 0;
    }
    case 'notificationsEnabled':
      return typeof value === 'boolean';
    case 'whisperImageEnabled':
      return typeof value === 'boolean';
    case 'chatImageEnabled':
      return typeof value === 'boolean';
    case 'animations':
      return animationsValid(value);
    case 'animationWeights':
      return weightsValid(value);
    case 'physics':
      return physicsValid(value);
    case 'workStatusTexts':
      return workStatusTextsValid(value);
    default:
      return true;
  }
}

/** eventsRefreshSec 段：深度合并——每个事件键都要有正数秒值；缺子键 → 静默取默认，显式写但非法 → 告警 + 默认 */
function mergeEventsRefreshSec(base: unknown, overlay: unknown, label: string): Record<string, number> {
  const baseErs = base && typeof base === 'object' ? (base as Record<string, unknown>) : {};
  const out: Record<string, number> = {};
  for (const [eventName, baseSec] of Object.entries(baseErs)) {
    const own = overlay && typeof overlay === 'object' ? (overlay as Record<string, unknown>)[eventName] : undefined;
    // 结构性常态：只写部分事件键（如只写 balance）→ 缺的键静默取默认
    if (own === undefined) {
      out[eventName] = Number(baseSec);
      continue;
    }
    const n = Number(own);
    if (!Number.isFinite(n) || n <= 0) {
      warnOnce(
        `${label}:eventsRefreshSec.${eventName}`,
        `「${label}」的 eventsRefreshSec.${eventName} 非法，已取默认值`,
      );
      out[eventName] = Number(baseSec);
      continue;
    }
    out[eventName] = n;
  }
  return out;
}

/** 一个覆盖文件 → 完整条目：顶层逐字段合并（没写/非法 → 内置默认 + 告警），pets 逐实例 */
function mergeEntry(
  base: Record<string, unknown>,
  overlay: Record<string, unknown> | undefined,
  label: string,
  basePets: Record<string, unknown>[],
  seenIds: Set<string>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(base)) {
    if (key === 'pets') {
      out.pets = mergePets(basePets, overlay?.[key], label, seenIds);
      continue;
    }
    if (key === 'eventsRefreshSec') {
      out[key] = mergeEventsRefreshSec(base[key], overlay?.[key], label);
      continue;
    }
    const own = overlay ? overlay[key] : undefined;
    // 结构性常态：覆盖层（尤其是设置页写的用户层）本来就不写顶层字段 → 缺失静默取默认，不告警；
    // 只有「显式写了但非法」才告警（真异常，默认值兜底）
    if (own === undefined) {
      out[key] = base[key];
      continue;
    }
    if (!topFieldValid(key, own)) {
      warnOnce(`${label}:${key}`, `「${label}」的 ${key} 非法，已取默认值`);
      out[key] = base[key];
      continue;
    }
    out[key] = own;
  }
  return out;
}

/** pets 数组合并：文件没写/空 → 默认列表；逐实例合并（缺字段 → 内置默认 pets[0]，静默）。 */
function mergePets(
  basePets: Record<string, unknown>[],
  raw: unknown,
  label: string,
  seenIds: Set<string>,
): Record<string, unknown>[] {
  const basePet: Record<string, unknown> = basePets[0] ?? {};
  if (!Array.isArray(raw) || raw.length === 0) {
    warnOnce(`${label}:pets`, `「${label}」的 pets 缺失或为空，已取默认宠物列表`);
    return basePets;
  }
  const out: Record<string, unknown>[] = [];
  for (const item of raw) {
    const pet = mergePet(basePet, item, label, seenIds);
    if (pet) out.push(pet);
  }
  if (out.length === 0) {
    warnOnce(`${label}:pets`, `「${label}」的 pets 全部被跳过（id 非法/重复/冲突），已取默认宠物列表`);
    return basePets;
  }
  return out;
}

/** 宠物实例字段取数字；缺失 → 静默取默认（结构性常态）；显式写但非法 → 告警 + 默认 */
function petNumber(own: unknown, def: unknown, min: number, label: string, field: string, id: string): number {
  const n = Number(own);
  if (own !== undefined && own !== null && Number.isFinite(n) && n >= min) return n;
  // 缺失 = 常态（文件宠物可只写 id/name 等少量字段），静默取默认；显式写了但非法才是真异常
  if (own !== undefined && own !== null) {
    warnOnce(`${label}:${field}:${id}`, `宠物「${id}」的 ${field} 非法，已取默认值`);
  }
  return Number(def);
}

/** 宠物实例字段取布尔；缺失 → 静默取默认；显式写但非法 → 告警 + 默认 */
function petBool(own: unknown, def: unknown, label: string, field: string, id: string): boolean {
  if (typeof own === 'boolean') return own;
  if (own !== undefined && own !== null) {
    warnOnce(`${label}:${field}:${id}`, `宠物「${id}」的 ${field} 非法，已取默认值`);
  }
  return Boolean(def);
}

/** 宠物实例字段取白名单枚举；缺失 → 静默取默认；显式写但非法 → 告警 + 默认 */
function petEnum(
  own: unknown,
  set: ReadonlySet<string>,
  def: unknown,
  label: string,
  field: string,
  id: string,
): string {
  if (typeof own === 'string' && set.has(own)) return own;
  if (own !== undefined && own !== null) {
    warnOnce(`${label}:${field}:${id}`, `宠物「${id}」的 ${field} 非法，已取默认值`);
  }
  return typeof def === 'string' ? def : '';
}

/** 一只实例 → 完成品实例（id 必须自己的且全局唯一；其余字段没写/非法 → 默认 + 告警） */
function mergePet(
  base: Record<string, unknown>,
  raw: unknown,
  label: string,
  seenIds: Set<string>,
): Record<string, unknown> | null {
  const p = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const id = typeof p.id === 'string' ? p.id.trim() : '';
  if (!id || id.length > 64 || ID_FORBIDDEN.test(id) || seenIds.has(id)) {
    warnOnce(`${label}:id:${id || '(空)'}`, `「${label}」的宠物 id「${id || '(空)'}」非法、重复或已存在，已跳过该实例`);
    return null;
  }
  seenIds.add(id);
  // name：缺失/空 → 按该宠物 id 处理（既定规则：可重复，不继承默认名字）
  const rawName = typeof p.name === 'string' ? p.name.trim() : '';
  const name = rawName || id;
  if (!rawName) warnOnce(`${label}:name:${id}`, `宠物「${id}」缺少 name，已按 id 处理`);

  // position：逐子字段合并（缺失 → 静默取默认；显式写但非法 → 告警 + 默认）
  const basePos = base.position && typeof base.position === 'object' ? (base.position as Record<string, unknown>) : {};
  const ownPos = p.position && typeof p.position === 'object' ? (p.position as Record<string, unknown>) : {};

  return {
    id,
    name,
    size: petNumber(p.size, base.size, 1, label, 'size', id),
    balanceEnabled: petBool(p.balanceEnabled, base.balanceEnabled, label, 'balanceEnabled', id),
    whisperEnabled: petBool(p.whisperEnabled, base.whisperEnabled, label, 'whisperEnabled', id),
    workStatusEnabled: petBool(p.workStatusEnabled, base.workStatusEnabled, label, 'workStatusEnabled', id),
    display: petEnum(p.display, PET_DISPLAY_SET, base.display, label, 'display', id),
    position: {
      corner: petEnum(ownPos.corner, CORNER_SET, basePos.corner, label, 'position.corner', id),
      marginX: petNumber(ownPos.marginX, basePos.marginX, -Infinity, label, 'position.marginX', id),
      marginY: petNumber(ownPos.marginY, basePos.marginY, -Infinity, label, 'position.marginY', id),
    },
  };
}

/**
 * 唯一读取函数：内置默认 + 用户主配置 + 文件宠物逐字段合并后的完成品聚合。
 * 返回 { main: {...}, test1: {...}, ... } —— 每个条目都是原文件结构且所有字段已填满，
 * 消费端直接读，不做任何校验/兜底。每次调用重新读文件：修改配置刷新/重启即生效。
 */
export function readAllConfig(paths: ConfigPaths): Record<string, Record<string, unknown>> {
  const base = readJsonc(paths.defaultFile);
  if (!base) throw new Error('dsh-pet: 内置默认配置缺失或解析失败（安装损坏）：' + paths.defaultFile);
  const basePets = Array.isArray(base.pets) ? (base.pets as Record<string, unknown>[]) : [];
  const seenIds = new Set<string>();
  const out: Record<string, Record<string, unknown>> = {};

  // main 条目：内置默认 ← main-config.json（可编辑层）
  const mainOverlay = readJsonc(paths.userFile);
  if (existsSync(paths.userFile) && !mainOverlay) {
    warnOnce('file:' + paths.userFile, '用户主配置解析失败，已按无用户配置处理：' + paths.userFile);
  }
  out.main = mergeEntry(base, mainOverlay, 'main-config.json', basePets, seenIds);

  // 文件宠物条目：pet/<名>-config.json，一个文件一个条目（key = 文件名前缀 = 素材根）
  for (const file of scanPetFiles(paths.petDir)) {
    const parsed = readJsonc(file.path);
    if (!parsed) {
      warnOnce('file:' + file.path, '文件宠物配置解析失败，已跳过：' + file.path);
      continue;
    }
    out[file.prefix] = mergeEntry(base, parsed, file.prefix + '-config.json', basePets, seenIds);
  }
  return out;
}

/** 拍平全部条目的 pets 为单列表（host 消费端用：桌面宠物列表 / 命令 / 当前桌宠解析） */
export function flattenPetList(merged: Record<string, Record<string, unknown>>): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  for (const conf of Object.values(merged)) {
    if (Array.isArray(conf?.pets)) out.push(...(conf.pets as Record<string, unknown>[]));
  }
  return out;
}

/** 在完成品聚合里按实例 id 定位宠物及其所属条目（host 内部消费索引）：
 *  条目 key 即素材根（assetRoot）；条目级字段（whisperPrompt/chatMemoryRounds/animations）随条目取。 */
export function findPetInstance(
  merged: Record<string, Record<string, unknown>>,
  petId: string,
): { entry: string; conf: Record<string, unknown>; pet: Record<string, unknown> } | undefined {
  for (const [entry, conf] of Object.entries(merged)) {
    const pets = Array.isArray(conf?.pets) ? (conf.pets as Record<string, unknown>[]) : [];
    const found = pets.find((p) => String(p.id) === petId);
    if (found) return { entry, conf, pet: found };
  }
  return undefined;
}

/** 白名单重建一只可编辑实例；任一字段非法 → null（整份提交作废，绝不写半份） */
function cleanPet(p: unknown): Record<string, unknown> | null {
  if (!p || typeof p !== 'object') return null;
  const pp = p as Record<string, unknown>;
  const id = String(pp.id ?? '');
  // 有意过滤文件名非法字符（Windows 保留符 + 控制字符），防止配置值逃逸配置文件路径
  if (!id || id.length > 64 || ID_FORBIDDEN.test(id)) return null;
  const size = Number(pp.size);
  if (!Number.isFinite(size) || size <= 0) return null;
  // 显示名：可重复不校验唯一；缺失/留空/非字符串 → 按该宠物 id 处理（兼容旧配置）并告警
  let name = typeof pp.name === 'string' ? pp.name.trim() : '';
  if (!name) {
    console.warn(`dsh-pet: pet「${id}」缺少 name，已按默认 ${id}（宠物 id）处理`);
    name = id;
  }
  const balanceEnabled = pp.balanceEnabled;
  if (typeof balanceEnabled !== 'boolean') return null;
  const whisperEnabled = pp.whisperEnabled;
  if (whisperEnabled !== undefined && typeof whisperEnabled !== 'boolean') return null;
  const workStatusEnabled = pp.workStatusEnabled;
  if (workStatusEnabled !== undefined && typeof workStatusEnabled !== 'boolean') return null;
  const display = String(pp.display ?? '');
  if (!PET_DISPLAY_SET.has(display)) return null;
  const pos = pp.position && typeof pp.position === 'object' ? (pp.position as Record<string, unknown>) : {};
  const corner = String(pos.corner ?? '');
  if (!CORNER_SET.has(corner)) return null;
  const marginX = Number(pos.marginX);
  const marginY = Number(pos.marginY);
  if (!Number.isFinite(marginX) || !Number.isFinite(marginY)) return null;
  return {
    id,
    name,
    size,
    balanceEnabled,
    whisperEnabled,
    workStatusEnabled,
    display,
    position: { corner, marginX, marginY },
  };
}

/** 一份写盘计划里的单个文件（内容 = 该文件的新全文） */
export interface ConfigSaveFile {
  /** 目标文件的绝对路径 */
  path: string;
  /** 条目 key（= 素材根；main-config.json 时为 'main'） */
  prefix: string;
  /** 写盘内容：非 pets 顶层字段已从磁盘原文件透传保留 */
  config: Record<string, unknown>;
}

/** PUT /config 的保存计划：宿主照此逐文件落盘，未列出的文件一个字节都不动 */
export interface ConfigSavePlan {
  /** 主条目（main-config.json）新内容；**null = 本次提交不涉及主条目** */
  main: (Record<string, unknown> & { pets: unknown[] }) | null;
  /** 文件宠物条目：本条目被提交了实例，逐个文件给出新全文 */
  entries: ConfigSaveFile[];
}

/** 全局开关白名单（顶层、不归宠物文件管）：请求体传了才算白名单字段，未传则透传磁盘旧值——
 *  否则整包调用的调用方漏传一个开关，就会把用户既有设置悄悄抹成默认。 */
const GLOBAL_SWITCHES = ['notificationsEnabled', 'whisperImageEnabled', 'chatImageEnabled'] as const;

/** 从磁盘原对象透传保留非白名单顶层字段（physics / whisperPrompt / workStatusTexts / memes…），
 *  再覆盖本次提交拥有的白名单字段——用户手改的精调配置不会被设置页保存抹掉。
 *  `body` 只用于判定「哪些全局开关由本次提交决定」；文件宠物条目传 {}（全局开关不归它管）。 */
function passthrough(
  disk: Record<string, unknown> | undefined,
  pets: unknown[],
  body?: Record<string, unknown>,
): Record<string, unknown> & { pets: unknown[] } {
  const out: Record<string, unknown> = { pets };
  const owned = new Set<string>(['pets']);
  for (const key of GLOBAL_SWITCHES) {
    if (body && body[key] !== undefined) owned.add(key);
  }
  if (disk && typeof disk === 'object') {
    for (const key of Object.keys(disk)) {
      if (owned.has(key)) continue; // 白名单字段由本次提交决定
      // 只透传可精调的顶层字段，其余（如 memes/unknown/占位）一并保留，不丢弃用户内容
      out[key] = disk[key];
    }
  }
  for (const key of GLOBAL_SWITCHES) {
    if (body && body[key] !== undefined) out[key] = body[key];
  }
  return out as Record<string, unknown> & { pets: unknown[] };
}

/** 归属表：实例 id → 它当前生效的条目（与读路径**同一套规则**，不重复实现合并语义） */
function petOwners(paths: ConfigPaths): Map<string, string> {
  const owners = new Map<string, string>();
  for (const [entry, conf] of Object.entries(readAllConfig(paths))) {
    const list = Array.isArray(conf?.pets) ? (conf.pets as Record<string, unknown>[]) : [];
    for (const p of list) {
      const id = String(p?.id ?? '');
      if (id) owners.set(id, entry);
    }
  }
  return owners;
}

/**
 * 保存计划（PUT /config）：把设置页提交的**完整宠物列表**按 id 归属分流到各自的配置文件。
 *
 * 归属规则（唯一规则，与 readAllConfig 的条目划分一致）：
 *   - id 当前生效于某个文件宠物条目 → 写回**那个 pet/<前缀>-config.json**（顶层字段透传保留）；
 *   - 其余（main 条目实例、以及设置页新建、尚未落盘的实例）→ 写进 main-config.json。
 * 未收到任何实例的条目**不进计划**（宿主不动该文件）；主条目同理（main = null）。
 *
 * 全局开关（notificationsEnabled / whisperImageEnabled / chatImageEnabled）只归主条目：
 * 请求体传了才写，未传则透传磁盘旧值（不凭空造字段，也不把既有设置抹成默认）。
 *
 * 校验：任一实例字段非法、pets 为空、任一全局开关非布尔 → 整份返回 null（宿主回 400）。
 * 这条「全有或全无」是有意的：绝不写出半份配置。
 */
export function planConfigSave(paths: ConfigPaths, raw: unknown): ConfigSavePlan | null {
  const o = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const arr = Array.isArray(o.pets) ? o.pets : null;
  if (!arr || !arr.length) return null;
  for (const key of GLOBAL_SWITCHES) {
    const v = o[key];
    if (v !== undefined && typeof v !== 'boolean') return null;
  }

  const cleaned: Record<string, unknown>[] = [];
  for (const p of arr) {
    const c = cleanPet(p);
    if (!c) return null; // 一票否决：非法实例与合法实例混合时也整份拒绝
    cleaned.push(c);
  }

  const owners = petOwners(paths);
  // 条目 key → 文件（只有被提交实例的条目才进计划）
  const files = new Map(scanPetFiles(paths.petDir).map((f) => [f.prefix, f]));
  const mainPets: unknown[] = [];
  const byPrefix = new Map<string, unknown[]>();
  for (const p of cleaned) {
    const entry = owners.get(String(p.id));
    const file = entry !== undefined && entry !== 'main' ? files.get(entry) : undefined;
    if (!file) {
      mainPets.push(p);
      continue;
    }
    const list = byPrefix.get(file.prefix) ?? [];
    list.push(p);
    byPrefix.set(file.prefix, list);
  }

  const entries: ConfigSaveFile[] = [];
  for (const [prefix, pets] of byPrefix) {
    const file = files.get(prefix);
    if (!file) continue; // 不可能：byPrefix 的 key 都来自 files
    // 该条目在盘上的原文：既有实例按原顺序保留（未被提交的可能是校验不过被加载跳过的，
    // 设置页根本看不到它——不能因为「没提交」就把它从文件里删掉），提交值覆盖同 id，新 id 追加末尾。
    const disk = readJsonc(file.path);
    const submitted = new Map(pets.map((p) => [String((p as Record<string, unknown>).id), p]));
    const merged: unknown[] = [];
    const diskPets = Array.isArray(disk?.pets) ? (disk.pets as Record<string, unknown>[]) : [];
    for (const d of diskPets) {
      const id = String(d?.id ?? '');
      const s = submitted.get(id);
      if (s) {
        merged.push(s); // 提交值覆盖（同 id）
        submitted.delete(id);
      } else {
        merged.push(d); // 未提交 → 原样保留
      }
    }
    for (const p of submitted.values()) merged.push(p); // 新实例追加末尾
    entries.push({ path: file.path, prefix, config: passthrough(disk, merged) });
  }

  // 主条目：有主条目实例才写（只带全局开关却不带主条目实例 = 客户端状态不一致，拒绝）
  // 注意主条目是**整体替换**（不是像文件宠物那样保留未提交项）：设置页支持删除主条目实例，
  // 「没提交」正是删除的表达，二者不可兼得——文件宠物则相反（设置页禁止删除，故必须保留）。
  const anySwitch = GLOBAL_SWITCHES.some((k) => o[k] !== undefined);
  let main: ConfigSavePlan['main'] = null;
  if (mainPets.length > 0) main = passthrough(readJsonc(paths.userFile), mainPets, o);
  else if (anySwitch) return null;
  return { main, entries };
}
