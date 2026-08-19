"""Re-shoot the three panel stills from the window as it stands now.

Kept as a script rather than a memory, because the portfolio site's hardest
lesson was a product screenshot that drifted from the product with nothing to
notice. A picture of a product is a claim about the product.
"""
import asyncio, base64, json, pathlib, sys, urllib.request, websockets

OUT = pathlib.Path(sys.argv[1])
PANELS = [("arb", "panel-arbitrage.jpg"), ("kelly", "panel-stake.jpg"),
          ("parlay", "panel-parlay.jpg")]


async def main():
    tabs = json.load(urllib.request.urlopen("http://localhost:9222/json"))
    page = next(t for t in tabs if t["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=64*1024*1024) as ws:
        n = [0]
        async def send(m, p=None):
            n[0] += 1
            await ws.send(json.dumps({"id": n[0], "method": m, "params": p or {}}))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == n[0]:
                    return r.get("result", {})
        async def ev(e):
            r = await send("Runtime.evaluate", {"expression": e, "returnByValue": True})
            return r.get("result", {}).get("value")

        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1280, "height": 720, "deviceScaleFactor": 2, "mobile": False})
        await send("Page.navigate", {"url": "http://localhost:8902/"})
        await asyncio.sleep(3)

        for panel, name in PANELS:
            await ev(f"(()=>{{const t=document.querySelector('.tab[data-panel=\"{panel}\"]');if(t)t.click();}})()")
            await asyncio.sleep(0.7)
            await ev("(()=>{const b=document.querySelector('.panel.is-on .go');if(b)b.click();})()")
            # Wait for the answer rather than guessing a delay.
            for _ in range(40):
                await asyncio.sleep(0.15)
                if await ev(f"(()=>{{const o=document.querySelector('#out-{panel}');"
                            f"return !!(o&&o.textContent.trim()&&!/Working/.test(o.textContent));}})()"):
                    break
            else:
                raise SystemExit(f"{panel} never rendered an answer")
            shot = await send("Page.captureScreenshot", {"format": "jpeg", "quality": 88})
            (OUT / name).write_bytes(base64.b64decode(shot["data"]))
            print(f"  {name}")


asyncio.run(main())
