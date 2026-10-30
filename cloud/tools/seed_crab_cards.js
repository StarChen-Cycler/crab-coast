'use strict';
/* 把测试环境里所有动物的动作卡统一换成螃蟹（一键造演示数据）。
 *
 * 说明：token 只以哈希入库，拿不到别人的明文 token，所以无法走 /animals/:id/card 上传。
 * 这里直接写卡片文件 + 更新 animals 表，然后**重启服务**让内存里的 World 重新加载
 * （页面侧按 id 拉 /cards/<id>.png，文件一落地视觉就变了；但 state 里的 card 摘要要等重启）。
 *
 * 用法：
 *   node tools/seed_crab_cards.js                 # 只看会改哪些（dry-run）
 *   node tools/seed_crab_cards.js --apply         # 真的写入
 *   node tools/seed_crab_cards.js --apply --data C:\...\cloud\data
 *
 * 只动 DATA_DIR 下的卡片与 animals 表，不碰世界位置、token、名字。
 */

const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { validateBundle } = require('../shared/card');
const C = require('../shared/const');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const APPLY = process.argv.includes('--apply');
const DATA_DIR = path.resolve(arg('--data', path.join(__dirname, '..', 'data')));
const SHEET = path.resolve(arg('--sheet', path.join(__dirname, '..', '..', 'assets', 'crab_sheet.png')));
const CARD_DIR = path.join(DATA_DIR, 'cards');
const DB_PATH = path.join(DATA_DIR, 'world.db');

const MANIFEST = {
  frame: C.CARD.frame, cols: C.CARD.cols, rows: C.CARD.rows,
  rowOrder: C.CARD.rowOrder, footLine: C.CARD.footLine, fps: C.CARD.fps,
};

function main() {
  if (!fs.existsSync(SHEET)) { console.error('找不到螃蟹卡：' + SHEET); return 1; }
  if (!fs.existsSync(DB_PATH)) { console.error('找不到数据库：' + DB_PATH); return 1; }

  const buf = fs.readFileSync(SHEET);
  const v = validateBundle(buf, MANIFEST);
  if (!v.ok) {
    console.error('螃蟹卡不满足多人版规格，拒绝写入：');
    for (const e of v.errors) console.error('  - ' + e);
    return 1;
  }
  console.log(`螃蟹卡 ${SHEET}`);
  console.log(`  通过校验：${v.size.width}×${v.size.height} digest ${v.digest.slice(0, 12)}… (${buf.length} 字节)`);

  const db = new DatabaseSync(DB_PATH);
  const rows = db.prepare('SELECT id, name, card_digest FROM animals ORDER BY id').all();
  if (!rows.length) { console.log('库里还没有动物。'); db.close(); return 0; }

  fs.mkdirSync(CARD_DIR, { recursive: true });
  let changed = 0, same = 0;
  for (const r of rows) {
    const file = path.join(CARD_DIR, `${r.id}.png`);
    if (r.card_digest === v.digest && fs.existsSync(file) && fs.statSync(file).size === buf.length) {
      same++;
      console.log(`  = ${r.id} ${r.name} 已经是螃蟹`);
      continue;
    }
    const before = r.card_digest ? r.card_digest.slice(0, 12) + '…' : '(无卡)';
    if (APPLY) {
      fs.writeFileSync(file, buf);
      db.prepare('UPDATE animals SET card_path = ?, card_digest = ?, card_w = ?, card_h = ? WHERE id = ?')
        .run(file, v.digest, v.size.width, v.size.height, r.id);
    }
    changed++;
    console.log(`  ${APPLY ? '+' : '·'} ${r.id} ${r.name}  ${before} → ${v.digest.slice(0, 12)}…`);
  }
  db.close();

  console.log(`\n${APPLY ? '已写入' : '待写入'} ${changed} 只，已是一致 ${same} 只（共 ${rows.length} 只）。`);
  if (!APPLY && changed) console.log('这是 dry-run，加 --apply 才会真的改。');
  if (APPLY && changed) console.log('⚠ 服务进程里的 World 还持有旧卡信息：重启服务后才生效（页面图片已即时生效）。');
  return 0;
}

process.exitCode = main();
