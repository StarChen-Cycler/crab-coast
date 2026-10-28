'use strict';
/* 极简 PNG 解码：只支持「8 bit / 真彩色+alpha (color type 6) / 非隔行」。
   Pillow 与 canvas 导出的 PNG 都落在这个范围内，够用来在服务端做真实校验
   （尺寸 + 四角透明），不需要引入 sharp / pngjs 之类的依赖。
   其它格式会抛错并说明原因，而不是静默放过。 */

const zlib = require('node:zlib');

const SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

/** @returns {{width:number,height:number,data:Buffer}} RGBA，行优先 */
function decodePng(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < 8 || !buf.subarray(0, 8).equals(SIG)) {
    throw new Error('不是 PNG 文件');
  }

  let pos = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let interlace = 0;
  const idat = [];

  while (pos + 8 <= buf.length) {
    const len = buf.readUInt32BE(pos);
    const type = buf.toString('ascii', pos + 4, pos + 8);
    const dataStart = pos + 8;
    const dataEnd = dataStart + len;
    if (dataEnd + 4 > buf.length) throw new Error('PNG 数据被截断');

    if (type === 'IHDR') {
      width = buf.readUInt32BE(dataStart);
      height = buf.readUInt32BE(dataStart + 4);
      bitDepth = buf[dataStart + 8];
      colorType = buf[dataStart + 9];
      interlace = buf[dataStart + 12];
    } else if (type === 'IDAT') {
      idat.push(buf.subarray(dataStart, dataEnd));
    } else if (type === 'IEND') {
      break;
    }
    pos = dataEnd + 4; // 跳过 CRC
  }

  if (!width || !height) throw new Error('PNG 缺少 IHDR');
  if (bitDepth !== 8) throw new Error(`只支持 8 bit PNG（当前 ${bitDepth}）`);
  if (colorType !== 6) throw new Error(`只支持 RGBA PNG（color type 6，当前 ${colorType}）`);
  if (interlace !== 0) throw new Error('不支持隔行 PNG');
  if (!idat.length) throw new Error('PNG 没有 IDAT 数据');

  const raw = zlib.inflateSync(Buffer.concat(idat));
  const bpp = 4;
  const stride = width * bpp;
  if (raw.length < (stride + 1) * height) {
    throw new Error('PNG 像素数据长度不足');
  }

  const out = Buffer.alloc(stride * height);
  let prevRow = Buffer.alloc(stride);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const line = raw.subarray(y * (stride + 1) + 1, y * (stride + 1) + 1 + stride);
    const row = out.subarray(y * stride, (y + 1) * stride);
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? row[i - bpp] : 0;
      const b = prevRow[i];
      const c = i >= bpp ? prevRow[i - bpp] : 0;
      const x = line[i];
      let v;
      switch (filter) {
        case 0: v = x; break;
        case 1: v = x + a; break;
        case 2: v = x + b; break;
        case 3: v = x + ((a + b) >> 1); break;
        case 4: v = x + paeth(a, b, c); break;
        default: throw new Error(`未知的 PNG 行过滤器 ${filter}`);
      }
      row[i] = v & 0xff;
    }
    prevRow = row;
  }

  return { width, height, data: out };
}

function alphaAt(img, x, y) {
  // 越界视为"不存在"，交给调用方当尺寸不符处理，避免读到 Buffer 之外
  if (x < 0 || y < 0 || x >= img.width || y >= img.height) return null;
  return img.data[(y * img.width + x) * 4 + 3];
}

module.exports = { decodePng, alphaAt, PNG_SIG: SIG };
