'use strict';
/* parseRange / contentRange / unsatisfiedRange 的定向单测（REQ-000022）。
 * 只导入纯函数，不写任何生产数据、不起服务。
 * 运行：node --test cloud/test/range.test.js      （在 cloud/ 下则是 node --test test/range.test.js）
 */

const test = require('node:test');
const assert = require('node:assert');
const { parseRange, contentRange, unsatisfiedRange } = require('../server/range');

const SIZE = 5120044;   // music/seaside_lazy_loop_40s.wav 的实际字节数

test('没有 Range 头 → null（按整文件 200 返回）', () => {
  assert.strictEqual(parseRange(undefined, SIZE), null);
  assert.strictEqual(parseRange(null, SIZE), null);
  assert.strictEqual(parseRange('', SIZE), null);
  assert.strictEqual(parseRange('   ', SIZE), null);
});

test('别的单位或不认识的语法 → null（RFC 允许忽略）', () => {
  assert.strictEqual(parseRange('items=0-1', SIZE), null);
  assert.strictEqual(parseRange('bytes=abc', SIZE), null);
  assert.strictEqual(parseRange('bytes=-', SIZE), null);
  assert.strictEqual(parseRange('bytes=0-1,5-6', SIZE), null);   // 多区间：忽略
});

test('bytes=0- → 从 0 到文件末尾', () => {
  assert.deepStrictEqual(parseRange('bytes=0-', SIZE), { ok: true, start: 0, end: SIZE - 1 });
});

test('bytes=start-end 原样返回闭区间', () => {
  assert.deepStrictEqual(parseRange('bytes=0-1023', SIZE), { ok: true, start: 0, end: 1023 });
  assert.deepStrictEqual(parseRange('bytes=100-199', SIZE), { ok: true, start: 100, end: 199 });
  assert.deepStrictEqual(parseRange('bytes=0-0', SIZE), { ok: true, start: 0, end: 0 });
  assert.deepStrictEqual(parseRange('BYTES=0-9', SIZE), { ok: true, start: 0, end: 9 });  // 大小写不敏感
});

test('end 超过文件大小时收敛到末尾', () => {
  assert.deepStrictEqual(parseRange(`bytes=100-${SIZE + 9999}`, SIZE), { ok: true, start: 100, end: SIZE - 1 });
});

test('后缀式 bytes=-N → 最后 N 字节', () => {
  assert.deepStrictEqual(parseRange('bytes=-500', SIZE), { ok: true, start: SIZE - 500, end: SIZE - 1 });
  assert.deepStrictEqual(parseRange(`bytes=-${SIZE + 10}`, SIZE), { ok: true, start: 0, end: SIZE - 1 });
});

test('越界与自相矛盾 → unsatisfiable（回 416）', () => {
  assert.deepStrictEqual(parseRange('bytes=99999999-', SIZE), { ok: false, unsatisfiable: true });
  assert.deepStrictEqual(parseRange(`bytes=${SIZE}-`, SIZE), { ok: false, unsatisfiable: true });
  assert.deepStrictEqual(parseRange('bytes=500-100', SIZE), { ok: false, unsatisfiable: true });
  assert.deepStrictEqual(parseRange('bytes=-0', SIZE), { ok: false, unsatisfiable: true });
});

test('空文件任何区间都不可满足', () => {
  assert.deepStrictEqual(parseRange('bytes=0-', 0), { ok: false, unsatisfiable: true });
  assert.strictEqual(parseRange('bytes=0-', 0).ok, false);
});

test('响应头文本格式', () => {
  assert.strictEqual(contentRange({ start: 0, end: 1023 }, SIZE), 'bytes 0-1023/5120044');
  assert.strictEqual(unsatisfiedRange(SIZE), 'bytes */5120044');
});
