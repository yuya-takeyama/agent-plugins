"""e2e for the player's maximize — F / the button / Esc, the Fullscreen API, and the fill-the-page fallback.

Shared by this skill's `build.py check` (one video page) and course's `build.py check` (a video inside the
course shell), which load this file by path. Needs only a Playwright browser.
"""

from __future__ import annotations

from pathlib import Path

# the fallback: a browser without element fullscreen (iPhone Safari)
NO_FULLSCREEN_API = """
for (const o of [Element.prototype, HTMLElement.prototype])
  for (const k of ['requestFullscreen', 'webkitRequestFullscreen'])
    try { Object.defineProperty(o, k, { value: undefined, configurable: true }); } catch {}
"""
VIEWS = {"desktop": (1280, 800), "phone-portrait": (390, 844), "phone-landscape": (844, 390)}


def state(page, sel: str) -> dict:
    """Where the shown player is, whether it is the fullscreen element, and what the button says."""
    return page.evaluate(
        """(sel) => { const r = document.querySelector(sel), b = r.getBoundingClientRect();
          const fs = document.fullscreenElement || document.webkitFullscreenElement || null;
          const hit = document.elementFromPoint(8, 8), st = r.querySelector('.ev-stage').getBoundingClientRect();
          return { full: r.classList.contains('ev-full'), pseudo: r.classList.contains('ev-pseudo'), api: fs === r,
                   x: b.x, y: b.y, w: b.width, h: b.height, vw: innerWidth, vh: innerHeight, sw: Math.round(st.width),
                   front: !!hit && r.contains(hit),
                   label: r.querySelector('.ev-fs').getAttribute('aria-label') }; }""",
        sel,
    )


def fills(s: dict) -> bool:
    return abs(s["x"]) < 1 and abs(s["y"]) < 1 and abs(s["w"] - s["vw"]) < 1 and abs(s["h"] - s["vh"]) < 1


def check_maximize(browser, url: str, sel: str, expect, frames: Path, label: str = "") -> None:
    """`url` opens the video past its start screen; `sel` matches the shown player's root (.ev-video)."""
    frames.mkdir(parents=True, exist_ok=True)
    tag = f"{label}: " if label else ""
    errors: list[str] = []

    def open_page(view: str, no_api: bool = False):
        w, h = VIEWS[view]
        ctx = browser.new_context(viewport={"width": w, "height": h})
        if no_api:
            ctx.add_init_script(NO_FULLSCREEN_API)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_timeout(500)
        return ctx, page

    def button(page):
        return page.locator(f"{sel} .ev-controls .ev-fs")

    # desktop: F in, Esc out, the button in and out; playback keys still work while maximized
    ctx, page = open_page("desktop")
    s0 = state(page, sel)
    expect(not s0["full"] and s0["label"] == "全画面", f"{tag}the player starts in the page, button says 全画面")
    page.keyboard.press("f")
    page.wait_for_timeout(500)
    s = state(page, sel)
    expect(s["api"] and s["full"] and not s["pseudo"] and fills(s) and s["label"] == "全画面を終了",
           f"{tag}F puts the player in fullscreen over the whole viewport {s}")
    # 16:9 at the largest size the screen allows
    expect(s["sw"] > s0["sw"] and min(s["sw"], round(s["vh"] * 16 / 9)) - 2 <= s["sw"] <= s["vw"],
           f"{tag}the stage grows to the screen's limit ({s0['sw']} -> {s['sw']} px)")
    expect(s["front"], f"{tag}nothing of the page shows over the maximized player")
    page.keyboard.press("Space")
    page.wait_for_timeout(400)
    playing = page.evaluate(f"!document.querySelector({sel!r} + ' audio').paused")
    page.keyboard.press("Space")
    page.wait_for_timeout(300)
    expect(playing, f"{tag}Space plays while maximized")
    page.screenshot(path=str(frames / f"_full-desktop{('-' + label) if label else ''}.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    s = state(page, sel)
    expect(not s["api"] and not s["full"] and s["sw"] == s0["sw"] and s["label"] == "全画面", f"{tag}Esc leaves fullscreen {s}")
    button(page).click()
    page.wait_for_timeout(500)
    s = state(page, sel)
    expect(s["api"] and fills(s), f"{tag}the button maximizes")
    button(page).click()
    page.wait_for_timeout(500)
    s = state(page, sel)
    expect(not s["api"] and not s["full"], f"{tag}the button again restores")
    ctx.close()

    # phones: the same, looked at upright and sideways
    for view in ("phone-portrait", "phone-landscape"):
        ctx, page = open_page(view)
        button(page).click()
        page.wait_for_timeout(600)
        s = state(page, sel)
        expect(s["full"] and fills(s), f"{tag}{view}: the button maximizes {s}")
        page.screenshot(path=str(frames / f"_full-{view}{('-' + label) if label else ''}.png"))
        ctx.close()

    # no element fullscreen: the player fills the page instead, and leaves the same ways
    ctx, page = open_page("desktop", no_api=True)
    button(page).click()
    page.wait_for_timeout(400)
    s = state(page, sel)
    expect(s["full"] and s["pseudo"] and not s["api"] and fills(s) and s["front"] and s["label"] == "全画面を終了",
           f"{tag}without the Fullscreen API the button fills the page, in front of everything {s}")
    page.screenshot(path=str(frames / f"_full-fallback{('-' + label) if label else ''}.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    s = state(page, sel)
    expect(not s["full"] and not s["pseudo"], f"{tag}Esc leaves the filled page {s}")
    page.keyboard.press("f")
    page.wait_for_timeout(300)
    s = state(page, sel)
    expect(s["pseudo"] and fills(s), f"{tag}F fills the page without the API")
    button(page).click()
    page.wait_for_timeout(300)
    expect(not state(page, sel)["full"], f"{tag}the button leaves the filled page")
    ctx.close()

    # the screenshot mode never offers it
    ctx, page = open_page("desktop")
    page.evaluate("location.hash = location.hash.replace(/(t=[\\d.]+)$/, '$1&shot')")
    page.wait_for_timeout(400)
    page.keyboard.press("f")
    page.wait_for_timeout(300)
    s = state(page, sel)
    expect(not s["full"] and not button(page).is_visible(), f"{tag}the shot mode has no maximize")
    ctx.close()
    expect(not errors, f"{tag}no page errors while maximizing {errors[:3]}")
