'use strict';
/* HTTP Range 解析（只支持单区间 bytes，够静态音频/视频用）。
 *
 * 纯函数：不读文件、不碰网络，便于单测（cloud/test/range.test.js）。
 * 背景：多人版要用服务端供给 4.88MB 的 WAV 做 BGM（REQ-000022），
 * 移动端浏览器只有在响应带 accept-ranges 且支持 206 时才能可靠分段取流与循环。
 *
 * 返回约定：
 *   null                                   没有 Range 头 / 语法不认识 / 多区间（RFC 允许忽略，按整文件 200 回）
 *   { ok: true, start, end }               可满足的闭区间（end 已按文件大小收敛）
 *   { ok: false, unsatisfiable: true }     语法合法但一个字节都取不到（回 416）
 */

const UNIT = 'bytes';
const PREFIX = UNIT + '=';      // 请求头：Range: bytes=0-1023
const HEADER_UNIT = UNIT + ' '; // 响应头：Content-Range: bytes 0-1023/1234（注意是空格，不是等号）

/**
 * @param {string|null|undefined} header 请求头 Range 的值，例如 "bytes=0-1023"
 * @param {number} size                  文件总字节数
 */
function parseRange(header, size) {
  if (typeof header !== 'string' || !header.trim()) return null;
  const raw = header.trim();
  if (raw.slice(0, PREFIX.length).toLowerCase() !== PREFIX) return null;

  const spec = raw.slice(PREFIX.length).trim();
  if (!spec || spec.includes(',')) return null;          // 多区间：忽略，整文件返回（不是错误）

  const m = /^(\d*)-(\d*)$/.exec(spec);
  if (!m) return null;
  const [, first, last] = m;
  if (first === '' && last === '') return null;

  const total = Number(size);
  if (!Number.isFinite(total) || total <= 0) return { ok: false, unsatisfiable: true };

  if (first === '') {                                     // 后缀式：bytes=-500 → 最后 500 字节
    const suffix = Number(last);
    if (!Number.isFinite(suffix) || suffix <= 0) return { ok: false, unsatisfiable: true };
    return { ok: true, start: Math.max(0, total - suffix), end: total - 1 };
  }

  const start = Number(first);
  if (!Number.isFinite(start) || start >= total) return { ok: false, unsatisfiable: true };
  let end = last === '' ? total - 1 : Number(last);
  if (!Number.isFinite(end) || end < start) return { ok: false, unsatisfiable: true };
  if (end >= total) end = total - 1;
  return { ok: true, start, end };
}

/** 便于 serveFile 拼响应头：长度与 Content-Range 文本。 */
function contentRange({ start, end }, size) {
  return `${HEADER_UNIT}${start}-${end}/${size}`;
}

/** 416 用的 Content-Range：bytes * /总长。 */
function unsatisfiedRange(size) {
  return `${HEADER_UNIT}*/${size}`;
}

module.exports = { parseRange, contentRange, unsatisfiedRange };
