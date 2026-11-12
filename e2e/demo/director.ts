/**
 * Helpers that make a scripted recording watchable: a visible cursor that glides to its
 * target, click ripples and captions. Videos are recorded per demo, after its setup.
 */
import type { Browser, BrowserContext, Locator, Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const OUT = join(__dirname, "output");
export const SCREENS = join(__dirname, "output", "screens");
const SIZE = { width: 1280, height: 720 };

const OVERLAY = `
(() => {
  const install = () => {
    if (document.getElementById("demo-cursor")) return;
    const style = document.createElement("style");
    style.textContent = \`
      #demo-cursor { position: fixed; z-index: 2147483647; left: 0; top: 0; width: 22px; height: 22px;
        pointer-events: none; transform: translate(-3px, -2px); transition: transform 0.05s; }
      #demo-cursor svg { filter: drop-shadow(0 1px 2px rgba(0,0,0,.35)); }
      .demo-ripple { position: fixed; z-index: 2147483646; width: 34px; height: 34px; margin: -17px 0 0 -17px;
        border-radius: 50%; border: 2px solid #2747d6; pointer-events: none; animation: demo-ripple .5s ease-out forwards; }
      @keyframes demo-ripple { from { transform: scale(.3); opacity: 1 } to { transform: scale(1.4); opacity: 0 } }
      #demo-caption { position: fixed; z-index: 2147483645; left: 50%; bottom: 28px; transform: translateX(-50%);
        max-width: 880px; padding: 12px 20px; border-radius: 10px; background: rgba(20,33,43,.92); color: #fff;
        font: 500 19px/1.4 "IBM Plex Sans", system-ui, sans-serif; text-align: center; pointer-events: none;
        opacity: 0; transition: opacity .35s; box-shadow: 0 10px 30px -10px rgba(0,0,0,.5); }
      #demo-caption.on { opacity: 1; }
    \`;
    document.head.appendChild(style);
    const cursor = document.createElement("div");
    cursor.id = "demo-cursor";
    cursor.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24"><path d="M4 2l15 9.5-6.6 1.4L16 21l-3 1.4-3.6-8.1L4 18.6z" fill="#14212b" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(cursor);
    const caption = document.createElement("div");
    caption.id = "demo-caption";
    document.body.appendChild(caption);
    const last = window.__demoCursor || { x: 640, y: 360 };
    cursor.style.left = last.x + "px"; cursor.style.top = last.y + "px";
    document.addEventListener("mousemove", (e) => {
      cursor.style.left = e.clientX + "px"; cursor.style.top = e.clientY + "px";
      window.__demoCursor = { x: e.clientX, y: e.clientY };
      try { sessionStorage.setItem("demo-cursor", JSON.stringify(window.__demoCursor)); } catch {}
    }, true);
    document.addEventListener("mousedown", (e) => {
      const ripple = document.createElement("div");
      ripple.className = "demo-ripple"; ripple.style.left = e.clientX + "px"; ripple.style.top = e.clientY + "px";
      document.body.appendChild(ripple); setTimeout(() => ripple.remove(), 600);
    }, true);
  };
  try { window.__demoCursor = JSON.parse(sessionStorage.getItem("demo-cursor") || "null") || undefined; } catch {}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install); else install();
})();
`;

export class Director {
  private position = { x: 640, y: 360 };
  private readonly started = Date.now();
  private readonly marks: Record<string, number> = {};

  private constructor(
    readonly context: BrowserContext,
    readonly page: Page,
    private readonly name: string,
  ) {}

  /** Open a recording context. Anything done before this call is not in the video. */
  static async start(browser: Browser, baseURL: string, name: string, cookies?: Awaited<ReturnType<BrowserContext["cookies"]>>) {
    mkdirSync(SCREENS, { recursive: true });
    const context = await browser.newContext({
      baseURL,
      viewport: SIZE,
      deviceScaleFactor: 1,
      recordVideo: { dir: join(OUT, "raw"), size: SIZE },
    });
    if (cookies?.length) await context.addCookies(cookies);
    await context.addInitScript(OVERLAY);
    const page = await context.newPage();
    return new Director(context, page, name);
  }

  /** Remember the current time in the video, for cutting clips such as the hero animation. */
  mark(name: string) {
    this.marks[name] = (Date.now() - this.started) / 1000;
  }

  async pause(ms: number) {
    await this.page.waitForTimeout(ms);
  }

  async caption(text: string, hold = 2600) {
    await this.page.evaluate((t) => {
      const el = document.getElementById("demo-caption");
      if (!el) return;
      el.textContent = t;
      el.classList.add("on");
    }, text);
    await this.pause(hold);
  }

  async hideCaption() {
    await this.page.evaluate(() => document.getElementById("demo-caption")?.classList.remove("on"));
    await this.pause(350);
  }

  /** Move the cursor to the middle of ``target`` in a smooth, deliberate path. */
  async glide(target: Locator) {
    await target.scrollIntoViewIfNeeded();
    const box = await target.boundingBox();
    if (!box) throw new Error("target is not visible");
    const to = { x: box.x + box.width / 2, y: box.y + Math.min(box.height / 2, 18) };
    const distance = Math.hypot(to.x - this.position.x, to.y - this.position.y);
    await this.page.mouse.move(to.x, to.y, { steps: Math.max(12, Math.round(distance / 14)) });
    this.position = to;
    await this.pause(220);
  }

  async click(target: Locator) {
    await this.glide(target);
    await this.page.mouse.down();
    await this.pause(70);
    await this.page.mouse.up();
    await this.pause(450);
  }

  async type(target: Locator, text: string) {
    await this.click(target);
    await this.page.keyboard.type(text, { delay: 28 });
    await this.pause(300);
  }

  /** Scroll the window smoothly so ``target`` sits near the top. */
  async scrollTo(target: Locator, offset = 90) {
    const box = await target.boundingBox();
    if (!box) return;
    await this.page.evaluate(
      ([y]) => window.scrollTo({ top: window.scrollY + y, behavior: "smooth" }),
      [box.y - offset],
    );
    await this.pause(900);
  }

  async screenshot(file: string) {
    await this.hideCaption();
    await this.page.screenshot({ path: join(SCREENS, file) });
  }

  /** Stop recording and keep the video as ``output/<name>.webm``. */
  async finish() {
    const video = this.page.video();
    await this.context.close();
    await video?.saveAs(join(OUT, `${this.name}.webm`));
    writeFileSync(join(OUT, `${this.name}.marks.json`), JSON.stringify(this.marks, null, 2));
  }
}
