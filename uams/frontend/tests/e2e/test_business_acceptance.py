#!/usr/bin/env python3
"""FIX-BUSINESS-001 浏览器验收（Chrome/CDP，仅 uams_test）。

覆盖：学生学院级联、批量删除与关联保护、四类模板下载与导入、
三字段登录（含初始 admin / 教师兼任管理员 / 负向用例）、
无 F5 数据刷新，并检查 Console 异常与 Network 5xx。

前置：按 README 启动 8010 测试后端与 5180 前端，并先执行
`/tmp/uams_e2e_prep.py`（或按 README 准备 fixtures）。
"""
import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import urlparse

API = os.environ.get("UAMS_E2E_API", "http://127.0.0.1:8010/api/v1")
FRONT = os.environ.get("UAMS_E2E_FRONT", "http://127.0.0.1:5180")
PORT = int(os.environ.get("UAMS_E2E_CDP_PORT", "9241"))
FIXTURES = Path(os.environ.get("UAMS_E2E_FIXTURES", "/tmp/uams-e2e"))
META = json.loads((FIXTURES / "meta.json").read_text(encoding="utf-8"))
DOWNLOAD = Path("/tmp/uams-e2e-downloads")
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

failures: list[str] = []


def check(cond, label, detail=""):
    print(("PASS " if cond else "FAIL ") + label + (f" :: {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)
    return cond


def ensure_test_environment():
    base = API.rsplit("/api/v1", 1)[0]
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as x:
            health = json.loads(x.read().decode())
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"无法连接隔离测试后端 {base}/health：{exc}")
    if health.get("env") != "testing":
        raise SystemExit(f"拒绝执行：目标环境不是 testing（env={health.get('env')}）")


def api(path, tok=None, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    try:
        with urllib.request.urlopen(req, timeout=20) as x:
            raw = x.read().decode()
            return x.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return e.code, raw


# ---------------- CDP ----------------


def wsc(url):
    u = urlparse(url)
    s = socket.create_connection((u.hostname, u.port), timeout=15)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(
        (f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
         "Upgrade: websocket\r\nConnection: Upgrade\r\n"
         f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode()
    )
    if b"101" not in s.recv(4096):
        raise RuntimeError("websocket upgrade failed")
    return s


def send(s, payload, op=1):
    b = payload.encode()
    mask = os.urandom(4)
    n = len(b)
    h = bytes([0x80 | op])
    if n < 126:
        h += bytes([0x80 | n])
    elif n < 65536:
        h += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        h += bytes([0x80 | 127]) + struct.pack(">Q", n)
    s.sendall(h + mask + bytes(x ^ mask[i % 4] for i, x in enumerate(b)))


def recv(s):
    h = s.recv(2)
    op = h[0] & 15
    n = h[1] & 127
    if n == 126:
        n = struct.unpack(">H", s.recv(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", s.recv(8))[0]
    d = b""
    while len(d) < n:
        d += s.recv(n - len(d))
    if op == 9:
        send(s, d, 10)
        return recv(s)
    return op, d


class C:
    def __init__(self, ws):
        self.w = ws
        self.i = 0
        self.events: list[dict] = []

    def call(self, method, params=None, timeout=30):
        self.i += 1
        mid = self.i
        send(self.w, json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            op, d = recv(self.w)
            if op != 1:
                continue
            msg = json.loads(d)
            if msg.get("id") == mid:
                return msg
            if "method" in msg:
                self.events.append(msg)
        raise TimeoutError(method)

    def ev(self, expr, awaitp=False):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": awaitp})
        return r.get("result", {}).get("result", {}).get("value")


def target():
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as x:
        return json.loads(x.read().decode())["webSocketDebuggerUrl"]


HELPERS = r"""
window.__e2e = {
  vis: (el) => !!el && el.getClientRects().length > 0 &&
    getComputedStyle(el).visibility !== 'hidden',
  set: (el, val) => {
    if (!el) return false;
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  },
  byLabel: (label) => {
    const items = [...document.querySelectorAll('.el-form-item')];
    const it = items.find(i =>
      (i.querySelector('.el-form-item__label')?.innerText || '').trim().startsWith(label));
    return it?.querySelector('input,textarea') || null;
  },
  fill: (label, val) => window.__e2e.set(window.__e2e.byLabel(label), val),
  setInputs: (values) => {
    const els = [...document.querySelectorAll('.form input')];
    values.forEach((v, i) => window.__e2e.set(els[i], v));
    return els.length;
  },
  clickText: (text, root = document) => {
    const els = [...root.querySelectorAll('button,a,.el-tabs__item,.el-select-dropdown__item')]
      .filter(e => window.__e2e.vis(e));
    const e = els.find(x => (x.innerText || '').trim() === text)
      || els.find(x => (x.innerText || '').trim().includes(text));
    if (e) { e.click(); return (e.innerText || '').trim(); }
    return '';
  },
  currentDropdown: () => {
    const dds = [...document.querySelectorAll('.el-select-dropdown')].filter(d => {
      const p = d.closest('.el-popper');
      const pv = !p || (getComputedStyle(p).display !== 'none' &&
        getComputedStyle(p).visibility !== 'hidden');
      return d.getClientRects().length > 0 && getComputedStyle(d).display !== 'none' && pv;
    });
    return dds[dds.length - 1] || null;
  },
  options: () => {
    const d = window.__e2e.currentDropdown();
    return d ? [...d.querySelectorAll('.el-select-dropdown__item')]
      .map(e => (e.innerText || '').trim()) : [];
  },
  clickOption: (text) => {
    const d = window.__e2e.currentDropdown();
    const items = d ? [...d.querySelectorAll('.el-select-dropdown__item')] : [];
    const e = items.find(x => (x.innerText || '').trim() === text)
      || items.find(x => (x.innerText || '').trim().includes(text));
    if (e) { e.click(); return (e.innerText || '').trim(); }
    return '';
  },
  openSelect: (i, root = '.el-dialog') => {
    const s = document.querySelectorAll(root + ' .el-select')[i];
    if (!s) return false;
    (s.querySelector('.el-select__wrapper') || s.querySelector('input')).click();
    return true;
  },
  selectValue: (i, root = '.el-dialog') => {
    const s = document.querySelectorAll(root + ' .el-select')[i];
    if (!s) return '';
    const item = s.querySelector('.el-select__placeholder')
      || s.querySelector('.el-select__selected-item');
    if (item && (item.innerText || '').trim()) return item.innerText.trim();
    const inp = s.querySelector('input');
    return inp ? inp.value : '';
  },
  selectDisabled: (i, root = '.el-dialog') => {
    const s = document.querySelectorAll(root + ' .el-select')[i];
    if (!s) return null;
    const wrap = s.querySelector('.el-select__wrapper');
    const inp = s.querySelector('input');
    return s.classList.contains('is-disabled')
      || !!wrap?.classList.contains('is-disabled') || !!inp?.disabled;
  },
  rowByText: (text, root = '.el-table__row') => {
    return [...document.querySelectorAll(root)].find(r => (r.innerText || '').includes(text)) || null;
  },
  checkRow: (text, root = '.el-table__row') => {
    const r = [...document.querySelectorAll(root)].find(x => (x.innerText || '').includes(text));
    if (!r) return false;
    const cb = r.querySelector('.el-checkbox');
    if (cb) cb.click();
    return !!cb;
  },
  clickRowButton: (text, button, root = '.el-table__row') => {
    const r = [...document.querySelectorAll(root)].find(x => (x.innerText || '').includes(text));
    if (!r) return false;
    const b = [...r.querySelectorAll('button')].find(x => (x.innerText || '').trim() === button);
    if (b) b.click();
    return !!b;
  },
  confirm: (labels) => {
    const b = [...document.querySelectorAll('.el-message-box__btns button')]
      .find(x => labels.some(l => (x.innerText || '').trim().includes(l)));
    if (b) { b.click(); return true; }
    return false;
  },
  stats: () => [...document.querySelectorAll('.result-stats .rstat__value')]
    .map(e => (e.innerText || '').trim()),
};
"""


def wait(c, expr, timeout=10, interval=0.25):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if c.ev(expr):
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(interval)
    return False


def nav(c, path, timeout=12):
    c.call("Page.navigate", {"url": FRONT + path})
    wait(c, "document.readyState === 'complete'", timeout)
    time.sleep(1.2)
    c.ev(HELPERS)


def body_has(c, text):
    return bool(c.ev(f"document.body.innerText.includes({json.dumps(text)})"))


def login_ui(c, username, real_name, password):
    c.ev("localStorage.clear()")
    nav(c, "/login")
    wait(c, "document.querySelectorAll('.form input').length >= 3")
    c.ev(f"window.__e2e.setInputs({json.dumps([username, real_name, password])})")
    c.ev("window.__e2e.clickText('登 录') || window.__e2e.clickText('登录')")
    if real_name and password:
        wait(c, "location.pathname !== '/login' || !!document.querySelector('.login-error')", 12)
    else:
        wait(c, "!!document.querySelector('.login-error')", 8)
    return c.ev("location.pathname"), c.ev(
        "document.querySelector('.login-error')?.innerText || ''")


def console_errors(c):
    errs = []
    for e in c.events:
        m = e.get("method")
        p = e.get("params", {})
        if m == "Runtime.exceptionThrown":
            errs.append(str(p.get("exceptionDetails", {}).get("text", "exception")))
        elif m == "Runtime.consoleAPICalled" and p.get("type") == "error":
            txt = " ".join(str(a.get("value", "")) for a in p.get("args", []))
            errs.append(txt[:200])
    return errs


def bad_network(c):
    bad = []
    for e in c.events:
        if e.get("method") == "Network.responseReceived":
            r = e.get("params", {}).get("response", {})
            if int(r.get("status", 0)) >= 500:
                bad.append(f"{r.get('status')} {r.get('url', '')[:120]}")
    return bad


# ---------------- fixtures ----------------


def api_login(username="admin", real_name="admin", password="admin123"):
    st, b = api("/auth/login", method="POST",
                body={"username": username, "real_name": real_name, "password": password})
    assert st == 200, (st, b)
    return b["access_token"]


def purge(endpoint, keyword, tok):
    st, page = api(f"{endpoint}?page_size=100&keyword={keyword}", tok)
    if st == 200 and page:
        for item in page.get("items", []):
            api(f"{endpoint}/{item['id']}", tok, "DELETE")


def xlsx_first_row(path):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        row = sheet.find(f"{NS}sheetData/{NS}row")
        vals = []
        for cell in row.findall(NS + "c"):
            if cell.get("t") == "s":
                vals.append(shared[int(cell.find(NS + "v").text)])
            elif cell.get("t") == "inlineStr":
                vals.append("".join(t.text or "" for t in cell.iter(NS + "t")))
            else:
                v = cell.find(NS + "v")
                vals.append(v.text if v is not None else "")
        return vals


def newest_download(before: set[Path], timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        now = set(DOWNLOAD.iterdir()) if DOWNLOAD.exists() else set()
        new = [p for p in now - before if p.suffix.lower() == ".xlsx" and p.stat().st_size > 0]
        if new:
            time.sleep(0.4)  # 等文件写完
            return max(new, key=lambda p: p.stat().st_mtime)
        time.sleep(0.25)
    return None


# ---------------- scenarios ----------------


def main():
    ensure_test_environment()
    tok = api_login()
    meta = META
    no = "E2EACC_U1"
    no2 = "E2EACC_U1改"
    try:
        shutil.rmtree(DOWNLOAD, ignore_errors=True)
        DOWNLOAD.mkdir(parents=True, exist_ok=True)
        # 清理上次遗留
        purge("/students", "E2EACC", tok)
        purge("/teachers", "E2EACC", tok)
        purge("/courses", "E2EACC", tok)

        ch = subprocess.Popen(
            ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
             "--disable-dev-shm-usage", "--no-first-run",
             f"--remote-debugging-port={PORT}",
             "--user-data-dir=/tmp/chrome-e2e-accept", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(60):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.2)
            w = wsc(target())
            c = C(w)
            for domain in ("Page", "Runtime", "Network", "DOM"):
                c.call(domain + ".enable")
            c.call("Browser.setDownloadBehavior",
                   {"behavior": "allow", "downloadPath": str(DOWNLOAD),
                    "eventsEnabled": True})

            # ---------- 登录负向 ----------
            path, err = login_ui(c, "admin", "", "admin123")
            check("请输入用户名、个人姓名和密码" in err, "LOGIN-1 缺少姓名被前端拒绝", err)
            path, err = login_ui(c, "admin", "__WRONG_NAME__", "admin123")
            check(path == "/login" and "用户名、姓名或密码错误" in err,
                  "LOGIN-2 错误姓名被拒绝", f"{path} {err}")
            path, err = login_ui(c, "admin", "admin", "__WRONG_PW__")
            check(path == "/login" and "用户名、姓名或密码错误" in err,
                  "LOGIN-3 错误密码被拒绝", f"{path} {err}")

            # ---------- 初始 admin 兼容（admin / 系统管理员） ----------
            path, err = login_ui(c, "admin", "admin", "admin123")
            check(path == "/admin/dashboard" and "学生管理" in c.ev("document.body.innerText"),
                  "LOGIN-4 初始 admin 姓名 admin 登录", f"{path} {err}")
            st, me = api("/auth/me", tok)
            path, err = login_ui(c, "admin", me["user"]["real_name"], "admin123")
            check(path == "/admin/dashboard", "LOGIN-5 初始 admin 历史姓名登录", f"{path} {err}")

            # ---------- 教师 / 学生三字段登录与导航 ----------
            st, page = api("/users?page_size=100&keyword=T001", tok)
            teacher_name = [u for u in page["items"] if u["username"] == "T001"][0]["real_name"]
            path, err = login_ui(c, "T001", teacher_name, "T001")
            check(path == "/teacher/dashboard", "LOGIN-6 教师三字段登录", f"{path} {err}")
            check("批量导入" not in c.ev("document.body.innerText"),
                  "LOGIN-7 教师菜单不含教务管理项")

            st, page = api("/users?page_size=100&keyword=20260001", tok)
            student_name = [u for u in page["items"] if u["username"] == "20260001"][0]["real_name"]
            path, err = login_ui(c, "20260001", student_name, "20260001")
            check(path == "/student/dashboard", "LOGIN-8 学生三字段登录", f"{path} {err}")
            check("批量导入" not in c.ev("document.body.innerText"),
                  "LOGIN-9 学生菜单不含教务管理项")

            # ---------- 教师兼任管理员 ----------
            st, users = api("/users?page_size=100&keyword=T001", tok)
            tid = [u for u in users["items"] if u["username"] == "T001"][0]["id"]
            st, _ = api(f"/admins/{tid}/grant", tok, "POST")
            try:
                path, err = login_ui(c, "T001", teacher_name, "T001")
                me_roles = c.ev(
                    "fetch('/api/v1/auth/me',{headers:{Authorization:'Bearer '+"
                    "localStorage.getItem('uams_token')}}).then(r=>r.json()).then(d=>d.roles)",
                    awaitp=True,
                )
                check(path in ("/teacher/dashboard", "/admin/dashboard")
                      and "ACADEMIC_ADMIN" in (me_roles or []),
                      "LOGIN-10 教师兼任管理员同账号登录", f"{path} {me_roles} {err}")
                check("学生管理" in c.ev("document.body.innerText")
                      or path == "/teacher/dashboard",
                      "LOGIN-11 兼任管理员身份可用")
            finally:
                api(f"/admins/{tid}/revoke", tok, "POST")

            # ---------- 学生学院级联（无 F5） ----------
            path, err = login_ui(c, "admin", "admin", "admin123")
            nav(c, "/admin/students")
            check(wait(c, "!!document.querySelector('.el-table__row')"), "UI-1 学生列表加载")
            c.ev("window.__e2eAlive = 'student-page'")
            c.ev("window.__e2e.clickText('新增学生')")
            wait(c, "!!document.querySelector('.el-dialog')")
            c.ev(f"window.__e2e.fill('学号',{json.dumps(no)});"
                 f"window.__e2e.fill('姓名',{json.dumps(no2)})")
            check(c.ev("window.__e2e.selectDisabled(1)") is True
                  and c.ev("window.__e2e.selectDisabled(2)") is True,
                  "UI-2 未选学院时专业/班级禁用")
            c.ev("window.__e2e.openSelect(0)")
            wait(c, "window.__e2e.options().length > 0")
            college_name = meta["college"]["name"]
            c.ev(f"window.__e2e.clickOption({json.dumps(college_name)})")
            wait(c, "window.__e2e.selectDisabled(1) === false")
            c.ev("window.__e2e.openSelect(1)")
            wait(c, "window.__e2e.options().length > 0")
            major_opts = c.ev("window.__e2e.options()") or []
            check(set(major_opts) == set(meta["majors"]),
                  "UI-3 专业列表按学院过滤", str(major_opts))
            c.ev(f"window.__e2e.clickOption({json.dumps(meta['major']['name'])})")
            wait(c, "window.__e2e.selectDisabled(2) === false")
            c.ev("window.__e2e.openSelect(2)")
            wait(c, "window.__e2e.options().length > 0")
            class_opts = c.ev("window.__e2e.options()") or []
            check(set(class_opts) == set(meta["classes"]),
                  "UI-4 班级列表按专业过滤", str(class_opts))
            c.ev(f"window.__e2e.clickOption({json.dumps(meta['class']['name'])})")
            c.ev("window.__e2e.clickText('确定', document.querySelector('.el-dialog'))")
            check(wait(c, f"document.body.innerText.includes({json.dumps(no)})", 12),
                  "UI-5 新增学生无需 F5 可见")
            check(c.ev("window.__e2eAlive") == "student-page", "UI-6 新增未触发整页刷新")

            # 编辑：级联回显 + 姓名更新
            c.ev(f"window.__e2e.clickRowButton({json.dumps(no)},'编辑')")
            wait(c, "!!document.querySelector('.el-dialog')")
            check(c.ev(f"window.__e2e.selectValue(0)") == college_name
                  and c.ev(f"window.__e2e.selectValue(1)") == meta["major"]["name"]
                  and c.ev(f"window.__e2e.selectValue(2)") == meta["class"]["name"],
                  "UI-7 编辑时学院/专业/班级正确回显")
            c.ev(f"window.__e2e.fill('姓名',{json.dumps(no2 + '乙')})")
            c.ev("window.__e2e.clickText('确定', document.querySelector('.el-dialog'))")
            check(wait(c, f"document.body.innerText.includes({json.dumps(no2 + '乙')})", 12),
                  "UI-8 编辑学生无需 F5 可见")
            check(c.ev("window.__e2eAlive") == "student-page", "UI-9 编辑未触发整页刷新")
            c.ev(f"window.__e2e.clickRowButton({json.dumps(no)},'删除')")
            wait(c, "!!document.querySelector('.el-message-box')")
            c.ev("window.__e2e.confirm(['确定','删除'])")
            check(wait(c, f"!document.body.innerText.includes({json.dumps(no)})", 12),
                  "UI-10 删除学生无需 F5 消失")

            # ---------- 批量删除（成功 + 关联保护） ----------
            for sno, name in (("E2EACCB1", "批量一"), ("E2EACCB2", "批量二")):
                api("/students", tok, "POST", {
                    "student_no": sno, "real_name": name,
                    "class_id": meta["class"]["id"], "enrollment_year": 2026})
            nav(c, "/admin/students")
            wait(c, "!!document.querySelector('.el-table__row')")
            c.ev("window.__e2e.set(document.querySelector("
                 "\"input[placeholder='搜索学号或姓名']\"),'E2EACCB')")
            c.ev("window.__e2e.clickText('查询')")
            wait(c, "document.querySelectorAll('.el-table__row').length === 2")
            c.ev("window.__e2e.checkRow('E2EACCB1');window.__e2e.checkRow('E2EACCB2')")
            time.sleep(0.5)
            c.ev("window.__e2e.clickText('批量删除')")
            wait(c, "!!document.querySelector('.el-message-box')")
            c.ev("window.__e2e.confirm(['删除'])")
            check(wait(c, "document.body.innerText.includes('已删除 2 条')", 12),
                  "BATCH-1 学生批量删除成功反馈")
            check(wait(c, "!document.body.innerText.includes('E2EACCB1')", 12),
                  "BATCH-2 批量删除后无需 F5 消失")

            protected_no = meta["protected_student_no"]
            c.ev("window.__e2e.set(document.querySelector("
                 "\"input[placeholder='搜索学号或姓名']\"),%s)" % json.dumps(protected_no))
            c.ev("window.__e2e.clickText('查询')")
            wait(c, f"document.body.innerText.includes({json.dumps(protected_no)})")
            c.ev(f"window.__e2e.checkRow({json.dumps(protected_no)})")
            c.ev("window.__e2e.clickText('批量删除')")
            wait(c, "!!document.querySelector('.el-message-box')")
            c.ev("window.__e2e.confirm(['删除'])")
            check(wait(c, "document.body.innerText.includes('失败 1 条')", 12),
                  "BATCH-3 有选课学生被拒绝")
            check(body_has(c, protected_no), "BATCH-4 受保护学生仍保留")

            # 课程批量删除
            for code in ("E2EACCB_C1", "E2EACCB_C2"):
                st, _ = api("/courses", tok, "POST", {
                    "code": code, "name": "批量课程", "college_id": meta["college"]["id"],
                    "course_type": "ELECTIVE", "credits": 2, "total_hours": 32,
                    "theory_hours": 32, "practice_hours": 0})
                assert st == 201, (st, _)
            nav(c, "/admin/courses")
            wait(c, "!!document.querySelector('.el-table__row')")
            c.ev("window.__e2e.set(document.querySelector("
                 "\"input[placeholder='课程代码或名称']\"),'E2EACCB')")
            c.ev("window.__e2e.clickText('查询')")
            wait(c, "document.querySelectorAll('.el-table__row').length === 2")
            c.ev("window.__e2e.checkRow('E2EACCB_C1');window.__e2e.checkRow('E2EACCB_C2')")
            c.ev("window.__e2e.clickText('批量删除')")
            wait(c, "!!document.querySelector('.el-message-box')")
            c.ev("window.__e2e.confirm(['删除'])")
            check(wait(c, "document.body.innerText.includes('已删除 2 条')", 12),
                  "BATCH-5 课程批量删除成功反馈")

            pcode = meta["protected_course_code"]
            c.ev("window.__e2e.set(document.querySelector("
                 "\"input[placeholder='课程代码或名称']\"),%s)" % json.dumps(pcode))
            c.ev("window.__e2e.clickText('查询')")
            wait(c, f"document.body.innerText.includes({json.dumps(pcode)})")
            c.ev(f"window.__e2e.checkRow({json.dumps(pcode)})")
            c.ev("window.__e2e.clickText('批量删除')")
            wait(c, "!!document.querySelector('.el-message-box')")
            c.ev("window.__e2e.confirm(['删除'])")
            check(wait(c, "document.body.innerText.includes('失败 1 条')", 12),
                  "BATCH-6 有教学任务课程被拒绝")

            # 教学班名单批量移除（有成绩拒绝）
            nav(c, "/admin/selection")
            time.sleep(1.0)
            check(wait(c, f"document.body.innerText.includes({json.dumps(meta['graded_class']['code'])})", 12),
                  "SELECT-1 教学班列表加载")
            c.ev(f"window.__e2e.clickRowButton({json.dumps(meta['graded_class']['code'])},'名单')")
            wait(c, "!!document.querySelector('.el-dialog .el-table__row')")
            gno = meta["graded_class"]["student_no"]
            check(c.ev(f"window.__e2e.checkRow({json.dumps(gno)},'.el-dialog .el-table__row')"),
                  "SELECT-2 勾选有成绩学生")
            c.ev("window.__e2e.clickText('批量移除学生')")
            wait(c, "!!document.querySelector('.el-message-box')")
            c.ev("window.__e2e.confirm(['移除'])")
            check(wait(c, "document.body.innerText.includes('失败 1 人')", 12),
                  "SELECT-3 有成绩学生拒绝移除")
            check(c.ev(f"[...document.querySelectorAll('.el-dialog .el-table__row')]"
                       f".some(r=>r.innerText.includes({json.dumps(gno)}))"),
                  "SELECT-4 名单中该学生仍保留")
            c.ev("window.__e2e.clickText('关闭',document.querySelector('.el-dialog'))")

            # ---------- 四类模板下载 ----------
            nav(c, "/admin/imports")
            expect = {
                "学生导入": ["学号", "姓名", "登录名", "性别", "学院", "专业", "行政班",
                            "入学年份", "出生日期", "邮箱", "手机"],
                "教师导入": ["工号", "姓名", "学院", "职称", "性别", "入职日期", "邮箱", "联系电话"],
                "课程导入": ["课程代码", "课程名称", "学院", "学分", "总学时",
                            "理论学时", "实践学时", "课程性质", "考核形式", "课程简介", "状态"],
                "成绩导入": ["学号", "姓名", "班级", "课程代码", "课程名称", "教学班",
                            "平时成绩", "期末成绩"],
            }
            for tab, cols in expect.items():
                c.ev(f"window.__e2e.clickText({json.dumps(tab)})")
                time.sleep(0.6)
                if tab == "成绩导入":
                    c.ev("window.__e2e.openSelect(0, '.flow')")
                    wait(c, "window.__e2e.options().length > 0")
                    c.ev(f"window.__e2e.clickOption({json.dumps(meta['tclass']['code'])})")
                    time.sleep(0.4)
                before = set(DOWNLOAD.iterdir())
                c.ev("window.__e2e.clickText('下载模板')")
                f = newest_download(before)
                if check(f is not None, f"TPL-{tab} 下载成功"):
                    hdr = xlsx_first_row(f)
                    check(all(x in hdr for x in cols), f"TPL-{tab} 字段完整",
                          f"missing={[x for x in cols if x not in hdr]}")

            # ---------- 合法 / 非法导入 ----------
            def set_file(c, path):
                doc = c.call("DOM.getDocument", {"depth": 2})
                node = c.call("DOM.querySelector", {
                    "nodeId": doc["result"]["root"]["nodeId"],
                    "selector": ".el-upload input[type=file]"})
                nid = node["result"]["nodeId"]
                assert nid, "file input not found"
                c.call("DOM.setFileInputFiles", {"files": [str(path)], "nodeId": nid})

            def run_import(c, tab, file_key, exp_success, exp_failed):
                # 先切到另一个类型再切回，确保结果卡片与已选文件被重置
                other = "教师导入" if tab != "教师导入" else "学生导入"
                c.ev(f"window.__e2e.clickText({json.dumps(other)})")
                time.sleep(0.4)
                c.ev(f"window.__e2e.clickText({json.dumps(tab)})")
                time.sleep(0.6)
                set_file(c, meta["files"][file_key])
                time.sleep(0.4)
                c.ev("window.__e2e.clickText('开始导入')")
                ok = wait(c, "!!document.querySelector('.result-stats')", 20)
                stats = c.ev("window.__e2e.stats()") or []
                check(ok and stats[:3] == [str(1), str(exp_success), str(exp_failed)],
                      f"IMP-{tab}-{file_key}", str(stats))
                time.sleep(0.5)

            run_import(c, "学生导入", "students-ok", 1, 0)
            run_import(c, "学生导入", "students-bad", 0, 1)
            run_import(c, "教师导入", "teachers-ok", 1, 0)
            run_import(c, "教师导入", "teachers-bad", 0, 1)
            run_import(c, "课程导入", "courses-ok", 1, 0)
            run_import(c, "课程导入", "courses-bad", 0, 1)
            run_import(c, "成绩导入", "grades-ok", 1, 0)
            run_import(c, "成绩导入", "grades-bad", 0, 1)

            # ---------- Console / Network ----------
            errs = console_errors(c)
            bad = bad_network(c)
            check(not errs, "CONSOLE 无未捕获异常/error 日志", str(errs[:3]))
            check(not bad, "NETWORK 无 5xx", str(bad[:3]))
        finally:
            ch.terminate()
            ch.wait(timeout=10)
    finally:
        # 清理本次通过 UI/API 创建的记录
        for ep, kw in (("/students", "E2EACC"), ("/teachers", "E2EACC"),
                       ("/courses", "E2EACC")):
            try:
                purge(ep, kw, tok)
            except Exception:  # noqa: BLE001
                pass

    print("\nRESULT:", "PASS" if not failures else f"FAIL ({len(failures)})")
    if failures:
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print("BUSINESS_E2E_PASS")


main()
