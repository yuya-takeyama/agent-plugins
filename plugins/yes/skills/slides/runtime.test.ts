import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';

const DIR = __dirname;
const read = (name: string) => readFileSync(path.join(DIR, name), 'utf8');
// Both files end with a single newline; the HTML embeds them as
// <tag>\n<file without its final newline>\n</tag>.
const runtimeJs = read('runtime.js').trimEnd();
const runtimeCss = read('runtime.css').trimEnd();
const example = read('example.html');

type Loc = { pathname: string; protocol: string };
interface Internals {
  parseSize(text: string | null): { w: number; h: number };
  parseHash(hash: string): { slide: number | string; step: number } | null;
  formatHash(slide: number, step: number): string;
  fitScale(vw: number, vh: number, w: number, h: number, pad: number): number;
  pageHref(loc: Loc, id: string, hash: string, framed: boolean): { href: string; target: string } | null;
  buildRange(el: Element): { from: number; until: number };
  start(): void;
  api: {
    scene(name: string, def: Record<string, unknown>): void;
    go(slide: number | string, step?: number): void;
    next(): void;
    prev(): void;
    sfx(name: string, n?: number): boolean;
    readonly state: { slide: number; step: number; steps: number; count: number; mode: string };
  };
}

// Load a deck into happy-dom (scripts inside innerHTML are inert), evaluate the
// runtime as the inline copy would run, register scenes, then start it.
function boot(html: string, hash = '', scenes: (api: Internals['api']) => void = () => {}): Internals {
  history.replaceState(null, '', location.pathname + hash);
  // drop <link>s: happy-dom would fetch the Google Fonts stylesheet
  const doc = html.replace(/^<!doctype html>\s*/i, '').replace(/<link\b[^>]*>/gi, '');
  document.documentElement.innerHTML = doc.replace(/^<html[^>]*>/i, '').replace(/<\/html>\s*$/i, '');
  new Function(runtimeJs)();
  const ss = (window as unknown as { __yesSlides: Internals }).__yesSlides;
  scenes(ss.api);
  // the deck's own scripts (scene registrations) run after the runtime, as in the page
  for (const sc of document.querySelectorAll('script:not([data-slides])')) new Function(sc.textContent ?? '')();
  ss.start();
  return ss;
}
const web = (pathname: string): Loc => ({ pathname, protocol: 'https:' });
const deck = (slides: string, attrs = '') => `<main class="deck"${attrs}>${slides}</main>`;
const plain = (n: number) => Array.from({ length: n }, (_, i) => `<section class="slide"><h2>S${i + 1}</h2></section>`).join('');

beforeEach(() => {
  document.documentElement.innerHTML = '<head></head><body></body>';
  document.documentElement.removeAttribute('style');
});

describe('template and example embed the runtime verbatim', () => {
  it.each(['template.html', 'example.html'])('%s', (name) => {
    const html = read(name);
    expect(html).toContain(`<style data-slides>\n${runtimeCss}\n</style>`);
    expect(html).toContain(`<script data-slides>\n${runtimeJs}\n</script>`);
    expect(html).toContain('<!-- slides runtime v1 -->');
  });

  it.each(['template.html', 'example.html'])('%s links out only with target=_blank', (name) => {
    const doc = new DOMParser().parseFromString(read(name).replace(/<link\b[^>]*>/gi, ''), 'text/html');
    for (const a of doc.querySelectorAll('a[href^="http"]')) {
      expect(a.getAttribute('target')).toBe('_blank');
      expect(a.getAttribute('rel')).toContain('noopener');
    }
  });
});

describe('runtime.css', () => {
  it('hides every build attribute until its step, not only data-step', () => {
    expect(runtimeCss).toContain(':is([data-step], [data-only], [data-until]):not(.on)');
    expect(runtimeCss).not.toMatch(/(^|[\s,])\[data-step\]:not\(\.on\)/);
  });
});

describe('runtime.css specificity', () => {
  it('keeps element defaults at zero specificity so deck classes win', () => {
    expect(runtimeCss).not.toMatch(/(^|[\s,])\.slide (h1|h2|h3|p|ul|ol|code|pre|table|th|td|svg)\b/m);
    expect(runtimeCss).toContain(':where(.slide) table');
  });
});

describe('pure helpers', () => {
  const ss = () => boot(deck(plain(1)));

  it('parses slide numbers, slide ids and steps from the fragment, and nothing else', () => {
    const { parseHash } = ss();
    expect(parseHash('#5')).toEqual({ slide: 4, step: 0 });
    expect(parseHash('#5.2')).toEqual({ slide: 4, step: 2 });
    expect(parseHash('#intro.3')).toEqual({ slide: 'intro', step: 3 });
    expect(parseHash('')).toBeNull();
    expect(parseHash('#<img src=x>')).toBeNull();
    expect(parseHash('#5.')).toBeNull();
  });

  it('writes the opening state as no fragment and step 0 as the bare slide number', () => {
    const { formatHash } = ss();
    expect(formatHash(0, 0)).toBe('');
    expect(formatHash(0, 1)).toBe('#1.1');
    expect(formatHash(1, 0)).toBe('#2');
    expect(formatHash(2, 3)).toBe('#3.3');
  });

  it('reads the design size and falls back to 1280x720', () => {
    const { parseSize, fitScale } = ss();
    expect(parseSize('1920x1080')).toEqual({ w: 1920, h: 1080 });
    expect(parseSize('huge')).toEqual({ w: 1280, h: 720 });
    expect(fitScale(1312, 752, 1280, 720, 16)).toBeCloseTo(1);
  });

  it('keeps relative links and rejects executable URLs', () => {
    const { pageHref } = ss();
    expect(pageHref(web('/docs/slides.html'), 'other.html', '#3.2', false)).toEqual({href:'other.html#3.2',target:''});
    expect(pageHref(web('/docs/'), 'https://example.com/', '', false)).toEqual({href:'https://example.com/',target:'_blank'});
    expect(pageHref(web('/'), 'javascript:alert(1)', '', false)).toBeNull();
    expect(pageHref(web('/'), '//example.com', '', false)).toBeNull();
    expect(pageHref(web('/'), 'data:text/html,x', '', false)).toBeNull();
  });
});

describe('navigation', () => {
  const stepped = deck(
    `<section class="slide"><h2>A</h2></section>
     <section class="slide" id="b"><h2>B</h2><p data-step="1">one</p><p data-step="2" data-until="2">two</p><p data-only="3">three</p></section>
     <section class="slide"><h2>C</h2></section>`,
  );

  it('walks steps before slides and mirrors the position in the fragment', () => {
    const { api } = boot(stepped);
    expect(api.state).toMatchObject({ slide: 0, step: 0, count: 3 });
    expect(location.hash).toBe('');
    api.next();
    expect(api.state).toMatchObject({ slide: 1, step: 0, steps: 3 });
    expect(location.hash).toBe('#2');
    api.next(); api.next();
    expect(location.hash).toBe('#2.2');
    const [one, two, three] = [...document.querySelectorAll('#b p')];
    expect(one.classList.contains('on')).toBe(true);
    expect(one.classList.contains('past')).toBe(true);
    expect(two.classList.contains('now')).toBe(true);
    expect(three.classList.contains('on')).toBe(false);
    api.next();
    expect(two.classList.contains('on')).toBe(false);
    expect(three.classList.contains('on')).toBe(true);
    api.next();
    expect(api.state).toMatchObject({ slide: 2, step: 0 });
    api.prev();
    expect(api.state).toMatchObject({ slide: 1, step: 3 });
  });

  it('drops the fragment on the opening state and returns there when it is cleared', () => {
    const { api } = boot(stepped, '#2.1');
    api.go(0);
    expect(location.hash).toBe('');
    api.go(2);
    expect(location.hash).toBe('#3');
    history.replaceState(null, '', location.pathname);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    expect(api.state).toMatchObject({ slide: 0, step: 0 });
  });

  it('opens at the step named in the fragment, by number or by slide id', () => {
    expect(boot(stepped, '#2.2').api.state).toMatchObject({ slide: 1, step: 2 });
    expect(boot(stepped, '#b.1').api.state).toMatchObject({ slide: 1, step: 1 });
    expect(boot(stepped, '#2.99').api.state).toMatchObject({ slide: 1, step: 3 });
    expect(boot(stepped, '#nope').api.state).toMatchObject({ slide: 0, step: 0 });
  });

  it('shows dots up to 12 slides and a number input beyond', () => {
    boot(deck(plain(12)));
    expect(document.querySelectorAll('.ss-dots button')).toHaveLength(12);
    expect(document.querySelector('.ss-jump input')).toBeNull();
    const { api } = boot(deck(plain(13)));
    expect(document.querySelector('.ss-dots')).toBeNull();
    const input = document.querySelector<HTMLInputElement>('.ss-jump input')!;
    expect(input.value).toBe('1');
    input.value = '9';
    input.dispatchEvent(new Event('change'));
    expect(api.state.slide).toBe(8);
  });

  it('jumps with typed digits and Enter', () => {
    const { api } = boot(deck(plain(20)));
    for (const key of ['1', '5', 'Enter']) document.body.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    expect(api.state.slide).toBe(14);
  });

  it('lists every slide title in the table of contents', () => {
    boot(deck(`<section class="slide" data-title="Custom"><h2>Ignored</h2></section><section class="slide"><h3>Heading</h3></section>`));
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 't', bubbles: true }));
    expect([...document.querySelectorAll('.ss-toc li span')].map((e) => e.textContent)).toEqual(['Custom', 'Heading']);
  });
});

describe('scenes', () => {
  it('count toward the steps and redraw the target step without animation on a jump', () => {
    const calls: [number, boolean][] = [];
    const { api } = boot(deck(`${plain(1)}<section class="slide" data-scene="s"><h2>S</h2></section>`), '#2.2', (a) =>
      a.scene('s', { steps: 3, step: (ctx: { animate: boolean }, k: number) => calls.push([k, ctx.animate]) }),
    );
    expect(api.state).toMatchObject({ slide: 1, step: 2, steps: 3 });
    expect(calls).toEqual([[2, false]]);
    api.next();
    expect(calls.at(-1)).toEqual([3, true]);
  });
});

// A stand-in AudioContext that counts the oscillators it starts.
const param = () => ({ value: 0, setValueAtTime() {}, exponentialRampToValueAtTime() {} });
const node = () => ({ connect() {}, gain: param(), frequency: param() });
function fakeAudio() {
  const started: number[] = [];
  class FakeAC {
    state = 'running';
    currentTime = 0;
    sampleRate = 8000;
    destination = {};
    createGain = node;
    createDynamicsCompressor = node;
    createBiquadFilter = () => ({ ...node(), type: '' });
    createBuffer = (_c: number, len: number) => ({ getChannelData: () => new Float32Array(len) });
    createBufferSource = () => ({ connect() {}, start() {}, stop() {} });
    createOscillator = () => ({ ...node(), type: '', start: (t: number) => started.push(t), stop() {} });
  }
  (window as unknown as { AudioContext: unknown }).AudioContext = FakeAC;
  return started;
}
const soundDeck = (attr = ' data-sound') =>
  deck(`<section class="slide"><h2>A</h2><p data-step="1">x</p></section><section class="slide"><h2>B</h2></section>`, attr);

describe('sound', () => {
  it('offers no toggle unless the deck asks for sound', () => {
    boot(deck(plain(2)));
    expect(document.querySelector('.ss-bar [aria-label="効果音 (S)"]')).toBeNull();
  });

  it('starts muted and stays silent until the viewer turns it on', () => {
    const started = fakeAudio();
    const { api } = boot(soundDeck());
    const toggle = document.querySelector<HTMLButtonElement>('.ss-bar [aria-label="効果音 (S)"]')!;
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
    api.next();
    expect(api.sfx('correct')).toBe(false);
    expect(started).toHaveLength(0);
    toggle.click();
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
    const afterToggle = started.length;
    expect(afterToggle).toBeGreaterThan(0);
    api.next();
    expect(started.length).toBeGreaterThan(afterToggle);
    const beforeBack = started.length;
    api.prev();
    expect(started.length).toBe(beforeBack);
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 's', bubbles: true }));
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
    expect(api.sfx('correct')).toBe(false);
  });

  it('leaves navigation quiet with data-sound="manual"', () => {
    const started = fakeAudio();
    const { api } = boot(soundDeck(' data-sound="manual"'));
    document.querySelector<HTMLButtonElement>('.ss-bar [aria-label="効果音 (S)"]')!.click();
    const n = started.length;
    api.next(); api.next();
    expect(started.length).toBe(n);
    expect(api.sfx('xp')).toBe(true);
  });
});

describe('links to other documents', () => {
  it('fills href from data-page', () => {
    boot(deck(`<section class="slide"><a data-page="other.html#3.1">x</a></section>`));
    const a = document.querySelector('a')!;
    expect(a.getAttribute('href')).toMatch(/other\.html#3\.1$/);
  });
});

describe('example.html', () => {
  it('boots with every slide titled and the scene registered', () => {
    const { api } = boot(example);
    expect(api.state.count).toBeGreaterThanOrEqual(8);
    api.go('scene', 2);
    expect(api.state.steps).toBe(3);
    expect(document.querySelector('#scene .readout')!.textContent).toContain('step 2');
  });
});
