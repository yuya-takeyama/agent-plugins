/* oxlint-disable unicorn/consistent-function-scoping -- every runtime is inlined into one shared <script>; the surrounding block keeps these helpers private instead of global */
// course shell: outline, home, routing, progress, review. Knows nothing about unit kinds except
// that a quiz unit can be re-instantiated with collected questions for the review.
{
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const clean = (v) => ({ frac: +v.frac || 0, done: !!v.done, score: v.score == null ? undefined : +v.score,
                      total: v.total == null ? undefined : +v.total, wrong: Array.isArray(v.wrong) ? v.wrong.map(Number) : [] });
const lessonDuration = (l) => l.units.reduce((a, u) => a + (u.duration || 0), 0);
  const DATA = JSON.parse(document.getElementById('cs-data').textContent);
  const META = DATA.meta, LESSONS = DATA.lessons;
  const UNITS = LESSONS.flatMap((l) => l.units.map((u) => ({ ...u, lesson: l })));
  const byUnit = new Map(UNITS.map((u) => [u.id, u]));
  const byLesson = new Map(LESSONS.map((l) => [l.id, l]));
  const root = document.documentElement;

  // ---------- persistence: localStorage when available, otherwise in-memory state ----------
  const state = { units: {}, resume: null };   // units[uid] = {frac, done, score, total, wrong}
  const local = { get(k) { try { return JSON.parse(localStorage.getItem('cs:' + location.pathname + ':' + k)); } catch { return null; } },
                  set(k, v) { try { localStorage.setItem('cs:' + location.pathname + ':' + k, JSON.stringify(v)); } catch {} } };
  const timers = {};
  function save(key, value, delay = 0) {
    clearTimeout(timers[key]);
    timers[key] = setTimeout(() => { local.set(key, value); }, delay);
  }
  for (const u of UNITS) { const v = local.get(`u:${u.id}`); if (v && typeof v === 'object') state.units[u.id] = clean(v); }
  { const r = local.get('resume'); if (r && byUnit.has(r.unit)) state.resume = r; }
  const st = (uid) => (state.units[uid] ||= { frac: 0, done: false, wrong: [] });
  const lessonDone = (l) => l.units.every((u) => state.units[u.id]?.done);
  const prefs = { get: (k) => local.get('pref:' + k), set: (k, v) => local.set('pref:' + k, v) };

  // ---------- unit instances, created on first visit ----------
  const instances = new Map();
  let current = null;   // uid or '_review'
  function nextOf(u) {
    const i = u.lesson.units.indexOf(u);
    if (u.lesson.units[i + 1]) return u.lesson.units[i + 1];
    const nl = LESSONS[LESSONS.indexOf(u.lesson) + 1];
    return nl ? nl.units[0] : null;
  }
  function hostFor(u) {
    return {
      saved: state.units[u.id] || null,
      setRest(rest) { if (current === u.id) setHash(`#${u.id}${rest ? '/' + rest : ''}`); },
      progress(frac) { const s = st(u.id); if (frac > s.frac) { s.frac = frac; save(`u:${u.id}`, s, 3000); } },
      position(rest) { state.resume = { unit: u.id, rest }; save('resume', state.resume, 500); refresh(); },
      complete() { const s = st(u.id); if (!s.done) { s.done = true; save(`u:${u.id}`, s); refresh(); } },
      result(r) { const s = st(u.id); Object.assign(s, { score: r.score, total: r.total, wrong: r.wrong }); save(`u:${u.id}`, s); refresh(); },
      endActions() {
        const acts = [], n = nextOf(u);
        if (n && n.lesson === u.lesson) acts.push({ label: n.kind === 'quiz' ? '確認テストへ →' : '次へ →', primary: true, run: () => go(`#${n.id}`) });
        else if (n) acts.push({ label: '次のレッスンへ →', primary: true, run: () => go(`#${n.id}`) });
        if (u.kind === 'quiz' && u.lesson.units[0] !== u) acts.push({ label: '動画を見直す', run: () => go(`#${u.lesson.units[0].id}`) });
        acts.push({ label: 'コースのトップへ', run: () => go('#home') });
        return acts;
      },
      prefs,
    };
  }
  function instance(uid) {
    if (!instances.has(uid)) {
      const u = byUnit.get(uid);
      const node = document.querySelector(`.su-unit[data-unit="${CSS.escape(uid)}"]`);
      instances.set(uid, window.YESUnits.kinds[u.kind](node, DATA.unitData[uid], hostFor(u)));
    }
    return instances.get(uid);
  }

  // ---------- review: one quiz instance over every question still marked wrong ----------
  function wrongItems() {
    const items = [];
    for (const u of UNITS) if (u.kind === 'quiz') for (const qi of state.units[u.id]?.wrong || []) {
      const q = DATA.unitData[u.id].questions[qi];
      if (q) items.push({ ...q, from: u.lesson.title, ref: { unit: u.id, idx: qi } });
    }
    return items;
  }
  function openReview() {
    const items = wrongItems();
    if (!items.length) { go('#home'); return; }
    const node = $('cs-review'); node.textContent = '';
    const inst = window.YESUnits.kinds.quiz(node, { title: '間違えた問題の復習', sub: `${items.length} 問`, questions: items }, {
      saved: null, setRest() {}, progress() {}, position() {}, complete() {}, prefs,
      result(r) {
        // a question answered right here leaves its unit's wrong list; the unit's score stays as first taken
        for (const a of r.answers) if (a.correct && a.ref) { const s = st(a.ref.unit); s.wrong = s.wrong.filter((q) => q !== a.ref.idx); save(`u:${a.ref.unit}`, s); }
        refresh();
      },
      endActions() { const left = wrongItems().length;
        return left ? [{ label: `残り ${left} 問をもう一度`, primary: true, run: openReview }, { label: 'コースのトップへ', run: () => go('#home') }]
                    : [{ label: 'コースのトップへ', primary: true, run: () => go('#home') }]; },
    });
    current = '_review';
    inst.show('');
  }

  // ---------- chrome ----------
  function badge(u) {
    const s = state.units[u.id];
    if (u.kind === 'quiz') {
      if (s?.score == null) return el('span', 'cs-badge none', 'テスト未受験');
      return s.score === s.total ? el('span', 'cs-badge crown', `★ 全問正解 ${s.score}/${s.total}`) : el('span', 'cs-badge part', `テスト ${s.score}/${s.total}`);
    }
    if (s?.done) return el('span', 'cs-badge done', '✓ 視聴済み');
    if (s?.frac) return el('span', 'cs-badge none', `${Math.round(s.frac * 100)}%`);
    return null;
  }
  function refresh() {
    const doneN = LESSONS.filter(lessonDone).length;
    const side = $('cs-side'); side.textContent = '';
    const head = el('button', 'cs-side-title', META.title); head.addEventListener('click', () => go('#home')); side.append(head);
    const pr = el('div', 'cs-prog'), pb = el('div', 'cs-prog-bar'), pi = el('i');
    pi.style.width = `${(doneN / LESSONS.length) * 100}%`; pb.append(pi);
    pr.append(pb, el('div', 'cs-prog-txt', `完了 ${doneN} / ${LESSONS.length} レッスン`)); side.append(pr);
    const curU = byUnit.get(current);
    const ol = el('ol');
    LESSONS.forEach((l, i) => {
      const li = el('li', 'cs-lesson'); if (lessonDone(l)) li.classList.add('done');
      const isNow = curU && curU.lesson === l; if (isNow) li.classList.add('now');
      const b = el('button'); b.addEventListener('click', () => go(`#${l.id}`));
      b.append(el('span', 'cs-num', lessonDone(l) ? '✓' : String(i + 1)), el('span', 'cs-name', l.title), el('span', 'cs-meta', lessonDuration(l) ? fmt(lessonDuration(l)) : ''));
      li.append(b);
      if (isNow) {
        const sub = el('div', 'cs-sub');
        for (const u of l.units) {
          if (u.outline.length) for (const o of u.outline) { const ob = el('button', null, o.title); ob.addEventListener('click', () => go(`#${u.id}/${o.rest}`)); sub.append(ob); }
          else { const ub = el('button', null, u.kind === 'quiz' ? '確認テスト' : u.title); ub.addEventListener('click', () => go(`#${u.id}`));
                 if (u.id === current) ub.classList.add('now'); const bd = badge(u); if (bd) ub.append(' ', bd); sub.append(ub); }
        }
        li.append(sub);
      }
      ol.append(li);
    });
    side.append(ol);
    if (root.dataset.view === 'home') renderHome();
  }
  function renderHome() {
    const box = $('cs-home-in'); box.textContent = '';
    const head = el('div', 'cs-home-head'); head.append(el('h1', null, META.title));
    if (META.subtitle) head.append(el('p', null, META.subtitle));
    const total = LESSONS.reduce((a, l) => a + lessonDuration(l), 0);
    head.append(el('p', null, `${LESSONS.length} レッスン ・ 合計 ${Math.round(total / 60)} 分 ・ 完了 ${LESSONS.filter(lessonDone).length} / ${LESSONS.length}`));
    box.append(head);
    const acts = el('div', 'cs-acts');
    const r = state.resume && byUnit.get(state.resume.unit);
    const firstOpen = LESSONS.find((l) => !lessonDone(l));
    const main = el('button', 'cs-act primary', r ? `続きから: ${r.lesson.title}` : firstOpen ? `はじめる: ${firstOpen.title}` : '最初から見直す');
    main.addEventListener('click', () => go(r ? `#${r.id}${state.resume.rest ? '/' + state.resume.rest : ''}` : `#${(firstOpen || LESSONS[0]).id}`));
    acts.append(main);
    const wrong = wrongItems().length;
    if (wrong) { const rb = el('button', 'cs-act', `間違えた問題を復習 (${wrong})`); rb.addEventListener('click', () => go('#review')); acts.append(rb); }
    box.append(acts);
    const cards = el('div', 'cs-cards');
    LESSONS.forEach((l, i) => {
      const c = el('button', 'cs-card'); if (lessonDone(l)) c.classList.add('done');
      c.addEventListener('click', () => go(`#${l.id}`));
      const mid = el('div'); mid.append(el('h3', null, `${i + 1}. ${l.title}`)); if (l.summary) mid.append(el('p', null, l.summary));
      const stc = el('div', 'cs-card-st'); if (lessonDuration(l)) stc.append(el('span', null, fmt(lessonDuration(l))));
      for (const u of l.units) { const bd = badge(u); if (bd) stc.append(bd); }
      c.append(el('span', 'cs-num', lessonDone(l) ? '✓' : String(i + 1)), mid, stc);
      cards.append(c);
    });
    box.append(cards);
    const credits = META.credits || (META.credit ? [META.credit] : []);
    const voices = credits.filter((c) => c.startsWith('VOICEVOX:'));
    const credit = [voices.length ? `音声: ${voices.join('、')}` : '', ...credits.filter((c) => !c.startsWith('VOICEVOX:'))]
      .filter(Boolean).join(' / ');
    if (credit) box.append(el('p', 'cs-credit', credit));
  }

  // ---------- routing: #home  #review  #<lesson>  #<unit>[/<rest>] ----------
  function setHash(h) { if (location.hash !== h) history.replaceState(null, '', h); }
  function go(h) { if (location.hash !== h) history.pushState(null, '', h); route(); }
  function route() {
    const h = decodeURIComponent(location.hash.slice(1));
    const [key, rest = ''] = h.split(/\/(.*)/s);
    let target = byUnit.get(key) || null;
    if (!target && byLesson.has(key)) {
      const l = byLesson.get(key);
      target = l.units.find((u) => !state.units[u.id]?.done) || l.units[0];
    }
    for (const [uid, inst] of instances) if (uid !== target?.id) inst.hide();
    $('cs-review').hidden = key !== 'review';
    root.classList.remove('cs-side-open');
    if (key === 'review') { root.dataset.view = 'unit'; openReview(); refresh(); return; }
    if (!target) { current = null; root.dataset.view = 'home'; refresh(); return; }
    current = target.id; root.dataset.view = 'unit';
    if (rest.endsWith('&shot')) root.classList.add('ev-shot');
    refresh();
    instance(target.id).show(rest);
  }
  $('cs-menu').addEventListener('click', (e) => { e.stopPropagation(); root.classList.toggle('cs-side-open'); });
  document.querySelector('.cs-main').addEventListener('click', (e) => {
    if (root.classList.contains('cs-side-open')) { root.classList.remove('cs-side-open'); e.stopPropagation(); }
  }, true);
  addEventListener('popstate', route);
  addEventListener('hashchange', route);
  route();
}
