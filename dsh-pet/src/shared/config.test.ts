/**
 * 拍平逻辑单元测试 —— 钉住「成品聚合 → 渲染用宠物列表」这一层的两个关键契约：
 *
 * 1. **assetRoot = 条目 key**：设置页保存时按它把实例分流回各自的配置文件
 *    （host planConfigSave 的归属判据），素材 URL 也用它（多实例共享同一素材目录）。
 *    一旦这里错位，文件宠物就会被写进 main-config.json（既不生效，还会被 seenIds 去重吃掉）。
 * 2. **条目级字段吹入**：animations / animationWeights / eventsRefreshSec / physics /
 *    workStatusTexts 从条目取，多实例共享同一份——实例自己写的同名字段不参与。
 *
 * 跑法：node --experimental-strip-types --test src/shared/config.test.ts
 */
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { flattenConfigPets } from './config.ts';

/** 一只最小的合法实例（拍平不校验字段，这里只为断言取用方便） */
const pet = (id: string, name: string) => ({
  id,
  name,
  size: 400,
  balanceEnabled: false,
  whisperEnabled: false,
  workStatusEnabled: false,
  display: 'web',
  position: { corner: 'bottom-right', marginX: 24, marginY: 100 },
});

/** 与生产同形的成品聚合：main 条目（1 只）+ 文件宠物条目（2 只多实例共享同一素材根） */
const MERGED = {
  main: {
    pets: [pet('main', '蓝毛小女仆')],
    animations: { idle: ['主待机'], tag: 'main' },
    animationWeights: { idle: 10, turn: 5, move: 5 },
    eventsRefreshSec: { balance: 1800, whisper: 300 },
    physics: { gravity: 1400 },
    workStatusTexts: [['主文案']],
  },
  dachshund: {
    pets: [pet('dachshund1', '腊肠犬'), pet('dachshund2', '腊肠犬二号')],
    animations: { idle: ['犬待机'], tag: 'pack' },
    animationWeights: { idle: 80, turn: 10, move: 10 },
    eventsRefreshSec: { balance: 60 },
    physics: { gravity: 900 },
    workStatusTexts: [['犬文案']],
  },
};

describe('flattenConfigPets —— assetRoot 是条目 key（保存分流的唯一判据）', () => {
  test('每条实例的 assetRoot = 它所属条目的 key，与 id 无关', () => {
    const list = flattenConfigPets(MERGED);
    assert.deepEqual(
      list.map((p) => [p.id, p.assetRoot]),
      [
        ['main', 'main'],
        ['dachshund1', 'dachshund'],
        ['dachshund2', 'dachshund'],
      ],
    );
  });

  test('同一条目多实例共享同一 assetRoot（素材目录共用）', () => {
    const roots = flattenConfigPets(MERGED)
      .filter((p) => p.id.startsWith('dachshund'))
      .map((p) => p.assetRoot);
    assert.deepEqual(roots, ['dachshund', 'dachshund']);
  });

  test('条目顺序原样保留，条目内实例顺序原样保留', () => {
    const list = flattenConfigPets({
      zeta: { pets: [pet('z1', 'Z1')] },
      main: { pets: [pet('main', 'M'), pet('m2', 'M2')] },
    });
    assert.deepEqual(
      list.map((p) => p.id),
      ['z1', 'main', 'm2'],
    );
  });
});

describe('flattenConfigPets —— 条目级字段吹入（多实例共享）', () => {
  test('animations / weights / 周期 / 物理 / 文案 逐条来自各自条目', () => {
    const list = flattenConfigPets(MERGED);
    const m = list.find((p) => p.id === 'main')!;
    const d = list.find((p) => p.id === 'dachshund1')!;
    assert.deepEqual(m.animations, MERGED.main.animations);
    assert.deepEqual(m.animationWeights, MERGED.main.animationWeights);
    assert.deepEqual(m.eventsRefreshSec, MERGED.main.eventsRefreshSec);
    assert.deepEqual(m.physics, MERGED.main.physics);
    assert.deepEqual(m.workStatusTexts, MERGED.main.workStatusTexts);
    assert.deepEqual(d.animations, MERGED.dachshund.animations);
    assert.deepEqual(d.animationWeights, MERGED.dachshund.animationWeights);
    assert.deepEqual(d.eventsRefreshSec, MERGED.dachshund.eventsRefreshSec);
    assert.deepEqual(d.physics, MERGED.dachshund.physics);
    assert.deepEqual(d.workStatusTexts, MERGED.dachshund.workStatusTexts);
  });

  test('同一条目内多实例拿到同一份条目级字段（不是各自缺省）', () => {
    const [a, b] = flattenConfigPets(MERGED).filter((p) => p.id.startsWith('dachshund'));
    assert.deepEqual(a.animations, b.animations);
    assert.deepEqual(a.workStatusTexts, b.workStatusTexts);
  });

  test('条目缺条目级字段 → 该字段为 undefined（不伪造、不回落别的条目）', () => {
    const list = flattenConfigPets({ main: { pets: [pet('main', 'M')] } });
    assert.equal(list[0].animations, undefined);
    assert.equal(list[0].animationWeights, undefined);
    assert.equal(list[0].eventsRefreshSec, undefined);
    assert.equal(list[0].physics, undefined);
    assert.equal(list[0].workStatusTexts, undefined);
    assert.equal(list[0].assetRoot, 'main'); // assetRoot 永远有值
  });

  test('空聚合 / pets 非数组 → 空列表，不抛异常', () => {
    assert.deepEqual(flattenConfigPets({}), []);
    assert.deepEqual(flattenConfigPets({ main: {} }), []);
    assert.deepEqual(flattenConfigPets({ main: { pets: 'x' as unknown as [] } }), []);
  });
});

describe('flattenConfigPets —— 不再输出 extra 标记（旧标识符已彻底移除）', () => {
  test('拍平结果里没有 extra 字段（无论主条目还是文件宠物）', () => {
    for (const p of flattenConfigPets(MERGED)) {
      assert.equal('extra' in p, false, p.id + ' 仍带 extra 字段');
    }
  });
});
