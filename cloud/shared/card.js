'use strict';
/* 动作卡：规格校验。服务端收到上传的 card.png + manifest.json 后，
   用这里的函数做真实校验（尺寸、四角透明、manifest 字段），不信任客户端声明。 */

const crypto = require('node:crypto');
const { CARD, DIRECTIONS } = require('./const');
const { decodePng, alphaAt } = require('./png');

const MANIFEST_FIELDS = ['frame', 'cols', 'rows', 'rowOrder', 'footLine', 'fps'];

/**
 * 校验 manifest 形状。
 * @returns {{ok:boolean, errors:string[], manifest?:object}}
 */
function validateManifest(input) {
  const errors = [];
  let m = input;
  if (typeof m === 'string') {
    try { m = JSON.parse(m); } catch (e) { return { ok: false, errors: ['manifest 不是合法 JSON'] }; }
  }
  if (!m || typeof m !== 'object') return { ok: false, errors: ['manifest 必须是对象'] };

  for (const f of MANIFEST_FIELDS) {
    if (!(f in m)) errors.push(`manifest 缺少字段 ${f}`);
  }
  if (!errors.length) {
    if (m.frame !== CARD.frame) errors.push(`单帧尺寸必须是 ${CARD.frame}，收到 ${m.frame}`);
    if (m.cols !== CARD.cols) errors.push(`列数必须是 ${CARD.cols}，收到 ${m.cols}`);
    if (m.rows !== CARD.rows) errors.push(`行数必须是 ${CARD.rows}，收到 ${m.rows}`);
    if (m.fps !== CARD.fps) errors.push(`帧率必须是 ${CARD.fps}，收到 ${m.fps}`);
    if (m.footLine !== CARD.footLine) errors.push(`脚底线必须是 ${CARD.footLine}，收到 ${m.footLine}`);
    if (!Array.isArray(m.rowOrder) || m.rowOrder.length !== CARD.rows
      || m.rowOrder.join(',') !== CARD.rowOrder.join(',')) {
      errors.push(`rowOrder 必须是 ${CARD.rowOrder.join(',')}`);
    }
  }

  // 允许携带额外信息（生成方声明），但不作为校验依据
  const extra = {};
  for (const k of Object.keys(m)) if (!MANIFEST_FIELDS.includes(k)) extra[k] = m[k];
  return { ok: errors.length === 0, errors, manifest: m, extra };
}

/**
 * 校验 card.png：真实解码，检查尺寸与四角透明。
 * @returns {{ok:boolean, errors:string[], digest?:string, width?:number, height?:number}}
 */
function validateCardPng(buf) {
  const errors = [];
  let img;
  try {
    img = decodePng(buf);
  } catch (e) {
    return { ok: false, errors: [`card.png 解码失败：${e.message}`] };
  }

  const expect = CARD.frame * CARD.cols;
  const expectH = CARD.frame * CARD.rows;
  if (img.width !== expect || img.height !== expectH) {
    errors.push(`card.png 必须是 ${expect}×${expectH}，实际 ${img.width}×${img.height}`);
  }

  // 四角必须完全透明：否则会把背景色一起画出来
  const corners = [[0, 0], [img.width - 1, 0], [0, img.height - 1], [img.width - 1, img.height - 1]];
  for (const [x, y] of corners) {
    const a = alphaAt(img, x, y);
    if (a !== 0) {
      errors.push(`四角必须透明：(${x},${y}) 的 alpha=${a}`);
    }
  }

  // 每一帧左下角也应是透明空地（避免帧间粘连）
  // 尺寸已经不符时跳过——否则会按 4 行去读一张 3 行的图，报出误导性的"第 4 行"错误
  if (img.width === expect && img.height === expectH) {
    for (let r = 0; r < CARD.rows; r++) {
      let bad = false;
      for (let c = 0; c < CARD.cols; c++) {
        const x = c * CARD.frame;
        const y = r * CARD.frame + CARD.frame - 1;
        if (alphaAt(img, x, y) !== 0) {
          errors.push(`第 ${r + 1} 行第 ${c + 1} 帧左下角不透明，可能帧与帧粘连`);
          bad = true;
          break;
        }
      }
      if (bad) break;
    }
  }

  const digest = crypto.createHash('sha256').update(buf).digest('hex');
  return {
    ok: errors.length === 0,
    errors,
    digest,
    width: img.width,
    height: img.height,
  };
}

function validateBundle(pngBuf, manifestInput) {
  const m = validateManifest(manifestInput);
  const p = validateCardPng(pngBuf);
  const errors = [...m.errors, ...p.errors];
  return {
    ok: errors.length === 0,
    errors,
    digest: p.digest,
    manifest: m.manifest,
    size: p.ok ? { width: p.width, height: p.height } : null,
    directions: DIRECTIONS.slice(),
  };
}

module.exports = { validateManifest, validateCardPng, validateBundle, MANIFEST_FIELDS };
