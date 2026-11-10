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

  // フェーズ228: 「車両を追加」自由記述枠(web-form-ui-design.md 5節・フェーズ227)の検証。
  const vehicleAddInput = page.locator('.vehicle-add-input');
  check('daily: 「車両を追加」未選択の間は自由記述欄が非表示', !(await vehicleAddInput.isVisible()));
  await page.locator('label[for="vehicle-new"]').click();
  check('daily: 「車両を追加」を選ぶと自由記述欄が表示される', await vehicleAddInput.isVisible());
  await vehicleAddInput.fill('倉庫2F用');
  check('daily: 自由記述欄に車両の表記を入力できる', (await vehicleAddInput.inputValue()) === '倉庫2F用');
}

async function checkDailyEmpty(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'daily-empty.html'));

  check('daily-empty: ページが例外なく読み込める', (await page.title()).length > 0);
  check('daily-empty: 車両番号ボタンが存在しない(保有0台)', (await page.locator('.vehicle-buttons').count()) === 0);
  check('daily-empty: 車両の自由記述欄が常時表示されている', await page.locator('.vehicle-add-input').isVisible());

  const input = page.locator('.vehicle-add-input');
  await input.fill('1号車');
  check('daily-empty: 自由記述欄に車両の表記を入力できる', (await input.inputValue()) === '1号車');
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
// を検証する。フェーズ102でメールアドレス変更欄(任意入力)の表示・入力可否も追加検証する。
async function checkSettings(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'settings.html'));

  check('settings: ページが例外なく読み込める', (await page.title()).length > 0);
  check('settings: 前回のアクセス日時が表示されている', (await page.locator('.last-accessed .value').innerText()).length > 0);

  const confirm = page.locator('.reissue-confirm');
  check('settings: 初期表示では再発行の確認メッセージが非表示', !(await confirm.isVisible()));

  await page.locator('label.reissue-btn').click();
  check('settings: 再発行ボタンを押すと確認メッセージが表示される', await confirm.isVisible());

  // フェーズ102: 確認メッセージ内のメールアドレス変更欄(任意)の検証。
  const newEmailInput = page.locator('#new-email');
  check('settings: 確認メッセージ内に新しいメールアドレス欄が表示される', await newEmailInput.isVisible());
  await newEmailInput.fill('new-address@example.com');
  check('settings: 新しいメールアドレス欄に入力できる', (await newEmailInput.inputValue()) === 'new-address@example.com');
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

// フェーズ139: フェーズ138で新設したplan-selection.html(プラン選択UI)の
// 3プラン表示・申し込みボタンのdisabled状態・index.htmlからの遷移リンクを検証する。
// 本ページはJS不使用の静的HTML(CSSによる出し分けなし)のため、daily.html等のような
// 状態切り替えの検証対象はなく、表示内容とボタンの無効化状態のみを確認する。
async function checkPlanSelection(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'plan-selection.html'));

  check('plan-selection: ページが例外なく読み込める', (await page.title()).length > 0);

  const cards = page.locator('.plan-card');
  check('plan-selection: プランカードが3件表示される', (await cards.count()) === 3);

  check('plan-selection: ライトプランの料金が表示される', (await cards.nth(0).innerText()).includes('980円'));
  check('plan-selection: スタンダードプランの料金が表示される', (await cards.nth(1).innerText()).includes('2,480円'));
  check('plan-selection: 複数台プランの料金が表示される', (await cards.nth(2).innerText()).includes('4,980円'));

  const buttons = page.locator('button.apply-btn');
  check('plan-selection: 申し込むボタンが3件とも無効化されている(バックエンド未接続)', (await buttons.count()) === 3 && (await Promise.all([0, 1, 2].map(async i => buttons.nth(i).isDisabled()))).every(Boolean));
}

async function checkIndexPlanSelectionLink(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'index.html'));
  check('index: plan-selectionへのリンクが存在する(フェーズ138)', (await page.locator('a[href="plan-selection.html"]').count()) > 0);
}

// フェーズ205: annual-result.html(annual区分の送信完了・結果表示画面)の新規追加に伴う
// 静的内容の確認。plan-selection.htmlと同様にJS不使用の静的HTML(CSSによる出し分けなし)
// のため、annual区分専用の法定保存義務注意カード(labor-notice-card)・記録本文・
// 戻るリンクが表示されることのみを確認する。
async function checkAnnualResult(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'annual-result.html'));

  check('annual-result: ページが例外なく読み込める', (await page.title()).length > 0);

  const noticeCard = page.locator('.labor-notice-card');
  check('annual-result: annual区分専用の法定保存義務注意カードが表示される', await noticeCard.isVisible());
  check('annual-result: 注意カードに3年間保存の文言が含まれる', (await noticeCard.innerText()).includes('3年間保存'));

  check('annual-result: 記録本文(整形済みテキスト)が表示される', await page.locator('.body-text').isVisible());

  const copyBtn = page.locator('button.copy-btn');
  check('annual-result: コピーボタンが無効化されている(バックエンド未接続)', await copyBtn.isDisabled());

  check('annual-result: annual.htmlへの戻るリンクが存在する', (await page.locator('a[href="annual.html"]').count()) > 0);
}

// フェーズ206: daily-result.html(daily区分の送信完了・結果表示画面)の新規追加に伴う
// 静的内容の確認。annual区分と異なり法定保存義務注意カード(labor-notice-card)は
// 表示されないこと、reminder_notice(次回のお知らせ)セクション自体が存在しないこと
// (mvp-flow-draft.md「type=dailyのときreminder_noticeは常にnull」に対応)を確認する。
async function checkDailyResult(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'daily-result.html'));

  check('daily-result: ページが例外なく読み込める', (await page.title()).length > 0);

  check('daily-result: annual区分専用の法定保存義務注意カードが表示されない', (await page.locator('.labor-notice-card').count()) === 0);
  check('daily-result: 次回のお知らせセクションが存在しない(dailyはreminder_notice常にnull)', (await page.locator('.reminder-text').count()) === 0);

  check('daily-result: 記録本文(整形済みテキスト)が表示される', await page.locator('.body-text').isVisible());

  const copyBtn = page.locator('button.copy-btn');
  check('daily-result: コピーボタンが無効化されている(バックエンド未接続)', await copyBtn.isDisabled());

  check('daily-result: daily.htmlへの戻るリンクが存在する', (await page.locator('a[href="daily.html"]').count()) > 0);
}

// フェーズ206: monthly-result.html(monthly区分の送信完了・結果表示画面)の新規追加に伴う
// 静的内容の確認。daily区分と異なりreminder_noticeが非nullの場合の表示例として
// 次回のお知らせセクションを持つが、annual区分専用の法定保存義務注意カードは
// 表示されないことを確認する。
async function checkMonthlyResult(page) {
  await page.goto('file://' + path.join(MOCKUP_DIR, 'monthly-result.html'));

  check('monthly-result: ページが例外なく読み込める', (await page.title()).length > 0);

  check('monthly-result: annual区分専用の法定保存義務注意カードが表示されない', (await page.locator('.labor-notice-card').count()) === 0);

  const reminder = page.locator('.reminder-text');
  check('monthly-result: 次回のお知らせ(reminder_notice非nullの表示例)が表示される', await reminder.isVisible());
  check('monthly-result: 記録本文(整形済みテキスト)が表示される', await page.locator('.body-text').isVisible());

  const copyBtn = page.locator('button.copy-btn');
  check('monthly-result: コピーボタンが無効化されている(バックエンド未接続)', await copyBtn.isDisabled());

  check('monthly-result: monthly.htmlへの戻るリンクが存在する', (await page.locator('a[href="monthly.html"]').count()) > 0);
}

(async () => {
  const browser = await chromium.launch(LAUNCH_OPTIONS);
  const page = await browser.newPage();
  try {
    await checkDaily(page);
    await checkDailyEmpty(page);
    await checkAnnual(page);
    await checkIndex(page);
    await checkMonthly(page);
    await checkSettings(page);
    await checkPlanSelection(page);
    await checkIndexPlanSelectionLink(page);
    await checkAnnualResult(page);
    await checkDailyResult(page);
    await checkMonthlyResult(page);
  } finally {
    await browser.close();
  }

  console.log(failures === 0 ? '\nAll browser mockup checks passed.' : `\n${failures} check(s) failed.`);
  process.exit(failures === 0 ? 0 : 1);
})();
