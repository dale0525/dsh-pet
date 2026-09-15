/**
 * 移动端判定与订阅模块测试
 *
 * 验证契约：
 * 1. 媒体查询串精确等于 '(pointer: coarse), (max-width: 767.98px)'（防止后人改动阈值）
 * 2. isMobileEnvironment：
 *    - matchMedia matches: true / false 判定
 *    - 查询参数原样传递
 *    - 无 matchMedia 或非函数兜底返回 false
 *    - Node 环境无参调用返回 false 且不抛错
 * 3. subscribeMobileEnvironment：
 *    - 同步初始回调
 *    - addEventListener 事件变化驱动
 *    - 幂等解绑及解绑后不再回调
 *    - 无 matchMedia 时回调一次 false 并返回安全空函数（含无参调用场景）
 *
 * 跑法：node --experimental-strip-types --test src/client/mobile.test.ts
 */
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { MOBILE_MEDIA_QUERY, isMobileEnvironment, subscribeMobileEnvironment } from './mobile.ts';

describe('MOBILE_MEDIA_QUERY —— 媒体查询契约', () => {
  test("精确等于 '(pointer: coarse), (max-width: 767.98px)'", () => {
    assert.equal(MOBILE_MEDIA_QUERY, '(pointer: coarse), (max-width: 767.98px)');
  });
});

describe('isMobileEnvironment —— 移动端判定', () => {
  test('伪造 matchMedia 返回 matches: true 时返回 true', () => {
    const env = {
      matchMedia: () => ({ matches: true }),
    };
    assert.equal(isMobileEnvironment(env), true);
  });

  test('伪造 matchMedia 返回 matches: false 时返回 false', () => {
    const env = {
      matchMedia: () => ({ matches: false }),
    };
    assert.equal(isMobileEnvironment(env), false);
  });

  test('把 MOBILE_MEDIA_QUERY 原样传给 matchMedia', () => {
    let capturedQuery = '';
    const env = {
      matchMedia: (query: string) => {
        capturedQuery = query;
        return { matches: false };
      },
    };
    isMobileEnvironment(env);
    assert.equal(capturedQuery, MOBILE_MEDIA_QUERY);
  });

  test('env 为 {}（无 matchMedia）时返回 false', () => {
    const env = {};
    assert.equal(isMobileEnvironment(env), false);
  });

  test('matchMedia 为非函数值时返回 false', () => {
    const envUndef = { matchMedia: undefined };
    assert.equal(
      isMobileEnvironment(envUndef as unknown as { matchMedia: (q: string) => { matches: boolean } }),
      false,
    );

    const envString = { matchMedia: 'not-a-function' };
    assert.equal(
      isMobileEnvironment(envString as unknown as { matchMedia: (q: string) => { matches: boolean } }),
      false,
    );
  });

  test('不带参数且在 Node 环境（全局无 matchMedia）时返回 false 且不抛错', () => {
    const origMatchMedia = (globalThis as { matchMedia?: unknown }).matchMedia;
    delete (globalThis as { matchMedia?: unknown }).matchMedia;
    try {
      assert.equal(isMobileEnvironment(), false);
    } finally {
      if (origMatchMedia !== undefined) {
        (globalThis as { matchMedia?: unknown }).matchMedia = origMatchMedia;
      }
    }
  });
});

describe('subscribeMobileEnvironment —— 移动端判定变化订阅', () => {
  test('调用时同步回调一次初始值（在 subscribe 返回前即已回调）', () => {
    const calls: boolean[] = [];
    const env = {
      matchMedia: () => ({
        matches: true,
        addEventListener: () => {},
        removeEventListener: () => {},
      }),
    };

    const unsubscribe = subscribeMobileEnvironment((val) => {
      calls.push(val);
    }, env);

    assert.equal(calls.length, 1);
    assert.equal(calls[0], true);
    unsubscribe();
  });

  test('伪造 MediaQueryList 暴露 addEventListener/removeEventListener，捕获 change handler 并触发新值', () => {
    let changeHandler: (() => void) | undefined;
    const mql = {
      matches: false,
      addEventListener: (type: string, listener: () => void) => {
        if (type === 'change') {
          changeHandler = listener;
        }
      },
      removeEventListener: () => {},
    };
    const env = {
      matchMedia: () => mql,
    };

    const received: boolean[] = [];
    subscribeMobileEnvironment((val) => received.push(val), env);

    assert.deepEqual(received, [false]);
    assert.ok(typeof changeHandler === 'function');

    mql.matches = true;
    changeHandler?.();
    assert.deepEqual(received, [false, true]);

    mql.matches = false;
    changeHandler?.();
    assert.deepEqual(received, [false, true, false]);
  });

  test('解绑后，再触发 change handler 不再回调；解绑函数调用两次不抛错', () => {
    let changeHandler: (() => void) | undefined;
    let removeCount = 0;
    const mql = {
      matches: true,
      addEventListener: (type: string, listener: () => void) => {
        if (type === 'change') {
          changeHandler = listener;
        }
      },
      removeEventListener: () => {
        removeCount++;
      },
    };
    const env = {
      matchMedia: () => mql,
    };

    const received: boolean[] = [];
    const unsubscribe = subscribeMobileEnvironment((val) => received.push(val), env);

    assert.deepEqual(received, [true]);

    // 首次解绑
    assert.doesNotThrow(() => unsubscribe());
    assert.equal(removeCount, 1);

    // 再次解绑（幂等测试）
    assert.doesNotThrow(() => unsubscribe());
    assert.equal(removeCount, 1);

    // 触发捕获的 changeHandler，不应产生新的回调
    mql.matches = false;
    changeHandler?.();
    assert.deepEqual(received, [true]);
  });

  test('无 matchMedia 时回调一次 false，返回的解绑函数可安全调用且幂等', () => {
    // 1) 显式传 env 为 {}
    const received1: boolean[] = [];
    const env = {};

    const unsubscribe1 = subscribeMobileEnvironment((val) => received1.push(val), env);
    assert.deepEqual(received1, [false]);

    assert.doesNotThrow(() => unsubscribe1());
    assert.doesNotThrow(() => unsubscribe1());
    assert.deepEqual(received1, [false]);

    // 2) 不传 env 且全局无 matchMedia（Node 默认环境）
    const origMatchMedia = (globalThis as { matchMedia?: unknown }).matchMedia;
    delete (globalThis as { matchMedia?: unknown }).matchMedia;
    try {
      const received2: boolean[] = [];
      const unsubscribe2 = subscribeMobileEnvironment((val) => received2.push(val));
      assert.deepEqual(received2, [false]);
      assert.doesNotThrow(() => unsubscribe2());
      assert.doesNotThrow(() => unsubscribe2());
      assert.deepEqual(received2, [false]);
    } finally {
      if (origMatchMedia !== undefined) {
        (globalThis as { matchMedia?: unknown }).matchMedia = origMatchMedia;
      }
    }
  });

  test('通过标准 addEventListener/removeEventListener 注册与解绑 change 监听', () => {
    let changeHandler: (() => void) | undefined;
    let removeEventListenerCalls = 0;

    const mql = {
      matches: false,
      addEventListener: (_type: string, listener: () => void) => {
        changeHandler = listener;
      },
      removeEventListener: () => {
        removeEventListenerCalls++;
      },
    };
    const env = {
      matchMedia: () => mql,
    };

    const received: boolean[] = [];
    const unsubscribe = subscribeMobileEnvironment((val) => received.push(val), env);

    assert.deepEqual(received, [false]);
    assert.ok(typeof changeHandler === 'function');

    mql.matches = true;
    changeHandler?.();
    assert.deepEqual(received, [false, true]);

    // 解绑
    unsubscribe();
    assert.equal(removeEventListenerCalls, 1);

    // 解绑后不再回调
    mql.matches = false;
    changeHandler?.();
    assert.deepEqual(received, [false, true]);

    // 重复解绑安全
    assert.doesNotThrow(() => unsubscribe());
    assert.equal(removeEventListenerCalls, 1);
  });
});
