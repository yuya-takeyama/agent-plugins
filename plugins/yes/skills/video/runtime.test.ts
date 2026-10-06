import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';

const runtimeJs = readFileSync(path.join(__dirname, 'runtime.js'), 'utf8');

interface Line { id?: string; scene?: string; chapter?: string; idx?: number; text?: string; start: number; end: number;
  cues?: { start: number; end: number; html: string }[]; who?: string; face?: string; mouth?: string }
interface Face { layers: string[]; mouth: string[] | null; blink: string | null }
interface Cast { id: string; name?: string; color?: string; side?: string; canvas?: number[];
  layers?: Record<string, { x: number; y: number; w: number; h: number; src: string; blend: string }>;
  base?: string[]; faces?: Record<string, Partial<Face>> }
interface Motion {
  blinkClosed(t: number, seed: number): boolean;
  seedOf(id: string): number;
  mouthLevel(line: Line | null, t: number): number;
  faceAt(lines: Line[], li: number, who: string): string;
  hopAt(lines: Line[], li: number, t: number): number;
  faceOf(ch: Cast, name: string): Face;
  visibleLayers(ch: Cast, f: Face, level: number, blinking: boolean): Set<string>;
  mirrored(side: string, facing?: string): boolean;
  lineAt(lines: Line[], t: number): number;
}
type Unit = { show(rest: string): void; hide(): void };
type Win = Window & { EV: { motion: Motion }; YESUnits: { kinds: { video(root: Element, data: unknown, host: unknown): Unit } } };
const win = () => window as unknown as Win;

beforeAll(() => {
  // the runtime adds the caption font once per document; a placeholder keeps happy-dom off the network
  document.head.innerHTML = '<link data-ev-cap-font>';
  new Function(runtimeJs)();
});
const M = () => win().EV.motion;

function blinkStarts(seed: number, until: number): number[] {
  const starts: number[] = [];
  let prev = false;
  for (let i = 0; i <= until * 1000; i++) {
    const on = M().blinkClosed(i / 1000, seed);
    if (on && !prev) starts.push(i / 1000);
    prev = on;
  }
  return starts;
}

describe('blink schedule', () => {
  it('closes for 120 ms every 3 to 5 s', () => {
    const seed = M().seedOf('zundamon');
    const starts = blinkStarts(seed, 120);
    expect(starts.length).toBeGreaterThanOrEqual(24);
    for (let i = 1; i < starts.length; i++) {
      const gap = starts[i] - starts[i - 1];
      expect(gap).toBeGreaterThan(3 - 1e-6);
      expect(gap).toBeLessThan(5 + 1e-6);
    }
    for (const s of starts) {
      expect(M().blinkClosed(s + 0.119, seed)).toBe(true);
      expect(M().blinkClosed(s + 0.121, seed)).toBe(false);
    }
  });

  it('is a pure function of t and seed, and two characters do not blink together', () => {
    const a = M().seedOf('metan'), b = M().seedOf('zundamon');
    expect(blinkStarts(a, 60)).toEqual(blinkStarts(a, 60));
    const sa = blinkStarts(a, 60), sb = new Set(blinkStarts(b, 60).map((x) => x.toFixed(2)));
    expect(sa.filter((x) => sb.has(x.toFixed(2)))).toEqual([]);
  });
});

describe('line lookup, mouth, face and hop', () => {
  const lines: Line[] = [
    { start: 0.5, end: 1.5, who: 'metan', face: 'smile', mouth: '012' + '2'.repeat(27) },
    { start: 2, end: 3, who: 'zundamon', face: 'troubled', mouth: '0'.repeat(10) + '1'.repeat(10) + '2'.repeat(10) },
    { start: 3.5, end: 4, who: 'zundamon', mouth: '1'.repeat(15) },
    { start: 4.5, end: 5, who: 'metan', face: 'normal' },
  ];

  it('finds the last line starting at or before t', () => {
    expect([0, 0.5, 1.9, 2, 4.4, 9].map((t) => M().lineAt(lines, t))).toEqual([-1, 0, 0, 1, 2, 3]);
  });

  it('reads the mouth frame at 30 fps and closes outside the line', () => {
    expect(M().mouthLevel(lines[1], 2.1)).toBe(0);
    expect(M().mouthLevel(lines[1], 2 + 15 / 30)).toBe(1);
    expect(M().mouthLevel(lines[1], 2 + 25 / 30)).toBe(2);
    expect(M().mouthLevel(lines[1], 3)).toBe(0);
    expect(M().mouthLevel(lines[1], 1.99)).toBe(0);
    expect(M().mouthLevel(lines[3], 4.7)).toBe(0);
    expect(M().mouthLevel(null, 1)).toBe(0);
  });

  it('keeps each character on its last set face, normal before its first line', () => {
    expect(M().faceAt(lines, -1, 'metan')).toBe('normal');
    expect(M().faceAt(lines, 0, 'zundamon')).toBe('normal');
    expect(M().faceAt(lines, 1, 'metan')).toBe('smile');
    expect(M().faceAt(lines, 2, 'zundamon')).toBe('troubled');
    expect(M().faceAt(lines, 3, 'metan')).toBe('normal');
  });

  it('hops over the first 200 ms only when the speaker changes', () => {
    expect(M().hopAt(lines, 1, 2.1)).toBeCloseTo(1);
    expect(M().hopAt(lines, 1, 2.05)).toBeGreaterThan(0);
    expect(M().hopAt(lines, 1, 2.2)).toBe(0);
    expect(M().hopAt(lines, 2, 3.6)).toBe(0);
    expect(M().hopAt(lines, -1, 0)).toBe(0);
  });
});

describe('facing', () => {
  it('mirrors only a character whose art looks away from the stage centre, with missing facing read as left', () => {
    expect(M().mirrored('left', 'left')).toBe(true);
    expect(M().mirrored('right', 'right')).toBe(true);
    expect(M().mirrored('left', 'right')).toBe(false);
    expect(M().mirrored('right', 'left')).toBe(false);
    expect(M().mirrored('left', undefined)).toBe(true);
    expect(M().mirrored('right', undefined)).toBe(false);
  });
});

describe('visible layers', () => {
  // めたん-shaped: the eyes are a white and a pupil layer under one group
  const ch: Cast = {
    id: 'metan', base: ['体', '!前髪'],
    faces: {
      normal: { layers: ['!眉/*ごきげん', '!目/*目セット/*白目', '!目/*目セット/!黒目/*カメラ目線'], mouth: ['!口/*む', '!口/*▽', '!口/*わあー'], blink: '!目/*目閉じ' },
      smile: { layers: ['!眉/*太眉', '!目/*目閉じ2'], mouth: ['!口/*にやり', '!口/*▽', '!口/*わあー'], blink: null },
    },
  };

  it('shows base, the face and the mouth frame for the level', () => {
    const f = M().faceOf(ch, 'normal');
    expect(M().visibleLayers(ch, f, 2, false)).toEqual(
      new Set(['体', '!前髪', '!眉/*ごきげん', '!目/*目セット/*白目', '!目/*目セット/!黒目/*カメラ目線', '!口/*わあー']));
  });

  it('replaces every eye layer with the blink layer', () => {
    const on = M().visibleLayers(ch, M().faceOf(ch, 'normal'), 0, true);
    expect(on.has('!目/*目閉じ')).toBe(true);
    expect([...on].filter((p) => p.startsWith('!目/*目セット'))).toEqual([]);
    expect(on.has('!口/*む')).toBe(true);
  });

  it('does not blink a face whose blink is null, and an unknown face shows normal', () => {
    const on = M().visibleLayers(ch, M().faceOf(ch, 'smile'), 1, true);
    expect(on.has('!目/*目閉じ2')).toBe(true);
    expect(on.has('!目/*目閉じ')).toBe(false);
    expect(M().faceOf(ch, 'nope')).toEqual(M().faceOf(ch, 'normal'));
  });
});

// ---------- the unit in the DOM ----------

const PX = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
const layer = (x = 0) => ({ x, y: 0, w: 10, h: 10, src: PX, blend: 'normal' });
const art = (id: string): Cast => ({
  id, name: id === 'metan' ? '四国めたん' : 'ずんだもん', color: id === 'metan' ? '#d9418c' : '#2e9e3a', canvas: [100, 200],
  layers: { 体: layer(), '!目/*基本': layer(), '!目/*閉じ': layer(), '!口/*閉': layer(), '!口/*半': layer(), '!口/*開': layer(), '!口/*む': { ...layer(), blend: 'multiply' } },
  base: ['体'],
  faces: { normal: { layers: ['!目/*基本'], mouth: ['!口/*閉', '!口/*半', '!口/*開'], blink: '!目/*閉じ' },
           troubled: { layers: ['!目/*基本'], mouth: ['!口/*む', '!口/*半', '!口/*開'], blink: '!目/*閉じ' } },
});

function mount(extra: Record<string, unknown>, lines: Line[]) {
  document.body.innerHTML = '<div class="su-unit" data-unit="u"><section class="scene" data-scene="s1"></section></div>';
  const root = document.querySelector('.su-unit')!;
  const data = {
    title: 'T', goals: [], audio: 'data:audio/wav;base64,',
    timeline: { duration: 10, chapters: [{ id: 'c1', title: '第一章', start: 0, end: 10 }],
      scenes: [{ id: 's1', chapter: 'c1', kind: 'scene', start: 0, end: 10 }], lines },
    ...extra,
  };
  const unit = win().YESUnits.kinds.video(root, data, {
    saved: null, setRest() {}, progress() {}, position() {}, complete() {}, result() {}, endActions: () => [],
    prefs: { get: () => null, set() {} },
  });
  return { root, unit };
}
const shown = (root: Element, who: string) =>
  [...root.querySelectorAll(`.ev-char[data-who="${who}"] img`)].filter((i) => !(i as HTMLImageElement).hidden).length;
const visible = (root: Element, who: string, p: string) => {
  const ch = root.querySelector(`.ev-char[data-who="${who}"]`)!;
  const keys = Object.keys(art(who).layers!);
  return !(ch.querySelectorAll('img')[keys.indexOf(p)] as HTMLImageElement).hidden;
};

describe('video unit with a cast', () => {
  const lines: Line[] = [
    { id: 's1.0', scene: 's1', chapter: 'c1', idx: 0, text: 'めたんの台詞', start: 1, end: 3, who: 'metan', face: 'normal', mouth: '0'.repeat(15) + '2'.repeat(45),
      cues: [{ start: 1, end: 3, html: 'めたんの台詞' }] },
    { id: 's1.1', scene: 's1', chapter: 'c1', idx: 1, text: 'ずんだもんの台詞', start: 4, end: 6, who: 'zundamon', face: 'troubled', mouth: '1'.repeat(60),
      cues: [{ start: 4, end: 6, html: 'ずんだもんの台詞' }] },
  ];
  let root: Element, unit: Unit;
  beforeEach(() => {
    ({ root, unit } = mount({ cast: [art('metan'), art('zundamon')], credits: ['VOICEVOX:四国めたん', 'VOICEVOX:ずんだもん', '立ち絵: 坂本アヒル'], description: '説明文' }, lines));
  });

  it('opens the speaker mouth and keeps the listener closed', () => {
    unit.show('t=2&shot');
    expect(visible(root, 'metan', '!口/*開')).toBe(true);
    expect(visible(root, 'metan', '!口/*閉')).toBe(false);
    expect(visible(root, 'zundamon', '!口/*閉')).toBe(true);
    expect(shown(root, 'metan')).toBe(3);
    unit.show('t=5&shot');
    expect(visible(root, 'metan', '!口/*閉')).toBe(true);
    expect(visible(root, 'zundamon', '!口/*半')).toBe(true);
    expect(root.querySelector('.ev-cap')!.getAttribute('style')).toContain('#2e9e3a');
  });

  it('switches to the sticky face and applies multiply blending', () => {
    unit.show('t=7&shot');
    expect(visible(root, 'zundamon', '!口/*む')).toBe(true);
    const imgs = root.querySelectorAll('.ev-char[data-who="zundamon"] img');
    expect((imgs[6] as HTMLElement).style.mixBlendMode).toBe('multiply');
  });

  it('mirrors the art box, not the character box, for a character facing away', () => {
    ({ root, unit } = mount({ cast: [{ ...art('metan'), side: 'left', facing: 'left' }, { ...art('zundamon'), side: 'right', facing: 'left' }] }, lines));
    const box = (who: string) => root.querySelector(`.ev-char[data-who="${who}"]`) as HTMLElement;
    const artOf = (who: string) => box(who).querySelector('.ev-char-art') as HTMLElement;
    expect(box('metan').classList.contains('mirrored')).toBe(true);
    expect(artOf('metan').style.transform).toMatch(/^translateX\(.+px\) scale\(-/);
    expect(box('metan').style.transform).toBe('');
    expect(box('zundamon').classList.contains('mirrored')).toBe(false);
    expect(artOf('zundamon').style.transform).toMatch(/^scale\([\d.]+\)$/);
  });

  it('prefixes transcript lines with the speaker and lists credits only in the 概要欄', () => {
    const who = [...root.querySelectorAll('.ev-tr .ev-tr-who')].map((b) => b.textContent);
    expect(who).toEqual(['四国めたん', 'ずんだもん']);
    const desc = root.querySelector('.ev-desc')!;
    expect([...desc.querySelectorAll('.ev-desc-credits li')].map((l) => l.textContent)).toEqual(['VOICEVOX:四国めたん', 'VOICEVOX:ずんだもん', '立ち絵: 坂本アヒル']);
    expect(desc.querySelector('.ev-desc-text')!.textContent).toBe('説明文');
    expect(root.querySelector('.ev-stage')!.textContent).not.toContain('VOICEVOX');
    expect(root.querySelector('.ev-tr')!.textContent).not.toContain('VOICEVOX');
  });

  it('seeks to a chapter from the 概要欄', () => {
    unit.show('t=5&shot');
    (root.querySelector('.ev-desc-ch button') as HTMLButtonElement).click();
    expect(root.querySelector('.ev-time')!.textContent).toBe('0:00 / 0:10');
  });
});

describe('video unit without a cast', () => {
  it('draws no characters and moves the single credit to the 概要欄', () => {
    const { root, unit } = mount({ credit: 'VOICEVOX:ずんだもん' }, [
      { id: 's1.0', scene: 's1', chapter: 'c1', idx: 0, text: '台詞', start: 1, end: 3, cues: [{ start: 1, end: 3, html: '台詞' }] }]);
    unit.show('t=2&shot');
    expect(root.querySelector('.ev-char, .ev-board, .ev-cap-edge')).toBeNull();
    expect(root.classList.contains('ev-cast')).toBe(false);
    expect(root.querySelector('.ev-cap > span')!.innerHTML).toBe('台詞');
    expect([...root.querySelectorAll('.ev-desc-credits li')].map((l) => l.textContent)).toEqual(['VOICEVOX:ずんだもん']);
    expect(root.querySelector('.ev-stage')!.textContent).not.toContain('VOICEVOX');
  });
});
