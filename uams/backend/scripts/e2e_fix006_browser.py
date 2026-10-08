"""FIX-006 学期管理前端真实浏览器 E2E（Chrome + CDP）。

真实浏览器里点真实按钮：管理员登录 → 学期管理 → 读取真实学期 → 新增 →
刷新 → 激活 → 刷新 → 结束 → 刷新 → 非法重复结束 → 越权访问。

前置：
    uvicorn app.main:app --port 8000          # 前端 vite 代理指向 8000
    npm run dev                                # http://127.0.0.1:5173

用法：
    .venv/bin/python scripts/e2e_fix006_browser.py
"""

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND = "http://127.0.0.1:8000/api/v1"
FRONTEND = "http://127.0.0.1:5173"
CDP = "http://127.0.0.1:9222"
PROFILE = Path(tempfile.mkdtemp(prefix="uams_fix006_"))

# 演示数据中的进行中学期（seed_demo）：单激活约束要求测试期间临时降级
SEED_YEAR = "2026-2027"
SEED_SEM = 1

E2E_NAME = "FIX006-E2E-学期"
E2E_YEAR = "2999-3000"
E2E_SEM = 1

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    results.append((bool(cond), label))
    print(f"  {'✅' if cond else '❌'} {label}{(' — ' + detail) if detail else ''}")


def _db():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.db.session import SessionLocal
    return SessionLocal()


def _term_row(year: str, sem: int):
    from sqlalchemy import select

    from app.models.term import AcademicTerm

    with _db() as db:
        return db.execute(
            select(AcademicTerm).where(
                AcademicTerm.academic_year == year, AcademicTerm.semester == sem
            )
        ).scalar_one_or_none()


def _set_seed_active(active: bool) -> None:
    """临时把演示数据的进行中学期降级为 PLANNED（或恢复 ACTIVE）。

    与 `tests/test_academic_term.py::_set_seed_active` 同一手法：单激活约束下
    要让 E2E 学期可被激活，必须先把演示学期降级；结束是单向不可逆的，
    因此这里用 ORM 直接改状态做**测试装置的准备与还原**，被验证的操作本身
    全部走真实 API。
    """
    from sqlalchemy import select

    from app.models.term import AcademicTerm, TermStatus

    with _db() as db:
        t = db.execute(
            select(AcademicTerm).where(
                AcademicTerm.academic_year == SEED_YEAR,
                AcademicTerm.semester == SEED_SEM,
            )
        ).scalar_one_or_none()
        if t is not None:
            t.status = TermStatus.ACTIVE if active else TermStatus.PLANNED
            db.commit()


def _cleanup_e2e_terms() -> None:
    """删除历史遗留的 E2E 学期（无教学班才可删）。"""
    from sqlalchemy import delete

    from app.models.term import AcademicTerm

    with _db() as db:
        db.execute(delete(AcademicTerm).where(AcademicTerm.name.like("FIX006-E2E%")))
        db.commit()


class Browser:
    """极简 CDP 客户端：只实现本脚本需要的命令。"""

    def __init__(self, ws):
        self.ws = ws
        self._id = 0

    async def send(self, method: str, **params):
        self._id += 1
        msg_id = self._id
        await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
        while True:
            data = json.loads(await self.ws.recv())
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})

    async def js(self, expr: str):
        r = await self.send(
            "Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True
        )
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS 异常：{r['exceptionDetails'].get('text')}")
        return r.get("result", {}).get("value")

    async def goto(self, url: str):
        await self.send("Page.navigate", url=url)
        await self.wait_for("document.readyState === 'complete'", timeout=20)

    async def wait_for(self, expr: str, timeout: float = 15, interval: float = 0.2):
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

    async def click_row_button(self, row_text: str, button_text: str) -> bool:
        """在包含 row_text 的表格行内点击指定按钮。"""
        return await self.js(
            f"""(() => {{
              const row = [...document.querySelectorAll('.el-table__row')]
                .find(r => r.innerText.includes({json.dumps(row_text)}));
              if (!row) return false;
              const btn = [...row.querySelectorAll('button')]
                .find(b => b.textContent.includes({json.dumps(button_text)}));
              if (!btn) return false;
              btn.click(); return true;
            }})()"""
        )

    async def row_text(self, row_text: str) -> str:
        return await self.js(
            f"""(() => {{
              const row = [...document.querySelectorAll('.el-table__row')]
                .find(r => r.innerText.includes({json.dumps(row_text)}));
              return row ? row.innerText.replace(/\\s+/g, ' ') : 'ROW_NOT_FOUND';
            }})()"""
        )

    async def confirm_dialog(self, button_text: str) -> bool:
        """点击 ElMessageBox 的确认按钮（如「激活」「结束」「删除」）。"""
        await self.wait_for("!!document.querySelector('.el-message-box')", timeout=10)
        return await self.js(
            f"""(() => {{
              const btn = [...document.querySelectorAll('.el-message-box__btns button')]
                .find(b => b.textContent.includes({json.dumps(button_text)}));
              if (!btn) return false;
              btn.click(); return true;
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
  el.dispatchEvent(new Event('blur', { bubbles: true }));
  return true;
})(%s, %s)
"""


async def type_date(b: Browser, input_index: int, value: str) -> bool:
    """在第 input_index 个日期输入框里键入日期并触发 change。

    headless Chrome 下程序化点击不会展开 el-date-picker 面板，
    这里走 Element Plus 输入框自身的 change 解析路径（value-format=YYYY-MM-DD）。
    """
    ok = await b.js(
        f"""(() => {{
          const inputs = [...document.querySelectorAll('.el-date-editor input')];
          const el = inputs[{input_index}];
          if (!el) return false;
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, {json.dumps(value)});
          el.dispatchEvent(new Event('input', {{ bubbles: true }}));
          el.dispatchEvent(new Event('change', {{ bubbles: true }}));
          el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
          return true;
        }})()"""
    )
    await asyncio.sleep(0.3)
    return bool(ok) and bool(await b.js(
        f"document.querySelectorAll('.el-date-editor input')[{input_index}].value "
        f"=== {json.dumps(value)}"
    ))


def api_login(username: str, password: str) -> str:
    r = httpx.post(f"{BACKEND}/auth/login",
                   json={"username": username, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


async def main() -> int:
    _cleanup_e2e_terms()
    _set_seed_active(True)  # 确保起始状态 = 演示学期 ACTIVE

    chrome = subprocess.Popen(
        [
            "google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
            "--remote-debugging-port=9222", f"--user-data-dir={PROFILE / 'p'}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        targets = None
        for _ in range(60):
            try:
                targets = httpx.get(f"{CDP}/json/list", timeout=2).json()
                if targets:
                    break
            except Exception:
                await asyncio.sleep(0.5)
        if not targets:
            print("❌ 无法连接 Chrome CDP")
            return 1

        page = next(t for t in targets if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
            b = Browser(ws)
            await b.send("Page.enable")
            await b.send("DOM.enable")
            await b.send("Runtime.enable")

            # ---------- 1. 登录 + 进入学期管理 ----------
            print("\n[1] 管理员登录 → 学期管理")
            await b.goto(f"{FRONTEND}/login")
            check(await b.wait_for("document.querySelectorAll('input').length >= 2", timeout=30),
                  "登录页已渲染")
            await b.js(FILL_INPUT % ("'input:not([type=password])'", "'admin'"))
            await b.js(FILL_INPUT % ("'input[type=password]'", "'admin123'"))
            await b.click_text("button", "登 录")
            check(await b.wait_for("location.pathname.includes('/admin')", timeout=30),
                  "登录成功并跳转教务端", await b.js("location.pathname"))

            # 菜单入口（由路由 meta 动态生成）
            menu = await b.js(
                "[...document.querySelectorAll('.el-menu-item')].map(e=>e.innerText.trim())"
            )
            check("学期管理" in (menu or []), "教务端菜单出现「学期管理」", str(menu))

            await b.goto(f"{FRONTEND}/admin/terms")
            check(await b.wait_for("!!document.querySelector('.el-table__row')", timeout=30),
                  "学期管理页已渲染并读到真实学期")
            seeded = await b.row_text("2026-2027学年第一学期")
            check("2026-2027学年第一学期" in seeded, "列表中显示数据库已有学期", seeded)
            check("进行中" in seeded, "该学期状态来自后端（进行中）", seeded)

            # ---------- 1b. 筛选走真实后端（§七：不得前端假分页/假筛选） ----------
            print("\n[1b] 关键词筛选（真实请求）")
            total_before = await b.js("document.querySelectorAll('.el-table__row').length")
            await b.js(
                """(() => {
                  const el = [...document.querySelectorAll('.toolbar input')]
                    .find(i => (i.placeholder || '').includes('搜索学期'));
                  const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                  setter.call(el, '不存在的学期xyz');
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                })()"""
            )
            await b.click_text("button", "查询")
            await asyncio.sleep(1.2)
            empty = await b.js("document.querySelectorAll('.el-table__row').length")
            check(empty == 0, "关键词无匹配 → 表格为空（由后端过滤）",
                  f"before={total_before} after={empty}")
            check(await b.js("document.body.innerText.includes('暂无学期数据')"),
                  "空状态提示已展示")

            await b.js(
                """(() => {
                  const el = [...document.querySelectorAll('.toolbar input')]
                    .find(i => (i.placeholder || '').includes('搜索学期'));
                  const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                  setter.call(el, '');
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                })()"""
            )
            await b.click_text("button", "查询")
            await asyncio.sleep(1.2)
            back = await b.js("document.querySelectorAll('.el-table__row').length")
            check(back == total_before, "清空关键词后恢复全部行", str(back))

            # ---------- 2. 新增学期（真实表单） ----------
            print("\n[2] 新增学期")
            await b.click_text("button", "新增学期")
            check(await b.wait_for("!!document.querySelector('.el-dialog')", timeout=10),
                  "新增弹窗已打开")
            await b.js(FILL_INPUT % ("'.el-dialog input[maxlength=\"50\"]'", f"'{E2E_NAME}'"))
            await b.js(FILL_INPUT % ("'.el-dialog input[maxlength=\"9\"]'", f"'{E2E_YEAR}'"))
            await b.click_text(".el-dialog .el-radio", "第一学期")
            check(await type_date(b, 0, "2999-09-01"), "填写开始日期 2999-09-01")
            check(await type_date(b, 1, "3000-01-15"), "填写结束日期 3000-01-15")
            await b.click_text(".el-dialog__footer button", "确定")
            await asyncio.sleep(1.5)
            check(await b.js(f"document.body.innerText.includes({json.dumps(E2E_NAME)})"),
                  "新增后列表出现该学期")
            row = _term_row(E2E_YEAR, E2E_SEM)
            check(row is not None, "MySQL：academic_terms 新增记录")
            if row:
                check(row.status == "PLANNED", "MySQL：新学期待激活状态", row.status)
                check(str(row.start_date) < str(row.end_date),
                      "MySQL：起止日期已落库", f"{row.start_date} ~ {row.end_date}")

            # 刷新页面后仍存在（状态来自服务器，不是前端缓存）
            await b.goto(f"{FRONTEND}/admin/terms")
            check(await b.wait_for(f"document.body.innerText.includes({json.dumps(E2E_NAME)})",
                                   timeout=30),
                  "刷新页面后测试学期仍存在")

            # ---------- 3. 非法操作：已存在进行中时激活 ----------
            print("\n[3] 非法操作：单激活约束")
            check(await b.click_row_button(E2E_NAME, "激活"), "点击测试学期的「激活」")
            check(await b.confirm_dialog("激活"), "二次确认已点击")
            await asyncio.sleep(1.5)
            err = await b.js(
                "[...document.querySelectorAll('.el-message')].map(e=>e.innerText).join(' | ')"
            )
            check("进行中" in (err or ""), "后端拒绝并给出明确提示", err)
            row = _term_row(E2E_YEAR, E2E_SEM)
            check(row is not None and row.status == "PLANNED",
                  "MySQL：被拒绝后状态未变", row.status if row else "?")

            # ---------- 4. 激活（先临时降级演示学期） ----------
            print("\n[4] 激活学期")
            _set_seed_active(False)
            await b.goto(f"{FRONTEND}/admin/terms")
            await b.wait_for(f"document.body.innerText.includes({json.dumps(E2E_NAME)})", timeout=30)
            check(await b.click_row_button(E2E_NAME, "激活"), "点击「激活」")
            check(await b.confirm_dialog("激活"), "弹出并确认「激活学期」二次确认")
            await asyncio.sleep(1.5)
            row = _term_row(E2E_YEAR, E2E_SEM)
            check(row is not None and row.status == "ACTIVE", "MySQL：状态变为 ACTIVE",
                  row.status if row else "?")

            await b.goto(f"{FRONTEND}/admin/terms")
            await b.wait_for(f"document.body.innerText.includes({json.dumps(E2E_NAME)})", timeout=30)
            row_text = await b.row_text(E2E_NAME)
            check("进行中" in row_text, "刷新后页面显示「进行中」", row_text)
            check(await b.js("document.body.innerText.includes('当前激活学期：FIX006-E2E')"),
                  "页面顶部「当前激活学期」同步为测试学期")

            # ---------- 5. 结束学期 ----------
            print("\n[5] 结束学期")
            check(await b.click_row_button(E2E_NAME, "结束"), "点击「结束」")
            check(await b.confirm_dialog("结束"), "弹出并确认「结束学期」二次确认")
            await asyncio.sleep(1.5)
            row = _term_row(E2E_YEAR, E2E_SEM)
            check(row is not None and row.status == "ENDED", "MySQL：状态变为 ENDED",
                  row.status if row else "?")
            await b.goto(f"{FRONTEND}/admin/terms")
            await b.wait_for(f"document.body.innerText.includes({json.dumps(E2E_NAME)})", timeout=30)
            row_text = await b.row_text(E2E_NAME)
            check("已结束" in row_text, "刷新后页面显示「已结束」", row_text)
            check("结束" not in row_text.split("已结束")[-1],
                  "已结束学期不再显示「结束」按钮（状态机由后端决定）", row_text)

            # ---------- 6. 非法重复结束（后端必须拒绝） ----------
            print("\n[6] 非法操作：重复结束")
            tok = api_login("admin", "admin123")
            r = httpx.post(f"{BACKEND}/terms/{row.id}/end",
                           headers={"Authorization": f"Bearer {tok}"}, timeout=20)
            check(r.status_code == 409 and "进行中" in r.json()["message"],
                  "已结束学期再次结束 → 后端 409", f"{r.status_code} {r.json().get('message')}")
            r2 = httpx.post(f"{BACKEND}/terms/{row.id}/activate",
                            headers={"Authorization": f"Bearer {tok}"}, timeout=20)
            check(r2.status_code == 409 and "已结束" in r2.json()["message"],
                  "已结束学期不可再激活 → 后端 409", f"{r2.status_code} {r2.json().get('message')}")

            # ---------- 7. 越权 ----------
            print("\n[7] 权限")
            for uname, pwd, label in (("T001", "T001", "教师"), ("20260001", "20260001", "学生")):
                await b.js("localStorage.clear()")
                await b.goto(f"{FRONTEND}/login")
                await b.wait_for("document.querySelectorAll('input').length >= 2", timeout=30)
                await b.js(FILL_INPUT % ("'input:not([type=password])'", f"'{uname}'"))
                await b.js(FILL_INPUT % ("'input[type=password]'", f"'{pwd}'"))
                await b.click_text("button", "登 录")
                await b.wait_for("location.pathname.includes('/teacher') || "
                                 "location.pathname.includes('/student')", timeout=30)
                await b.goto(f"{FRONTEND}/admin/terms")
                ok = await b.wait_for("location.pathname === '/403'", timeout=15)
                check(ok, f"{label}访问 /admin/terms 被挡到 403",
                      await b.js("location.pathname"))
                menus = await b.js(
                    "[...document.querySelectorAll('.el-menu-item')].map(e=>e.innerText.trim())"
                )
                check("学期管理" not in (menus or []), f"{label}端不显示「学期管理」菜单",
                      str(menus))
                # 真实 API 权限：写接口必须 403
                t = api_login(uname, pwd)
                w = httpx.post(f"{BACKEND}/terms/{row.id}/activate",
                               headers={"Authorization": f"Bearer {t}"}, timeout=20)
                check(w.status_code == 403, f"{label}调用 activate 接口 → 403",
                      str(w.status_code))

            # ---------- 8. 清理 E2E 数据 ----------
            print("\n[8] 清理")
            await b.js("localStorage.clear()")
            await b.goto(f"{FRONTEND}/login")
            await b.wait_for("document.querySelectorAll('input').length >= 2", timeout=30)
            await b.js(FILL_INPUT % ("'input:not([type=password])'", "'admin'"))
            await b.js(FILL_INPUT % ("'input[type=password]'", "'admin123'"))
            await b.click_text("button", "登 录")
            await b.wait_for("location.pathname.includes('/admin')", timeout=30)
            await b.goto(f"{FRONTEND}/admin/terms")
            await b.wait_for(f"document.body.innerText.includes({json.dumps(E2E_NAME)})", timeout=30)
            check(await b.click_row_button(E2E_NAME, "删除"), "点击「删除」")
            # 删除确认由 useCrudTable 统一发起，按钮文案是 MessageBox 默认的「确定」
            check(await b.confirm_dialog("确定"), "确认删除")
            await asyncio.sleep(1.5)
            check(_term_row(E2E_YEAR, E2E_SEM) is None, "MySQL：E2E 学期已清理")
            check(not await b.js(
                f"document.body.innerText.includes({json.dumps(E2E_NAME)})"
            ), "列表刷新后不再显示已删除学期")

            print(f"\n{'=' * 60}\n浏览器 E2E："
                  f"{sum(1 for ok, _ in results if ok)}/{len(results)} 通过")
            for ok, label in results:
                if not ok:
                    print(f"  ❌ {label}")
            return 0 if all(ok for ok, _ in results) else 1
    finally:
        chrome.terminate()
        shutil.rmtree(PROFILE, ignore_errors=True)
        _cleanup_e2e_terms()
        _set_seed_active(True)  # 还原演示数据的 ACTIVE 学期


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
