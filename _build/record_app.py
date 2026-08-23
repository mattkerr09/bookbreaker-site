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

        if not await value("!!document.querySelector('.tab')"):
            raise SystemExit(f"nothing at {URL} — is preview_live.py running?")

        GO = ("(()=>{const b=document.querySelector('.panel.is-on .go');"
              "if(b)b.click();})()")

        # The board first: it is the product. Scan, wait for a real row
        # rather than a fixed delay, then let it sit long enough to read.
        await hold(1.1)
        await js(GO)
        for _ in range(40):
            await shot()
            await asyncio.sleep(1.0 / FPS)
            if await value("(()=>{const o=document.querySelector('#out-board');"
                           "return o?o.querySelectorAll('.play').length:0;})()"):
                break
        else:
            raise SystemExit("the board never rendered a play")
        await hold(2.6)

        await js("(()=>{const i=document.querySelector('#b-bank');"
                 "if(i){i.value='5000';i.dispatchEvent(new Event('input',{bubbles:true}));}"
                 "const b=document.querySelector('.panel.is-on .go');if(b)b.click();})()")
        await hold(2.4)

        # Then the working behind the answer.
        await js('(()=>{const t=document.querySelector(\'.tab[data-panel="devig"]\');'
                 "if(t)t.click();})()")
        await hold(1.2)
        await js(GO)
        await hold(2.6)

    print(f"{frame[0]} frames -> {out}")


if __name__ == "__main__":
    asyncio.run(main(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "frames")))
