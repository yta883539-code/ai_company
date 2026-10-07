// web-form-mockup/*.html の CSS-only(JS不使用)動的表示の実ブラウザ回帰チェック。
// フェーズ77でPlaywrightによる一度限りの手動検証により、要素の入れ子構造が原因でCSSの
// 出し分けが実際には機能していなかった不具合(daily.html)が4フェーズ気づかれずに残っていた
// ことが判明したため、以後の定例更新でも再現できるスクリプトとして切り出した。
// 実行: node prototype/browser_mockup_checks.js
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const MOCKUP_DIR = path.join(__dirname, '..', 'web-form-mockup');
// このエージェント実行環境ではPLAYWRIGHT_BROWSERS_PATHにプリインストール済みのchromiumを
// 使う(executablePathを明示)。CI(GitHub Actions)等、そのパスが存在しない環境では
// `npx playwright install --with-deps chromium`でインストールした既定のブラウザを使う。
const SANDBOX_CHROMIUM = '/opt/pw-browsers/chromium';
const LAUNCH_OPTIONS = fs.existsSync(SANDBOX_CHROMIUM) ? { executablePath: SANDBOX_CHROMIUM } : {};
let failures = 0;

function check(label, condition) {
  const mark = condition ? 'OK' : 'FAIL';
  if (!condition) failures += 1;
  console.log(`[${mark}] ${label}`);
}

async function checkDaily(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'daily.html'));

  check('daily: 初期表示は異常なしチェックリストのみ表示', await page.locator('.checklist-ok').isVisible() && !(await page.locator('.checklist-ng').isVisible()));

  // 車両番号ボタン・異常なし/異常あり・各項目チェックボックスはいずれもCSSで
  // 視覚的に隠した<input>をlabelクリックで操作する実装のため、labelをクリックする
  // (inputを直接.check()すると「element is not visible」でタイムアウトする)。
  await page.locator('label[for="mode-ng"]').click();
  check('daily: 異常ありを選ぶとチェックリストが切り替わる', !(await page.locator('.checklist-ok').isVisible()) && await page.locator('.checklist-ng').isVisible());

  const firstBlock = page.locator('.item-block').first();
  const firstNote = firstBlock.locator('.item-note');
  const firstWarn = firstBlock.locator('.item-note-warn');
  check('daily: 項目未チェックの間は自由記述欄が非表示', !(await firstNote.isVisible()));

  await firstBlock.locator('label.item-check').click();
  check('daily: 項目チェックで自由記述欄が表示される', await firstNote.isVisible());
  check('daily: 自由記述欄が空のままだと警告が表示される', await firstWarn.isVisible());

  await firstNote.fill('ブレーキの効きがやや甘い');
  check('daily: 自由記述欄に入力すると警告が消える', !(await firstWarn.isVisible()));

  await page.locator('label[for="vehicle-2"]').click();
  check('daily: 車両番号ボタンの選択状態が切り替わる', await page.locator('#vehicle-2').isChecked());
}

async function checkAnnual(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'annual.html'));

  const input = page.locator('input.text-input');
  const warn = page.locator('.field-warn');
  check('annual: 検査業者名欄が未入力の間は警告が表示される', await warn.isVisible());

  await input.fill('○○検査サービス株式会社');
  check('annual: 検査業者名欄に入力すると警告が消える', !(await warn.isVisible()));
}

async function checkIndex(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'index.html'));
  check('index: daily/monthly/annualへのリンクが存在する', (await page.locator('a[href="daily.html"]').count()) > 0 && (await page.locator('a[href="monthly.html"]').count()) > 0 && (await page.locator('a[href="annual.html"]').count()) > 0);
  check('index: settingsへのリンクが存在する', (await page.locator('a[href="settings.html"]').count()) > 0);
}

// フェーズ101: settings.html(access-token-reissue-design.md 2節・6節のモックアップ化)の
// CSSのみの確認メッセージ切替(daily.htmlの異常あり/なし切替と同じchecked+一般兄弟結合子の手法)
// を検証する。
async function checkSettings(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'settings.html'));

  check('settings: ページが例外なく読み込める', (await page.title()).length > 0);
  check('settings: 前回のアクセス日時が表示されている', (await page.locator('.last-accessed .value').innerText()).length > 0);

  const confirm = page.locator('.reissue-confirm');
  check('settings: 初期表示では再発行の確認メッセージが非表示', !(await confirm.isVisible()));

  await page.locator('label.reissue-btn').click();
  check('settings: 再発行ボタンを押すと確認メッセージが表示される', await confirm.isVisible());
}

// フェーズ82でdaily.html同型のチェックリスト(:has()による出し分け)をmonthly.htmlにも
// 移植したため、daily用のcheckDaily()と同じ観点をmonthly.htmlにも適用する。
async function checkMonthly(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'monthly.html'));
  check('monthly: ページが例外なく読み込める', (await page.title()).length > 0);

  check('monthly: 初期表示は異常なしチェックリストのみ表示', await page.locator('.checklist-ok').isVisible() && !(await page.locator('.checklist-ng').isVisible()));

  await page.locator('label[for="mode-ng"]').click();
  check('monthly: 異常ありを選ぶとチェックリストが切り替わる', !(await page.locator('.checklist-ok').isVisible()) && await page.locator('.checklist-ng').isVisible());

  const firstBlock = page.locator('.item-block').first();
  const firstNote = firstBlock.locator('.item-note');
  const firstWarn = firstBlock.locator('.item-note-warn');
  check('monthly: 項目未チェックの間は自由記述欄が非表示', !(await firstNote.isVisible()));

  await firstBlock.locator('label.item-check').click();
  check('monthly: 項目チェックで自由記述欄が表示される', await firstNote.isVisible());
  check('monthly: 自由記述欄が空のままだと警告が表示される', await firstWarn.isVisible());

  await firstNote.fill('ブレーキの効きがやや甘い');
  check('monthly: 自由記述欄に入力すると警告が消える', !(await firstWarn.isVisible()));
}

(async () => {
  const browser = await chromium.launch(LAUNCH_OPTIONS);
  const page = await browser.newPage();
  try {
    await checkDaily(page);
    await checkAnnual(page);
    await checkIndex(page);
    await checkMonthly(page);
    await checkSettings(page);
  } finally {
    await browser.close();
  }

  console.log(failures === 0 ? '\nAll browser mockup checks passed.' : `\n${failures} check(s) failed.`);
  process.exit(failures === 0 ? 0 : 1);
})();
