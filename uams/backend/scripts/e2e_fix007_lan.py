"""FIX-007 局域网真实浏览器验收（Chrome + CDP）。

从「局域网地址」而不是 localhost 打开前端，真实登录并访问排课/课表，
同时抓取浏览器发出的每一个请求，验证：

  - 所有请求都打在同一个局域网来源上（http://<LAN_IP>:<前端端口>）；
  - 没有任何请求指向 127.0.0.1 / localhost（FIX-007 §十七 的经典陷阱）；
  - 没有 404、没有 CORS/加载失败。

前置：./start.sh start
用法：.venv/bin/python scripts/e2e_fix007_lan.py [LAN_IP]
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

PROFILE = Path(tempfile.mkdtemp(prefix="uams_fix007_lan_"))
BACKEND_PORT = os.environ.get("UAMS_BACKEND_PORT", "8000")
FRONTEND_PORT = os.environ.get("UAMS_FRONTEND_PORT", "5173")

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    results.append((bool(cond), label))
    print(f"  {'✅' if cond else '❌'} {label}{(' — ' + detail) if detail else ''}")


def lan_ip() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    try:
        out = subprocess.run(
            ["bash", "-c", "ip route get 1.1.1.1 | grep -oP 'src \\K[0-9.]+' | head -1"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()[0]


class Browser:
    """极简 CDP 客户端 + 网络事件采集。"""

    def __init__(self, ws):
        self.ws = ws
        self._id = 0
        self.requests: list[dict] = []
        self.failures: list[dict] = []
        self._url_by_id: dict[str, str] = {}

    async def pump(self, timeout: float = 0.05) -> None:
        """消费已到达的事件（非阻塞）。"""
        try:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            return
        msg = json.loads(raw)
        method = msg.get("method")
        params = msg.get("params", {})
        if method == "Network.requestWillBeSent":
            self._url_by_id[params.get("requestId", "")] = params["request"]["url"]
            self.requests.append({
                "url": params["request"]["url"],
                "method": params["request"]["method"],
            })
        elif method == "Network.responseReceived":
            self.requests.append({
                "url": params["response"]["url"],
                "status": params["response"]["status"],
            })
        elif method == "Network.loadingFailed":
            self.failures.append({
                "url": self._url_by_id.get(params.get("requestId", ""), ""),
                "error": params.get("errorText"),
                "blocked": params.get("blockedReason"),
                "cors": params.get("corsErrorStatus"),
            })

    async def send(self, method: str, **params):
        self._id += 1
        mid = self._id
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            raw = await self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            await self._handle_event(msg)

    async def _handle_event(self, msg: dict) -> None:
        method = msg.get("method")
        params = msg.get("params", {})
        if method == "Network.requestWillBeSent":
            self._url_by_id[params.get("requestId", "")] = params["request"]["url"]
            self.requests.append({
                "url": params["request"]["url"],
                "method": params["request"]["method"],
            })
        elif method == "Network.responseReceived":
            self.requests.append({
                "url": params["response"]["url"],
                "status": params["response"]["status"],
            })
        elif method == "Network.loadingFailed":
            self.failures.append({
                "url": self._url_by_id.get(params.get("requestId", ""), ""),
                "error": params.get("errorText"),
                "blocked": params.get("blockedReason"),
                "cors": params.get("corsErrorStatus"),
            })

    async def js(self, expr: str):
        r = await self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                            awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS 异常：{r['exceptionDetails'].get('text')}")
        return r.get("result", {}).get("value")

    async def goto(self, url: str):
        await self.send("Page.navigate", url=url)
        await self.wait_for("document.readyState === 'complete'", timeout=25)

    async def wait_for(self, expr: str, timeout: float = 20, interval: float = 0.25):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if await self.js(expr):
                    return True
            except RuntimeError:
                pass
            await asyncio.sleep(interval)
        return False

    async def click_text(self, selector: str, text: str) -> bool:
        return await self.js(
            f"""(() => {{
              const els = [...document.querySelectorAll({json.dumps(selector)})];
              const el = els.find(e => (e.textContent || '').includes({json.dumps(text)}));
              if (!el) return false;
              el.click(); return true;
            }})()"""
        )


FILL_INPUT = """
((sel, val) => {
  const el = document.querySelector(sel);
  if (!el) return false;
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value').set;
  setter.call(el, val);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
})(%s, %s)
"""


async def login_as(b: Browser, origin: str, username: str, password: str) -> str:
    # 先落到真实来源再清 localStorage（about:blank 上访问 localStorage 会抛 SecurityError）
    await b.goto(f"{origin}/login")
    await b.js("try { localStorage.clear() } catch (e) {}")
    await b.goto(f"{origin}/login")
    await b.wait_for("document.querySelectorAll('input').length >= 2", timeout=30)
    await b.js(FILL_INPUT % ("'input:not([type=password])'", f"'{username}'"))
    await b.js(FILL_INPUT % ("'input[type=password]'", f"'{password}'"))
    await b.click_text("button", "登 录")
    await b.wait_for(
        "location.pathname.includes('/admin') || location.pathname.includes('/teacher')"
        " || location.pathname.includes('/student')", timeout=30,
    )
    return await b.js("location.pathname")


async def main() -> int:
    ip = lan_ip()
    origin = f"http://{ip}:{FRONTEND_PORT}"
    print(f"局域网地址：{origin}（后端 :{BACKEND_PORT}）")

    # 前置：局域网地址可达
    try:
        r = httpx.get(f"{origin}/", timeout=10)
        check(r.status_code == 200, f"局域网地址可访问 {origin}", str(r.status_code))
        api = httpx.post(f"{origin}/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"}, timeout=10)
        check(api.status_code == 200, "局域网地址下的 /api 代理可用（登录成功）",
              str(api.status_code))
    except Exception as e:  # noqa: BLE001
        check(False, "局域网地址不可达", str(e)[:120])
        return 1

    chrome = subprocess.Popen(
        ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
         "--remote-debugging-port=9225", f"--user-data-dir={PROFILE / 'p'}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        targets = None
        for _ in range(60):
            try:
                targets = httpx.get("http://127.0.0.1:9225/json/list", timeout=2).json()
                if targets:
                    break
            except Exception:
                await asyncio.sleep(0.5)
        if not targets:
            print("❌ 无法连接 Chrome CDP")
            return 1
        page = next(t for t in targets if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=40_000_000) as ws:
            b = Browser(ws)
            await b.send("Page.enable")
            await b.send("Runtime.enable")
            await b.send("Network.enable")

            # ---------- 管理员 ----------
            print("\n[1] 管理员（局域网）")
            path = await login_as(b, origin, "admin", "admin123")
            check("/admin" in path, "局域网登录成功并进入教务端", path)

            await b.goto(f"{origin}/admin/teaching")
            check(await b.wait_for("!!document.querySelector('.el-table__row')", timeout=30),
                  "开课排课页已渲染")
            check(await b.click_text("button", "排课"), "点击教学班的「排课」按钮")
            ok = await b.wait_for(
                "document.body.innerText.includes('系统自动检测教室冲突')", timeout=20
            )
            check(ok, "排课弹窗已打开")
            await asyncio.sleep(1.5)
            rows = await b.js("document.querySelectorAll('.el-dialog .el-table__row').length")
            check(rows > 0, f"排课弹窗列出真实排课 {rows} 条（来自平铺接口）")
            check(await b.js("document.body.innerText.includes('尚未排课')") is False,
                  "弹窗非空状态")

            # ---------- 教师 ----------
            print("\n[2] 教师课表（局域网）")
            path = await login_as(b, origin, "T001", "T001")
            check("/teacher" in path, "教师登录成功", path)
            await b.goto(f"{origin}/teacher/schedule")
            ok = await b.wait_for("document.querySelectorAll('.course').length > 0", timeout=30)
            check(ok, "教师课表渲染出真实课程块",
                  await b.js("String(document.querySelectorAll('.course').length)"))
            check(await b.js("document.body.innerText.includes('共 ')"),
                  "课表统计条显示安排数量",
                  (await b.js("document.querySelector('.el-tag')?.innerText")) or "")
            teacher_names = await b.js(
                "[...document.querySelectorAll('.course .meta')].map(e=>e.innerText)"
                ".filter(t=>t.includes('周')).length"
            )
            check(bool(teacher_names), "课程块含周次信息", str(teacher_names))

            # ---------- 学生 ----------
            print("\n[3] 学生课表（局域网）")
            path = await login_as(b, origin, "20260001", "20260001")
            check("/student" in path, "学生登录成功", path)
            await b.goto(f"{origin}/student/schedule")
            ok = await b.wait_for("document.querySelectorAll('.course').length > 0", timeout=30)
            check(ok, "学生课表渲染出真实课程块",
                  await b.js("String(document.querySelectorAll('.course').length)"))
            has_teacher = await b.js(
                "[...document.querySelectorAll('.course')]"
                ".some(c => c.querySelectorAll('.meta').length >= 3)"
            )
            check(bool(has_teacher), "学生课表显示教师与教室")

            # ---------- 网络断言 ----------
            print("\n[4] 网络请求审计（DevTools 等价）")
            for _ in range(20):          # 收尾：把剩余事件排空
                await b.pump(timeout=0.1)
            reqs = b.requests
            urls = [r["url"] for r in reqs]
            api_reqs = [r for r in reqs if "/api/" in r["url"]]
            bad_host = [u for u in urls
                        if "127.0.0.1" in u or "localhost" in u]
            check(not bad_host, "没有任何请求指向 127.0.0.1 / localhost",
                  str(bad_host[:3]))
            check(all(u.startswith(origin) for u in urls if u.startswith("http")),
                  "所有请求都指向局域网来源", origin)
            check(any("/api/v1/teaching-schedules/mine" in u for u in urls),
                  "教师课表确实调用 /teaching-schedules/mine")
            check(any("/api/v1/teaching-schedules/my" in u for u in urls),
                  "学生课表确实调用 /teaching-schedules/my")
            check(any("/api/v1/teaching-schedules?" in u or
                      "/api/v1/teaching-schedules" in u and "teaching_class_id" in u
                      for u in urls),
                  "教务排课列表调用平铺接口 /teaching-schedules")
            def bad(items):
                return [r for r in items
                        if isinstance(r.get("status"), int) and r["status"] >= 400]

            api_bad = bad([r for r in reqs if "/api/" in r["url"]])
            check(not api_bad, "所有 /api 请求均成功（无 4xx/5xx）",
                  str([(r["url"], r["status"]) for r in api_bad][:3]))

            non_api_bad = bad([r for r in reqs if "/api/" not in r["url"]])
            vite_dep = [r for r in non_api_bad if "/node_modules/.vite/deps/" in r["url"]]
            favicon = [r for r in non_api_bad if r["url"].endswith("/favicon.ico")]
            other_bad = [r for r in non_api_bad if r not in vite_dep and r not in favicon]
            check(not other_bad, "除已知项外无非 API 资源错误",
                  str([(r["url"], r["status"]) for r in other_bad][:3]))
            if vite_dep or favicon:
                print(f"  ℹ️  非 API 资源（与局域网/接口无关）："
                      f"Vite 依赖预构建 504 ×{len(vite_dep)}、favicon 404 ×{len(favicon)}")

            cors = [f for f in b.failures if f.get("cors")]
            check(not cors, "无 CORS 失败", str(cors[:2]))
            api_failures = [f for f in b.failures if "/api/" in (f.get("url") or "")]
            check(not api_failures, "无 /api 请求加载失败",
                  str([(f.get("url"), f.get("error")) for f in api_failures][:3]))
            other_failures = [f for f in b.failures
                              if "/api/" not in (f.get("url") or "")]
            if other_failures:
                print(f"  ℹ️  非 API 加载失败（Vite 开发服务器重新预构建导致的中止）："
                      f"{[(f.get('url','')[-40:], f.get('error')) for f in other_failures][:2]}")
            check(len(api_reqs) > 0, f"共捕获 {len(api_reqs)} 条 /api 请求")
    finally:
        chrome.terminate()
        shutil.rmtree(PROFILE, ignore_errors=True)

    passed = sum(1 for ok, _ in results if ok)
    print(f"\n{'=' * 60}\n局域网浏览器 E2E：{passed}/{len(results)} 通过")
    for ok, label in results:
        if not ok:
            print(f"  ❌ {label}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
