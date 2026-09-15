/**
 * 保存计划单元测试 —— 钉住 PUT /config 的**多条目分流**契约：
 * 设置页提交的是一份完整宠物列表（主条目实例 + 文件宠物实例混在一起），
 * host 必须按 id 归属把每只实例送回**它自己所属的那个配置文件**：
 *   - 主条目实例（含设置页新建、尚未落盘的实例）→ main-config.json 的 pets
 *   - 文件宠物实例 → pet/<前缀>-config.json 的 pets（条目 key = 文件名前缀 = 素材根）
 * 并保证：未涉及的文件**一个字节都不动**（main 为 null = 不写 main-config.json），
 * 文件宠物自己文件的顶层字段（whisperPrompt / workStatusTexts / animations / animationWeights）
 * 必须原样活着——写进 main-config.json 既不生效也会被 seenIds 去重吃掉。
 *
 * 走完整 readAllConfig 管线（与生产同一路径）定位归属，用临时目录隔离真实文件。
 *
 * 跑法：node --experimental-strip-types --test src/host/save-config.test.ts
 */
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { planConfigSave, type ConfigPaths } from './config.ts';

/** 内置默认配置的完整最小形态（与 config.test.ts 同构） */
const BASE = {
  pets: [
    {
      id: 'main',
      name: '主宠',
      size: 462,
      balanceEnabled: false,
      whisperEnabled: false,
      workStatusEnabled: false,
      display: 'web',
      position: { corner: 'bottom-right', marginX: 40, marginY: 40 },
    },
  ],
  animations: {
    idle: ['待机'],
    turn: ['转向'],
    drag: ['拖拽'],
    clicks: ['点击'],
    moves: {
      default: { minDist: 100, maxDist: 300, margin: 100, leadSec: 0.2, tailSec: 0.2 },
      actions: [{ name: '走动', params: {} }],
    },
    categories: [],
    events: { balance: ['余额A'], whisper: ['碎碎念A'], workStatus: ['工作A', '工作B'] },
  },
  animationWeights: { idle: 10, turn: 5, move: 5 },
  physics: {
    gravity: 1400,
    restitution: 0.78,
    groundFriction: 2.5,
    ceilingBounce: true,
    throwPower: 1.0,
    petCollision: false,
  },
  whisperPrompt: '你是桌面宠物',
  chatMemoryRounds: 4,
  notificationsEnabled: true,
  eventsRefreshSec: { balance: 1800, whisper: 300 },
  workStatusTexts: [['在干活']],
};

/** 文件宠物文件：真实腊肠形状——顶层带着只属于它自己的字段（保存时必须原样活着） */
const PACK = {
  pets: [
    {
      id: 'dachshund1',
      name: '腊肠犬',
      size: 420,
      balanceEnabled: true,
      whisperEnabled: true,
      workStatusEnabled: true,
      display: 'both',
      position: { corner: 'bottom-right', marginX: 24, marginY: 100 },
    },
  ],
  animations: BASE.animations,
  animationWeights: { idle: 80, turn: 10, move: 10 },
  whisperPrompt: '你是腊肠犬',
  workStatusTexts: [['小短腿想想办法~']],
};

/** 主条目用户层：已有一只被用户改过的主宠（size 500）+ 手改的顶层字段 */
const MAIN_OVERLAY = {
  pets: [
    {
      id: 'main',
      name: '蓝毛小女仆',
      size: 500,
      balanceEnabled: true,
      whisperEnabled: false,
      workStatusEnabled: false,
      display: 'web',
      position: { corner: 'top-right', marginX: 24, marginY: 100 },
    },
  ],
  notificationsEnabled: true,
  whisperPrompt: '女仆人设',
};

/** 一只完整的可编辑实例（设置页提交的形态） */
function pet(id: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id,
    name: id,
    size: 400,
    balanceEnabled: false,
    whisperEnabled: false,
    workStatusEnabled: false,
    display: 'web',
    position: { corner: 'bottom-right', marginX: 24, marginY: 100 },
    ...over,
  };
}

/** 建临时目录（默认配置 + 主条目用户层 + 可选一个文件宠物），返回路径集与清理函数 */
function fixture(withPack = true): { paths: ConfigPaths; packFile: string; done: () => void } {
  const dir = mkdtempSync(join(tmpdir(), 'dsh-pet-save-test-'));
  const paths: ConfigPaths = {
    defaultFile: join(dir, 'default.jsonc'),
    userFile: join(dir, 'main-config.json'),
    petDir: join(dir, 'pet'),
  };
  writeFileSync(paths.defaultFile, JSON.stringify(BASE));
  writeFileSync(paths.userFile, JSON.stringify(MAIN_OVERLAY));
  const packFile = join(paths.petDir, 'dachshund-config.json');
  if (withPack) {
    mkdirSync(paths.petDir, { recursive: true });
    writeFileSync(packFile, JSON.stringify(PACK));
  }
  return { paths, packFile, done: () => rmSync(dir, { recursive: true, force: true }) };
}

/** 读盘上的文件（断言真实落盘内容用） */
const readBack = (p: string): Record<string, unknown> => JSON.parse(readFileSync(p, 'utf8'));

describe('planConfigSave —— 按 id 归属分流到各配置文件', () => {
  test('主条目实例 + 文件宠物实例混在一起提交 → 各回各的文件', () => {
    const { paths, packFile, done } = fixture();
    try {
      const plan = planConfigSave(paths, {
        pets: [pet('main', { name: '蓝毛小女仆', size: 500 }), pet('dachshund1', { size: 430 })],
        notificationsEnabled: true,
      });
      assert.ok(plan);
      assert.deepEqual(
        (plan.main?.pets as Record<string, unknown>[]).map((p) => p.id),
        ['main'],
      );
      assert.equal(plan.entries.length, 1);
      assert.equal(plan.entries[0].path, packFile);
      assert.deepEqual(
        (plan.entries[0].config.pets as Record<string, unknown>[]).map((p) => [p.id, p.size]),
        [['dachshund1', 430]],
      );
    } finally {
      done();
    }
  });

  test('文件宠物自己文件的顶层字段原样保留（whisperPrompt / workStatusTexts / animations）', () => {
    const { paths, done } = fixture();
    try {
      const plan = planConfigSave(paths, { pets: [pet('dachshund1', { size: 380 })] });
      assert.ok(plan);
      const cfg = plan.entries[0].config;
      assert.equal(cfg.whisperPrompt, '你是腊肠犬');
      assert.deepEqual(cfg.workStatusTexts, [['小短腿想想办法~']]);
      assert.deepEqual(cfg.animationWeights, { idle: 80, turn: 10, move: 10 });
      assert.deepEqual(cfg.animations, BASE.animations);
    } finally {
      done();
    }
  });

  test('只提交文件宠物实例 → main 为 null（一个字节都不动 main-config.json）', () => {
    const { paths, done } = fixture();
    try {
      const plan = planConfigSave(paths, { pets: [pet('dachshund1', { size: 380 })] });
      assert.ok(plan);
      assert.equal(plan.main, null);
      assert.deepEqual(
        (plan.entries[0].config.pets as Record<string, unknown>[]).map((p) => p.size),
        [380],
      );
    } finally {
      done();
    }
  });

  test('设置页新建、尚未落盘的 id → 归主条目', () => {
    const { paths, done } = fixture();
    try {
      const plan = planConfigSave(paths, { pets: [pet('main'), pet('pet-2', { size: 300 })] });
      assert.ok(plan);
      assert.deepEqual(
        (plan.main?.pets as Record<string, unknown>[]).map((p) => p.id),
        ['main', 'pet-2'],
      );
      assert.deepEqual(plan.entries, []);
    } finally {
      done();
    }
  });

  test('同一条目多实例：提交顺序原样保留，其余条目互不干扰', () => {
    const { paths, done } = fixture();
    try {
      const plan = planConfigSave(paths, { pets: [pet('dachshund1', { size: 401 }), pet('main')] });
      assert.ok(plan);
      assert.deepEqual(
        (plan.entries[0].config.pets as Record<string, unknown>[]).map((p) => p.size),
        [401],
      );
      assert.deepEqual(
        (plan.main?.pets as Record<string, unknown>[]).map((p) => p.id),
        ['main'],
      );
    } finally {
      done();
    }
  });

  test('主条目非白名单顶层字段（whisperPrompt 等）原样透传保留', () => {
    const { paths, done } = fixture();
    try {
      const plan = planConfigSave(paths, { pets: [pet('main')] });
      assert.equal(plan?.main?.whisperPrompt, '女仆人设');
    } finally {
      done();
    }
  });

  test('文件里被加载跳过的实例原样保留（设置页看不到它 → 保存不得顺手删掉）', () => {
    const { paths, packFile, done } = fixture();
    try {
      // 手写一只**会被加载跳过**的实例：id 与前面那只重复（mergePet 的 seenIds 判重后才跳过；
      // 注意 display 非法不会跳过——它只告警并取默认值，那种实例设置页是看得见的）。
      const raw = readBack(packFile) as { pets: Record<string, unknown>[] };
      raw.pets.push({ ...raw.pets[0], name: '手写重复实例' }); // 同 id = dachshund1
      writeFileSync(packFile, JSON.stringify(raw));

      // 设置页只提交它看得见的那只（改了大小）
      const plan = planConfigSave(paths, { pets: [pet('dachshund1', { size: 411 })] });
      assert.ok(plan);
      const out = plan.entries[0].config.pets as Record<string, unknown>[];
      assert.equal(out.length, 2); // 被跳过的第二只仍在文件里，没被顺手删掉
      assert.equal(out[0].size, 411); // 看得见的那只正常更新
      assert.equal(out[1].name, '手写重复实例'); // 未被改写
    } finally {
      done();
    }
  });

  test('同条目内已声明的多只实例：提交值覆盖同 id，其余按原顺序保留', () => {
    const { paths, packFile, done } = fixture();
    try {
      const raw = readBack(packFile) as { pets: Record<string, unknown>[] };
      raw.pets.push({ ...raw.pets[0], id: 'dachshund2' });
      writeFileSync(packFile, JSON.stringify(raw));
      const plan = planConfigSave(paths, {
        pets: [pet('dachshund1', { size: 401 }), pet('dachshund2', { size: 402 })],
      });
      assert.ok(plan);
      assert.deepEqual(
        (plan.entries[0].config.pets as Record<string, unknown>[]).map((p) => [p.id, p.size]),
        [
          ['dachshund1', 401],
          ['dachshund2', 402],
        ],
      );
    } finally {
      done();
    }
  });
});

describe('planConfigSave —— 校验失败一律整体拒绝（宿主回 400）', () => {
  test('非数组 pets / 缺 pets / 缺 notificationsEnabled 类型', () => {
    const { paths, done } = fixture();
    try {
      assert.equal(planConfigSave(paths, { pets: 'x' }), null);
      assert.equal(planConfigSave(paths, {}), null);
      assert.equal(planConfigSave(paths, { pets: [pet('main')], notificationsEnabled: 'yes' }), null);
    } finally {
      done();
    }
  });

  test('提交列表内 id 重复 → 整份拒绝（放行会在下次加载时被去重丢掉一只）', () => {
    const { paths, done } = fixture();
    try {
      assert.equal(planConfigSave(paths, { pets: [pet('main'), pet('main')] }), null);
      assert.equal(planConfigSave(paths, { pets: [pet('dachshund1'), pet('dachshund1')] }), null);
    } finally {
      done();
    }
  });

  test('size 必须 ≥1：0.5 会被读取端判非法并改回默认，写入端必须同样拒绝', () => {
    const { paths, done } = fixture();
    try {
      // 读路径 petNumber(..., min=1)：0.5 落盘后会被读成默认值 → 写入端提前拒绝，避免读写不一致
      assert.equal(planConfigSave(paths, { pets: [pet('main', { size: 0.5 })] }), null);
      assert.equal(planConfigSave(paths, { pets: [pet('main', { size: 0 })] }), null);
      assert.equal(planConfigSave(paths, { pets: [pet('main', { size: -3 })] }), null);
      assert.ok(planConfigSave(paths, { pets: [pet('main', { size: 1 })] })); // 边界值放行
    } finally {
      done();
    }
  });

  test('pack 文件声明的 id 与主宠撞名 → 主宠仍归主条目（先到者胜，同 seenIds）', () => {
    const { paths, done } = fixture();
    try {
      // 该 pack 声明的实例 id 与主宠相同：读取端 seenIds 会丢掉它（main 先处理），
      // 归属表必须同样判给主条目，否则主宠会被分流进 pack 文件、保存直接 400。
      writeFileSync(join(paths.petDir, 'clash-config.json'), JSON.stringify({ pets: [pet('main')] }));
      const plan = planConfigSave(paths, { pets: [pet('main', { size: 470 })], notificationsEnabled: true });
      assert.ok(plan);
      assert.deepEqual(
        (plan.main?.pets as Record<string, unknown>[]).map((p) => p.id),
        ['main'],
      );
      assert.deepEqual(plan.entries, []);
    } finally {
      done();
    }
  });

  test('pack 文件没写 pets → 该条目没有实例，不劫持主宠归属，保存照常成功', () => {
    const { paths, done } = fixture();
    try {
      // 手写一个只有顶层人设、没有 pets 的 pack 文件：该条目就是「零实例」，
      // 主宠 main 只能归主条目；归属表若把主宠记到这个条目名下，保存随即 400。
      writeFileSync(join(paths.petDir, 'custom-config.json'), JSON.stringify({ whisperPrompt: '自定义人设' }));
      const plan = planConfigSave(paths, { pets: [pet('main', { size: 470 })], notificationsEnabled: true });
      assert.ok(plan, '保存不应失败');
      assert.deepEqual(
        (plan.main?.pets as Record<string, unknown>[]).map((p) => p.id),
        ['main'],
      );
      assert.deepEqual(plan.entries, []); // 主宠没有被分流进 custom-config.json
    } finally {
      done();
    }
  });

  test('文件宠物声明带首尾空格的 id → 归属表与 mergePet 同一归一化，不误写进 main', () => {
    const { paths, packFile, done } = fixture();
    try {
      // mergePet 会把 id trim 后使用（读到的实例 id = dachshund1）；归属表必须同样 trim，
      // 否则它认不出这个 id 属于本文件，会把实例分流进 main-config.json，下次加载即被去重吃掉。
      writeFileSync(packFile, JSON.stringify({ ...PACK, pets: [{ ...PACK.pets[0], id: ' dachshund1 ' }] }));
      const plan = planConfigSave(paths, { pets: [pet('dachshund1', { size: 430 })] });
      assert.ok(plan);
      assert.equal(plan.main, null); // 未被误判成主条目实例
      assert.equal(plan.entries.length, 1);
      assert.equal(plan.entries[0].path, packFile);
      // 分流对了还不够——必须断言**合并结果**：磁盘 id 带空格时，若回写合并用未归一化的
      // 磁盘 id 去查提交表就会查不中，于是原样吐出旧实例，用户改的 size 静默丢失。
      // 只断言 entries.length 会让这条缺陷从测试里溜过去（假阳性）。
      assert.deepEqual(
        (plan.entries[0].config.pets as Record<string, unknown>[]).map((p) => ({ id: p.id, size: p.size })),
        [{ id: 'dachshund1', size: 430 }],
      );
      assert.equal((plan.entries[0].config as Record<string, unknown>).whisperPrompt, '你是腊肠犬');
    } finally {
      done();
    }
  });

  test('提交带首尾空格的 id → 写路径与读路径同一归一化（cleanPet 必须 trim）', () => {
    const { paths, packFile, done } = fixture();
    try {
      // 读路径 mergePet 会把 id trim 后使用；写路径若原样收下 ' dachshund1 '，
      // 落盘后读取端读到的却是 'dachshund1'——同一个宠物在读写两侧是两个 id。
      const plan = planConfigSave(paths, { pets: [{ ...pet('dachshund1', { size: 430 }), id: ' dachshund1 ' }] });
      assert.ok(plan);
      assert.equal(plan.entries.length, 1, 'trim 后应归属文件宠物条目');
      assert.equal(plan.entries[0].path, packFile);
      assert.equal(plan.main, null);
      assert.deepEqual(
        (plan.entries[0].config.pets as Record<string, unknown>[]).map((p) => ({ id: p.id, size: p.size })),
        [{ id: 'dachshund1', size: 430 }],
      );
    } finally {
      done();
    }
  });

  test('实例字段非法（size / display / corner / id）→ 整份拒绝，不做部分写入', () => {
    const { paths, done } = fixture();
    try {
      const bads: Record<string, unknown>[] = [
        pet('main', { size: 0 }),
        pet('main', { size: 'big' }),
        pet('main', { display: 'screen' }),
        pet('main', { position: { corner: 'middle', marginX: 0, marginY: 0 } }),
        pet('', {}),
        pet('a/b', {}),
        pet('main', { balanceEnabled: 'yes' }),
        pet('main', { position: { corner: 'top-left', marginX: NaN, marginY: 0 } }),
      ];
      for (const bad of bads) {
        assert.equal(planConfigSave(paths, { pets: [bad] }), null, JSON.stringify(bad));
      }
    } finally {
      done();
    }
  });

  test('非法实例与合法实例混合 → 仍整体拒绝（绝不写半份）', () => {
    const { paths, done } = fixture();
    try {
      assert.equal(planConfigSave(paths, { pets: [pet('main'), pet('dachshund1', { size: -1 })] }), null);
    } finally {
      done();
    }
  });
});

describe('planConfigSave —— 删光主宠物（显式空 pets = 真正的零宠物）', () => {
  test('显式 pets: [] → 仍写 main（pets 为空）+ 开关，主宠物真正消失', () => {
    const { paths, done } = fixture();
    try {
      const plan = planConfigSave(paths, { pets: [], notificationsEnabled: true });
      assert.ok(plan, '空 pets 必须被接受：这是设置页删光宠物后的落盘形态');
      assert.deepEqual(plan.main?.pets, []);
      assert.equal(plan.main?.notificationsEnabled, true);
      assert.equal(plan.main?.whisperPrompt, '女仆人设'); // 顶层字段仍透传保留
      assert.deepEqual(plan.entries, []);
    } finally {
      done();
    }
  });

  test('显式 pets: [] 但**不带任何全局开关** → 仍必须写 main（否则删除请求被静默吞掉）', () => {
    const { paths, done } = fixture();
    try {
      // 设置页保存总是带开关，所以真实 UI 走不到这条；但 PUT /config 是公开契约，
      // 只提交 { pets: [] } 时若 main = null，宿主不会写盘却照样回 200——
      // 客户端以为删干净了，实际磁盘原封不动，下次刷新宠物全部复活。
      // 空 pets 本身就是「清空主条目」的明确意图，与是否带开关无关。
      const plan = planConfigSave(paths, { pets: [] });
      assert.ok(plan, '空 pets 必须被接受');
      assert.ok(plan.main, '不带开关也必须产出主条目计划，否则宿主不写盘 = 静默无操作');
      assert.deepEqual(plan.main.pets, []);
      assert.equal(plan.main.whisperPrompt, '女仆人设'); // 顶层字段仍透传
      assert.equal(plan.main.notificationsEnabled, true); // 未提交的开关透传磁盘旧值
    } finally {
      done();
    }
  });

  test('删光主宠物但保留文件宠物 → main 写空 pets，文件宠物照常写回（原「至少保留一个宠物」的触发场景）', () => {
    const { paths, packFile, done } = fixture();
    try {
      // 设置页提交的是完整列表：删掉唯一主宠后，列表里只剩文件宠物。
      // 旧实现因「带了全局开关却没有任何主条目实例」整份拒绝 → 用户被一句
      // 「至少保留一个宠物」挡住，而删除权其实不该被这样剥夺。
      const plan = planConfigSave(paths, {
        pets: [pet('dachshund1', { size: 430 })],
        notificationsEnabled: true,
      });
      assert.ok(plan, '只剩文件宠物时也必须能保存');
      assert.deepEqual(plan.main?.pets, []);
      assert.equal(plan.main?.notificationsEnabled, true);
      assert.equal(plan.entries.length, 1);
      assert.equal(plan.entries[0].path, packFile);
      assert.deepEqual(
        (plan.entries[0].config.pets as Record<string, unknown>[]).map((p) => p.size),
        [430],
      );
    } finally {
      done();
    }
  });

  test('落盘后读回：main 的 pets 为空数组（不复活内置默认宠物），文件宠物仍在', async () => {
    const { paths, done } = fixture();
    try {
      const plan = planConfigSave(paths, { pets: [], notificationsEnabled: true });
      assert.ok(plan);
      writeFileSync(paths.userFile, JSON.stringify(plan.main, null, 2));
      // 重新读：与生产同一路径。写侧放行还不够——读侧若把「显式空数组」当「字段缺失」，
      // 内置默认宠物就会在下次加载时复活，删除形同虚设。
      const { readAllConfig, flattenPetList } = await import('./config.ts');
      const merged = readAllConfig(paths);
      assert.deepEqual(merged.main.pets, []);
      assert.deepEqual(
        flattenPetList(merged).map((p) => p.id),
        ['dachshund1'],
      );
    } finally {
      done();
    }
  });
});

describe('planConfigSave —— 无文件宠物时行为与旧实现一致（纯主条目）', () => {
  test('无 pet/ 目录 → 全部归 main，entries 为空', () => {
    const { paths, done } = fixture(false);
    try {
      const plan = planConfigSave(paths, { pets: [pet('main'), pet('pet-2')], notificationsEnabled: true });
      assert.ok(plan);
      assert.deepEqual(
        (plan.main?.pets as Record<string, unknown>[]).map((p) => p.id),
        ['main', 'pet-2'],
      );
      assert.equal(plan.main?.notificationsEnabled, true);
      assert.deepEqual(plan.entries, []);
    } finally {
      done();
    }
  });
});

describe('planConfigSave —— 落盘后的成品自洽（写回的文件能被重新读成同一只宠物）', () => {
  test('写回文件宠物文件后，readAllConfig 读到的实例与提交值一致', async () => {
    const { paths, packFile, done } = fixture();
    try {
      const plan = planConfigSave(paths, {
        pets: [
          pet('dachshund1', { size: 388, display: 'both', position: { corner: 'top-left', marginX: 8, marginY: 12 } }),
        ],
      });
      assert.ok(plan);
      writeFileSync(packFile, JSON.stringify(plan.entries[0].config, null, 2));
      // 重新读：与生产同一路径
      const { readAllConfig } = await import('./config.ts');
      const merged = readAllConfig(paths);
      const d = (merged.dachshund.pets as Record<string, unknown>[])[0];
      assert.equal(d.id, 'dachshund1');
      assert.equal(d.size, 388);
      assert.equal(d.display, 'both');
      assert.deepEqual(d.position, { corner: 'top-left', marginX: 8, marginY: 12 });
      // 条目级字段仍在
      assert.equal(merged.dachshund.whisperPrompt, '你是腊肠犬');
      assert.deepEqual(readBack(packFile).workStatusTexts, [['小短腿想想办法~']]);
    } finally {
      done();
    }
  });
});
