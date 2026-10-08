#!/usr/bin/env python3
"""Record the hero video from the real window doing real work.

Lives in the repo, not in a temp directory. The first version of this was a
scratchpad script; the window changed, the gate correctly said the video was
stale, and the tool needed to fix it had been cleaned up — so the fix cost a
rewrite instead of a command. `_build/shoot_panels.py` was committed for
exactly this reason and survived. This is the other half.

Every number that appears comes from the engine during the take. Frames are
captured with Page.captureScreenshot rather than Page.startScreencast:
headless Chrome has no compositor surface to stream from and screencast
returns a handful of frames for a twelve-second take.

Prerequisites — both printed if missing:
    Chrome with --remote-debugging-port=9222
    OVERLAY_PREVIEW_ENGINE=source python3 scripts/preview_live.py   (in the app repo)

    python3 _build/record_app.py <frames-dir>
"""

from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import sys
import urllib.error
import urllib.request

try:
    import websockets
except ImportError:                                        # pragma: no cover
    raise SystemExit("pip install websockets")

URL = "http://localhost:8902/"
W, H, FPS = 1280, 800, 12


async def main(out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    try:
        tabs = json.load(urllib.request.urlopen("http://localhost:9222/json"))
    except urllib.error.URLError:
        raise SystemExit("no Chrome on :9222 — start it with "
                         "--remote-debugging-port=9222 --headless=new")
    page = next(t for t in tabs if t["type"] == "page")
    frame = [0]

    async with websockets.connect(page["webSocketDebuggerUrl"],
                                  max_size=64 * 1024 * 1024) as ws:
        n = [0]

        async def send(method, params=None):
            n[0] += 1
            await ws.send(json.dumps({"id": n[0], "method": method,
                                      "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == n[0]:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg.get("result", {})

        async def shot():
            got = await send("Page.captureScreenshot", {"format": "png"})
            (out / f"f{frame[0]:05d}.png").write_bytes(
                base64.b64decode(got["data"]))
            frame[0] += 1

        async def hold(seconds):
            for _ in range(max(1, int(seconds * FPS))):
                await shot()
                await asyncio.sleep(1.0 / FPS)

        async def js(expr):
            await send("Runtime.evaluate", {"expression": expr})

        async def value(expr):
            got = await send("Runtime.evaluate",
                             {"expression": expr, "returnByValue": True})
            return got["result"]["value"]

        await send("Page.enable")
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": W, "height": H, "deviceScaleFactor": 2,
                    "mobile": False})
        await send("Page.navigate", {"url": URL})
        await asyncio.sleep(3.0)

        if not await value("!!document.querySelector('[data-panel]')"):
            raise SystemExit(f"nothing at {URL} — is preview_live.py running?")

        # 2026-10-07: the window moved from a tab strip to a rail of places
        # with tabs inside. Every step is addressed by what it is (the panel
        # it opens, the verb it runs, the box its answer lands in), not by
        # where it sits, so a later layout change cannot leave the take
        # clicking at nothing.
        def nav(panel):
            return ("(()=>{const b=document.querySelector('[data-panel=\"%s\"]');"
                    "if(b)b.click();})()" % panel)

        def run(verb):
            return ("(()=>{const b=document.querySelector('.panel.is-on "
                    ".go[data-run=\"%s\"]');if(b)b.click();})()" % verb)

        def landed(box):
            return ("(()=>{const o=document.querySelector('#%s');if(!o)return false;"
                    "const t=o.textContent.trim();return t.length>40&&!/Working/.test(t);})()" % box)

        async def until(expr, what, tries=80):
            for _ in range(tries):
                await shot()
                await asyncio.sleep(1.0 / FPS)
                if await value(expr):
                    return
            raise SystemExit(f"{what} never appeared")

        # 1. Arbitrage, the home page: find a pair, let the console fill.
        await js(nav("board"))
        await hold(1.0)
        await js(run("board"))
        await until(landed("out-board"), "the arbitrage console")
        await hold(3.2)

        # 2. Promos for one state: what each offer locks in, and where.
        await js(nav("welcome"))
        await hold(0.8)
        await js("(()=>{const s=document.querySelector('#w-state');if(s){s.value='MI';"
                 "s.dispatchEvent(new Event('change',{bubbles:true}));}})()")
        await hold(0.6)
        await js(run("welcome"))
        await until(landed("out-welcome"), "the offers")
        await hold(2.8)

        # 3. Tools: the parlay, answered in dollars.
        await js(nav("parlay"))
        await hold(0.8)
        await js(run("parlay"))
        await until(landed("out-parlay"), "the parlay answer")
        await hold(2.6)

        # Back to the console to close the loop.
        await js(nav("board"))
        await hold(1.6)

    print(f"{frame[0]} frames -> {out}")


if __name__ == "__main__":
    asyncio.run(main(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "frames")))
