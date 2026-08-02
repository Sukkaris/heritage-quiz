/* 世界遺産クイズ — 出題ロジックと画面制御
 *
 * 事実（遺産名・国・登録年・区分）はすべて data.js のマスタから引く。
 * このファイルには遺産に関する事実を一切書かない。
 */
'use strict';

// ============================================================
// 定数
// ============================================================

const SET_SIZE = 10;              // 1セットの問題数
const STORAGE_KEY = 'heritageQuiz.stats.v1';
const BACKUP_KEY = 'heritageQuiz.backup.v1';
const MANUAL_RATIO = 0.3;         // 1セットに混ぜる手書き問題の上限割合（§9）

// 学習記録の書き出しを促す条件。iOSは一定期間使わないとブラウザの保存領域を
// 消すことがあるため、記録が消えても取り返せるように書き出しを勧める。
const BACKUP = {
  warnAfterDays: 14,        // 前回の書き出しからこの日数を超えたら目立たせる
  remindAfterAnswers: 100   // 前回の書き出し後にこの問数を解いたら結果画面で促す
};

// 登録年代フィルタ（§4.1）
const ERAS = [
  { key: '80s',  label: '1970-80年代', from: 0,    to: 1989 },
  { key: '90s',  label: '1990年代',    from: 1990, to: 1999 },
  { key: '00s',  label: '2000年代',    from: 2000, to: 2009 },
  { key: '10s',  label: '2010年代',    from: 2010, to: 2019 },
  { key: '20s',  label: '2020年代',    from: 2020, to: 2099 }
];

const CATEGORIES = ['文化', '自然', '複合'];
const DIFFICULTIES = ['易', '中', '難'];

// 登録基準の系統（i〜vi = 文化、vii〜x = 自然）
const CULTURAL_CRITERIA = new Set(['i', 'ii', 'iii', 'iv', 'v', 'vi']);

// 誤答をどれだけ「近く」から引くか（§6.4 難易度調整のレバー）
// 値 = 4択のうち、正解と紛らわしい側から引く誤答の数。
//   所在国   … 同一地域の国
//   遺産名   … 同一地域にある別の遺産
//   登録基準 … 正解と同じ系統（文化どうし／自然どうし）の基準
const DISTRACTOR_NEARNESS = { '易': 0, '中': 1, '難': 3 };

// ============================================================
// マスタの前処理
// ============================================================

function difficultyOf(sitelinks) {
  if (sitelinks >= DIFFICULTY.easyMin) return '易';
  if (sitelinks <= DIFFICULTY.hardMax) return '難';
  return '中';
}

function eraOf(year) {
  for (const e of ERAS) if (year >= e.from && year <= e.to) return e.key;
  return null;
}

const SITES = HERITAGE_DATA.map((s) => Object.assign({}, s, {
  difficulty: difficultyOf(s.sitelinks),
  era: s.year ? eraOf(s.year) : null
}));

const SITE_BY_QID = {};
SITES.forEach((s) => { SITE_BY_QID[s.qid] = s; });

// 出題対象: 日本語ラベル・登録年・区分・所在国がそろっているもの（§3.4）
const ELIGIBLE = SITES.filter(
  (s) => s.hasJaLabel && s.year && s.category && s.countries.length > 0
);

// 誤答用の国プール: 世界遺産を持ち、日本語名と地域が判明している国
const COUNTRY_POOL = Object.keys(COUNTRIES).filter(
  (c) => COUNTRIES[c] && COUNTRIES[c].ja && COUNTRIES[c].region
);

// 同じ日本語名の遺産が複数ある（例: イグアス国立公園＝アルゼンチンとブラジル）。
// 選択肢は名前しか出ないので、名前で見て正解になりうるものは誤答に使えない。
const SITES_BY_NAME = {};
ELIGIBLE.forEach((s) => {
  (SITES_BY_NAME[s.ja] = SITES_BY_NAME[s.ja] || []).push(s);
});

function nameExistsInCountry(name, country) {
  return (SITES_BY_NAME[name] || []).some((s) => s.countries.indexOf(country) >= 0);
}

const MANUAL = (typeof MANUAL_QUESTIONS !== 'undefined' && Array.isArray(MANUAL_QUESTIONS))
  ? MANUAL_QUESTIONS : [];

// ============================================================
// 小道具
// ============================================================

const $ = (id) => document.getElementById(id);
const rand = (n) => Math.floor(Math.random() * n);
const pick = (arr) => arr[rand(arr.length)];

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = rand(i + 1);
    const t = a[i]; a[i] = a[j]; a[j] = t;
  }
  return a;
}

function sampleN(arr, n) {
  return shuffle(arr).slice(0, n);
}

const countryName = (qid) => (COUNTRIES[qid] && COUNTRIES[qid].ja) || qid;

function countryList(site) {
  return site.countries.map(countryName).join('・');
}

function siteSummary(site) {
  const parts = [countryList(site)];
  if (site.year) parts.push(site.year + '年登録');
  if (site.category) parts.push(site.category + '遺産');
  if (site.criteria && site.criteria.length) {
    parts.push('基準' + site.criteria.map((c) => '(' + c + ')').join(''));
  }
  return parts.join(' / ');
}

// 登録基準を選択肢として表示する文字列
function criterionLabel(c) {
  return '(' + c + ') ' + (CRITERIA_TEXT[c] || '');
}

// ============================================================
// 学習記録（localStorage・§7.1）
// ============================================================

let stats = loadStats();

function loadStats() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    return {};
  }
}

function saveStats() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stats));
  } catch (e) {
    /* プライベートモード等で保存できない場合は記録なしで続行する */
  }
}

function recordAnswer(qid, isCorrect) {
  if (!qid) return;
  const rec = stats[qid] || { correct: 0, wrong: 0, lastAnswered: 0 };
  if (isCorrect) rec.correct++; else rec.wrong++;
  rec.lastAnswered = Date.now();
  stats[qid] = rec;
  saveStats();
}

function totalAnswers() {
  let n = 0;
  for (const k of Object.keys(stats)) n += stats[k].correct + stats[k].wrong;
  return n;
}

// 書き出しの記録（いつ・何問時点で書き出したか）
function loadBackupInfo() {
  try {
    return JSON.parse(localStorage.getItem(BACKUP_KEY)) || {};
  } catch (e) {
    return {};
  }
}

function markExported() {
  try {
    localStorage.setItem(BACKUP_KEY, JSON.stringify({
      lastExport: Date.now(),
      answersAtExport: totalAnswers()
    }));
  } catch (e) {
    /* 保存できなくても書き出し自体は成功している */
  }
}

// 弱点モードの重み（§7.2）
function weightOf(qid) {
  const r = stats[qid];
  if (!r) return 1;
  return Math.max(1, 1 + r.wrong * 2 - r.correct);
}

// ============================================================
// 状態
// ============================================================

const state = {
  mode: 'normal',
  filters: { region: new Set(), category: new Set(), era: new Set(), difficulty: new Set() },
  quiz: null
};

function filteredSites() {
  const f = state.filters;
  return ELIGIBLE.filter((s) => {
    if (f.region.size && !s.regions.some((r) => f.region.has(r))) return false;
    if (f.category.size && !f.category.has(s.category)) return false;
    if (f.era.size && !f.era.has(s.era)) return false;
    if (f.difficulty.size && !f.difficulty.has(s.difficulty)) return false;
    return true;
  });
}

function filteredManual() {
  const f = state.filters;
  return MANUAL.filter((q) => {
    if (f.difficulty.size && q.difficulty && !f.difficulty.has(q.difficulty)) return false;
    const s = q.relatedQid ? SITE_BY_QID[q.relatedQid] : null;
    if (!s) return !(f.region.size || f.category.size || f.era.size);
    if (f.region.size && !s.regions.some((r) => f.region.has(r))) return false;
    if (f.category.size && !f.category.has(s.category)) return false;
    if (f.era.size && !f.era.has(s.era)) return false;
    return true;
  });
}

// ============================================================
// 出題テンプレート（第一版は3種・§6.2）
// ============================================================

// 1) 遺産名 → 所在国
// 複数国にまたがる遺産は「複数正解」になるため除外する（§6.4）
function makeCountryQuestion(site) {
  if (site.countries.length !== 1) return null;
  const correct = site.countries[0];
  if (!COUNTRIES[correct] || !COUNTRIES[correct].ja) return null;

  const region = COUNTRIES[correct].region;
  const near = COUNTRY_POOL.filter((c) => c !== correct && COUNTRIES[c].region === region);
  const far = COUNTRY_POOL.filter((c) => c !== correct && COUNTRIES[c].region !== region);

  const wantNear = Math.min(DISTRACTOR_NEARNESS[site.difficulty], near.length);
  let wrong = sampleN(near, wantNear).concat(sampleN(far, 3 - wantNear));
  if (wrong.length < 3) {                       // 地域が偏っている場合の穴埋め
    const rest = COUNTRY_POOL.filter((c) => c !== correct && wrong.indexOf(c) < 0);
    wrong = wrong.concat(sampleN(rest, 3 - wrong.length));
  }

  return {
    tag: '所在国',
    text: '「' + site.ja + '」があるのはどの国ですか？',
    choices: shuffle([correct].concat(wrong)).map(countryName),
    answer: countryName(correct),
    site: site
  };
}

// 2) 遺産名 → 区分（この設問のみ3択・§6.2）
function makeCategoryQuestion(site) {
  if (!site.category) return null;
  return {
    tag: '区分',
    text: '「' + site.ja + '」は文化遺産・自然遺産・複合遺産のどれですか？',
    choices: shuffle(CATEGORIES).map((c) => c + '遺産'),
    answer: site.category + '遺産',
    site: site
  };
}

// 3) 所在国 → 遺産名（テンプレート4・§6.3）
// 誤答には「その国に無い遺産」だけを使う。複数国にまたがる遺産も、
// 問う国を含んでいなければ誤答として使ってよい。
function makeSiteFromCountryQuestion(site) {
  const country = pick(site.countries.filter((c) => COUNTRIES[c] && COUNTRIES[c].ja));
  if (!country) return null;
  const region = COUNTRIES[country].region;

  const usable = (s) => s.qid !== site.qid && s.countries.indexOf(country) < 0
    && !nameExistsInCountry(s.ja, country);
  const near = ELIGIBLE.filter((s) => usable(s) && s.regions.indexOf(region) >= 0);
  const far = ELIGIBLE.filter((s) => usable(s) && s.regions.indexOf(region) < 0);

  const wantNear = Math.min(DISTRACTOR_NEARNESS[site.difficulty], near.length);
  let wrong = sampleN(near, wantNear).concat(sampleN(far, 3 - wantNear));
  if (wrong.length < 3) return null;

  return {
    tag: '遺産名',
    text: '次のうち、' + countryName(country) + 'にある世界遺産はどれですか？',
    choices: shuffle([site].concat(wrong)).map((s) => s.ja),
    answer: site.ja,
    site: site
  };
}

// 4) 遺産名 → 登録基準（テンプレート5・§6.3）
// 複数基準を持つ遺産は「正解の基準を1つ選ばせ、誤答にはその遺産が
// 持たない基準だけを使う」ことで、複数正解にならないようにする。
function makeCriteriaQuestion(site) {
  if (!site.criteria || !site.criteria.length) return null;
  const correct = pick(site.criteria);
  const others = CRITERIA_ORDER.filter((c) => site.criteria.indexOf(c) < 0);
  if (others.length < 3) return null;

  // 難: 正解と同じ系統（文化どうし/自然どうし）の紛らわしい基準を誤答にする
  const sameType = others.filter((c) => CULTURAL_CRITERIA.has(c) === CULTURAL_CRITERIA.has(correct));
  const otherType = others.filter((c) => CULTURAL_CRITERIA.has(c) !== CULTURAL_CRITERIA.has(correct));

  const wantNear = Math.min(DISTRACTOR_NEARNESS[site.difficulty], sameType.length);
  let wrong = sampleN(sameType, wantNear).concat(sampleN(otherType, 3 - wantNear));
  if (wrong.length < 3) {
    const rest = others.filter((c) => wrong.indexOf(c) < 0);
    wrong = wrong.concat(sampleN(rest, 3 - wrong.length));
  }

  return {
    tag: '登録基準',
    text: '「' + site.ja + '」の登録基準に含まれるものはどれですか？',
    choices: shuffle([correct].concat(wrong)).map(criterionLabel),
    answer: criterionLabel(correct),
    site: site,
    longChoices: true
  };
}

const TEMPLATES = [
  makeCountryQuestion,
  makeCategoryQuestion,
  makeSiteFromCountryQuestion,
  makeCriteriaQuestion
];

function makeQuestion(site) {
  const order = shuffle(TEMPLATES);
  for (const t of order) {
    const q = t(site);
    if (q && new Set(q.choices).size === q.choices.length) return q;  // 選択肢の重複禁止
  }
  return null;
}

// 手書き問題（§9）をアプリ内部の形式に変換
function manualToQuestion(m) {
  const site = m.relatedQid ? SITE_BY_QID[m.relatedQid] : null;
  const answer = m.choices[m.answerIndex];
  return {
    tag: '解説問題',
    text: m.question,
    choices: shuffle(m.choices),
    answer: answer,
    explanation: m.explanation,
    site: site,
    qid: m.relatedQid || m.id
  };
}

// ============================================================
// セットの組み立て
// ============================================================

function weightedPick(pool) {
  let total = 0;
  for (const s of pool) total += weightOf(s.qid);
  let r = Math.random() * total;
  for (const s of pool) {
    r -= weightOf(s.qid);
    if (r <= 0) return s;
  }
  return pool[pool.length - 1];
}

function buildQuiz() {
  const pool = filteredSites();
  if (!pool.length) return null;

  const manualPool = filteredManual();
  const manualCount = Math.min(manualPool.length, Math.floor(SET_SIZE * MANUAL_RATIO));
  const templateCount = Math.min(SET_SIZE - manualCount, pool.length);

  const questions = [];
  const used = new Set();
  let guard = 0;
  while (questions.length < templateCount && guard++ < 500) {
    const remaining = pool.filter((s) => !used.has(s.qid));
    if (!remaining.length) break;
    const site = state.mode === 'weak' ? weightedPick(remaining) : pick(remaining);
    used.add(site.qid);
    const q = makeQuestion(site);
    if (q) { q.qid = site.qid; questions.push(q); }
  }

  sampleN(manualPool, manualCount).forEach((m) => questions.push(manualToQuestion(m)));

  return {
    questions: shuffle(questions),
    index: 0,
    correct: 0,
    wrong: []
  };
}

// ============================================================
// 画面制御
// ============================================================

function showScreen(name) {
  ['start', 'quiz', 'result'].forEach((n) => {
    $('screen-' + n).hidden = (n !== name);
  });
  window.scrollTo(0, 0);
}

// --- スタート画面 -------------------------------------------

function buildChips() {
  const defs = [
    ['filter-region', 'region', REGIONS.map((r) => [r, r])],
    ['filter-category', 'category', CATEGORIES.map((c) => [c, c + '遺産'])],
    ['filter-era', 'era', ERAS.map((e) => [e.key, e.label])],
    ['filter-difficulty', 'difficulty', DIFFICULTIES.map((d) => [d, d])]
  ];
  for (const [elId, key, opts] of defs) {
    const box = $(elId);
    box.innerHTML = '';
    for (const [value, label] of opts) {
      const b = document.createElement('button');
      b.className = 'chip';
      b.textContent = label;
      b.addEventListener('click', () => {
        const set = state.filters[key];
        if (set.has(value)) set.delete(value); else set.add(value);
        b.classList.toggle('is-on', set.has(value));
        updatePoolInfo();
      });
      box.appendChild(b);
    }
  }
  document.querySelectorAll('[data-clear]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.clear;
      state.filters[key].clear();
      document.querySelectorAll('#filter-' + key + ' .chip').forEach((c) => c.classList.remove('is-on'));
      updatePoolInfo();
    });
  });
}

function updatePoolInfo() {
  const n = filteredSites().length;
  const m = filteredManual().length;
  $('pool-info').textContent = '出題対象 ' + n + '件' + (m ? '（＋解説問題' + m + '問）' : '');
  $('btn-start').disabled = (n + m) === 0;
  $('btn-start').textContent = (n + m) === 0
    ? '条件に合う遺産がありません'
    : Math.min(SET_SIZE, n + m) + '問はじめる';
}

function updateStatsView() {
  const keys = Object.keys(stats);
  let c = 0, w = 0, weak = 0;
  for (const k of keys) {
    c += stats[k].correct;
    w += stats[k].wrong;
    if (stats[k].wrong > stats[k].correct) weak++;
  }
  $('stat-answered').textContent = c + w;
  $('stat-rate').textContent = (c + w) ? Math.round((c / (c + w)) * 100) + '%' : '–';
  $('stat-seen').textContent = keys.length;
  $('stat-weak').textContent = weak;
  updateBackupNotice(c + w);
}

// A. スタート画面に、前回の書き出しからの経過を出す
function updateBackupNotice(answered) {
  const el = $('backup-notice');
  if (!el) return;
  const info = loadBackupInfo();

  if (!answered) {                       // まだ記録が無ければ何も出さない
    el.hidden = true;
    return;
  }
  el.hidden = false;

  if (!info.lastExport) {
    el.textContent = '学習記録はこの端末にしか残りません。まだ一度も書き出していません。';
    el.classList.toggle('is-warn', answered >= BACKUP.remindAfterAnswers);
    return;
  }
  const days = Math.floor((Date.now() - info.lastExport) / 86400000);
  el.textContent = days === 0
    ? '学習記録は今日書き出し済みです。'
    : '前回の書き出しから' + days + '日たちました。';
  el.classList.toggle('is-warn', days >= BACKUP.warnAfterDays);
}

// --- 出題画面 -----------------------------------------------

function renderQuestion() {
  const quiz = state.quiz;
  const q = quiz.questions[quiz.index];

  $('progress-text').textContent = (quiz.index + 1) + ' / ' + quiz.questions.length;
  $('progress-fill').style.width = (quiz.index / quiz.questions.length * 100) + '%';
  $('q-tag').textContent = q.tag;
  $('q-text').textContent = q.text;
  $('feedback').hidden = true;

  const box = $('choices');
  box.innerHTML = '';
  box.classList.toggle('long', !!q.longChoices);   // 登録基準は条文が長い
  q.choices.forEach((choice) => {
    const b = document.createElement('button');
    b.className = 'choice';
    b.textContent = choice;
    b.addEventListener('click', () => answer(b, choice));
    box.appendChild(b);
  });
}

function answer(btn, choice) {
  const quiz = state.quiz;
  const q = quiz.questions[quiz.index];
  const ok = choice === q.answer;

  document.querySelectorAll('.choice').forEach((el) => {
    el.disabled = true;
    if (el.textContent === q.answer) el.classList.add('correct');
    else if (el === btn) el.classList.add('wrong');
    else el.classList.add('dim');
  });

  if (ok) quiz.correct++;
  else if (q.site) quiz.wrong.push(q.site);

  recordAnswer(q.qid, ok);

  $('verdict').textContent = ok ? '正解' : '不正解';
  $('verdict').className = 'verdict ' + (ok ? 'ok' : 'ng');
  const lines = [];
  if (!ok) lines.push('正解: ' + q.answer);
  if (q.site) lines.push(q.site.ja + '（' + siteSummary(q.site) + '）');
  if (q.explanation) lines.push(q.explanation);
  $('explain').textContent = lines.join('　');

  $('btn-next').textContent = (quiz.index + 1 >= quiz.questions.length) ? '結果を見る' : '次へ';
  $('feedback').hidden = false;
  $('btn-next').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function nextQuestion() {
  const quiz = state.quiz;
  quiz.index++;
  if (quiz.index >= quiz.questions.length) showResult();
  else renderQuestion();
}

// --- 結果画面 -----------------------------------------------

function showResult() {
  const quiz = state.quiz;
  const total = quiz.questions.length;
  $('score').textContent = quiz.correct + ' / ' + total;
  $('score-rate').textContent = '正答率 ' + Math.round(quiz.correct / total * 100) + '%';

  const list = $('wrong-list');
  list.innerHTML = '';
  if (!quiz.wrong.length) {
    const li = document.createElement('li');
    li.innerHTML = '<p class="all-correct">全問正解です。</p>';
    list.appendChild(li);
  } else {
    // 同じ遺産を複数回間違えた場合はまとめる
    const seen = new Set();
    quiz.wrong.forEach((s) => {
      if (seen.has(s.qid)) return;
      seen.add(s.qid);
      const li = document.createElement('li');
      const name = document.createElement('span');
      name.className = 'wrong-name';
      name.textContent = s.ja;
      const meta = document.createElement('span');
      meta.className = 'wrong-meta';
      meta.textContent = siteSummary(s);
      li.appendChild(name);
      li.appendChild(meta);
      list.appendChild(li);
    });
  }

  updateStatsView();
  updateResultBackupHint();
  showScreen('result');
}

// B. 書き出さないまま一定問数を超えたら、結果画面で一言だけ促す
function updateResultBackupHint() {
  const box = $('backup-hint');
  if (!box) return;
  const info = loadBackupInfo();
  const since = totalAnswers() - (info.answersAtExport || 0);
  const show = since >= BACKUP.remindAfterAnswers;
  box.hidden = !show;
  if (show) {
    $('backup-hint-text').textContent = info.lastExport
      ? '前回の書き出しから' + since + '問ぶんの記録がたまっています。'
      : '記録が' + since + '問ぶんたまっています。この端末を離れると失われます。';
  }
}

// --- 開始・中断 ---------------------------------------------

function startQuiz() {
  const quiz = buildQuiz();
  if (!quiz || !quiz.questions.length) {
    alert('条件に合う問題を作れませんでした。フィルタを緩めてください。');
    return;
  }
  state.quiz = quiz;
  showScreen('quiz');
  renderQuestion();
}

// ============================================================
// 記録の書き出し／読み込み（§7.1 任意機能）
// ============================================================

function exportStats() {
  const blob = new Blob([JSON.stringify(stats, null, 1)], { type: 'application/json' });
  const a = document.createElement('a');
  const d = new Date();
  const stamp = d.getFullYear() + String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
  a.href = URL.createObjectURL(blob);
  a.download = 'heritage-quiz-stats-' + stamp + '.json';
  a.click();
  URL.revokeObjectURL(a.href);
  markExported();
  updateStatsView();
  updateResultBackupHint();
}

function importStats(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (typeof data !== 'object' || data === null) throw new Error('形式が違います');
      let merged = 0;
      for (const k of Object.keys(data)) {
        const v = data[k];
        if (!v || typeof v.correct !== 'number' || typeof v.wrong !== 'number') continue;
        const cur = stats[k] || { correct: 0, wrong: 0, lastAnswered: 0 };
        stats[k] = {
          correct: cur.correct + v.correct,
          wrong: cur.wrong + v.wrong,
          lastAnswered: Math.max(cur.lastAnswered || 0, v.lastAnswered || 0)
        };
        merged++;
      }
      saveStats();
      updateStatsView();
      alert(merged + '件の記録を現在の記録に合算しました。');
    } catch (e) {
      alert('読み込めませんでした: ' + e.message);
    }
  };
  reader.readAsText(file);
}

// ============================================================
// 初期化
// ============================================================

function init() {
  $('master-info').textContent =
    'マスタ ' + SITES.length + '件 / 出題可能 ' + ELIGIBLE.length + '件';

  buildChips();
  updatePoolInfo();
  updateStatsView();

  document.querySelectorAll('#mode-select .seg-btn').forEach((b) => {
    b.addEventListener('click', () => {
      state.mode = b.dataset.mode;
      document.querySelectorAll('#mode-select .seg-btn').forEach((x) => x.classList.remove('is-on'));
      b.classList.add('is-on');
      $('mode-hint').textContent = state.mode === 'weak'
        ? '間違えた回数の多い遺産が出やすくなります。'
        : 'フィルタ内から均等に出題します。';
    });
  });

  $('btn-start').addEventListener('click', startQuiz);
  $('btn-next').addEventListener('click', nextQuestion);
  $('btn-again').addEventListener('click', startQuiz);
  $('btn-home').addEventListener('click', () => {
    updatePoolInfo();
    showScreen('start');
  });
  $('btn-quit').addEventListener('click', () => {
    if (state.quiz.index > 0 && !confirm('中断してスタート画面に戻りますか？')) return;
    updateStatsView();
    showScreen('start');
  });

  $('btn-export').addEventListener('click', exportStats);
  $('btn-export-result').addEventListener('click', exportStats);
  $('import-file').addEventListener('change', (e) => {
    if (e.target.files[0]) importStats(e.target.files[0]);
    e.target.value = '';
  });
  $('btn-reset').addEventListener('click', () => {
    if (!confirm('学習記録をすべて消します。よろしいですか？')) return;
    stats = {};
    saveStats();
    updateStatsView();
  });
}

init();
