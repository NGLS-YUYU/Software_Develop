import base64,json,os,socket,struct,subprocess,time,urllib.request,urllib.error
from urllib.parse import urlparse
API=os.environ.get('UAMS_E2E_API','http://127.0.0.1:8010/api/v1'); FRONT=os.environ.get('UAMS_E2E_FRONT','http://127.0.0.1:5180'); PORT=9230
def ensure_test_environment():
    base=API.rsplit('/api/v1',1)[0]
    try:
        with urllib.request.urlopen(base+'/health',timeout=5) as x:
            health=json.loads(x.read().decode())
    except Exception as exc:
        raise SystemExit(f'无法连接隔离测试后端 {base}/health：{exc}')
    if health.get('env')!='testing':
        raise SystemExit(f'拒绝执行：目标环境不是 testing（env={health.get("env")}）')


def api(path, tok=None, method='GET', body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(API+path,data=data,method=method,headers={'Content-Type':'application/json'} if data else {})
    if tok: r.add_header('Authorization','Bearer '+tok)
    try:
        with urllib.request.urlopen(r,timeout=15) as x:
            raw=x.read().decode(); return x.status,(json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw=e.read().decode();
        try: return e.code,json.loads(raw)
        except: return e.code,raw

def login(u,p):
    st,b=api('/auth/login',method='POST',body={'username':u,'real_name':{'admin':'admin','T001':'钱秀兰','20260001':'钱伟'}.get(u,u),'password':p}); assert st==200,(st,b); return b

def wsc(url):
    u=urlparse(url); s=socket.create_connection((u.hostname,u.port),timeout=10); k=base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    if b'101' not in s.recv(4096): raise RuntimeError('ws')
    return s
def send(s,p,op=1):
    b=p.encode(); m=os.urandom(4); n=len(b); h=bytes([0x80|op])
    h+=bytes([0x80|n]) if n<126 else (bytes([0x80|126])+struct.pack('>H',n) if n<65536 else bytes([0x80|127])+struct.pack('>Q',n))
    s.sendall(h+m+bytes(x^m[i%4] for i,x in enumerate(b)))
def recv(s):
    h=s.recv(2); op=h[0]&15; n=h[1]&127
    if n==126: n=struct.unpack('>H',s.recv(2))[0]
    elif n==127: n=struct.unpack('>Q',s.recv(8))[0]
    d=b''
    while len(d)<n: d+=s.recv(n-len(d))
    if op==9: send(s,d,10); return recv(s)
    return op,d
class C:
    def __init__(s,w): s.w=w; s.i=0
    def call(s,m,p=None):
        s.i+=1; mid=s.i; send(s.w,json.dumps({'id':mid,'method':m,'params':p or {}}))
        while True:
            op,d=recv(s.w)
            if op==1:
                x=json.loads(d)
                if x.get('id')==mid: return x
    def ev(s,expr,awaitp=False):
        r=s.call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':awaitp})
        return r.get('result',{}).get('result',{}).get('value')
def target():
    r=urllib.request.Request(f'http://127.0.0.1:{PORT}/json/new?about:blank',method='PUT')
    with urllib.request.urlopen(r,timeout=10) as x: return json.loads(x.read().decode())['webSocketDebuggerUrl']
HELPERS='''
window.__e2e={
  q:(sel,root=document)=>root.querySelector(sel),
  set:(el,val)=>{if(!el)return false;const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(el,val);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true;},
  byLabel:(label)=>{const items=[...document.querySelectorAll('.el-form-item')];const it=items.find(i=>i.querySelector('.el-form-item__label')?.innerText.trim().startsWith(label));return it?.querySelector('input,textarea')||null;},
  fill:(label,val)=>window.__e2e.set(window.__e2e.byLabel(label),val),
  visible:(el)=>!!el && el.offsetParent!==null,
  clickText:(text,root=document)=>{const els=[...root.querySelectorAll('button,a,.el-select-dropdown__item')].filter(e=>window.__e2e.visible(e));const e=els.find(x=>(x.innerText||'').trim().includes(text));if(e){e.click();return true}return false},
  clickFirstOption:()=>{const els=[...document.querySelectorAll('.el-select-dropdown__item')].filter(e=>window.__e2e.visible(e));if(els[0]){els[0].click();return els[0].innerText}return ''},
  closeDialog:()=>{const b=[...document.querySelectorAll('.el-dialog button')].find(x=>(x.innerText||'').trim()==='取消');if(b){b.click();return true}return false},
  confirm:()=>{const b=[...document.querySelectorAll('.el-message-box button')].find(x=>(x.innerText||'').trim().includes('确定')||(x.innerText||'').trim().includes('删除'));if(b){b.click();return true}return false}
}
'''
def wait(c, expr, timeout=8, interval=.25):
    end=time.time()+timeout
    while time.time()<end:
        try:
            if c.ev(expr): return True
        except Exception: pass
        time.sleep(interval)
    return False
def main():
    ensure_test_environment()
    admin=login('admin','admin123'); tok=admin['access_token']; user=admin['user']
    ch=subprocess.Popen(['google-chrome','--headless=new','--no-sandbox','--disable-gpu',f'--remote-debugging-port={PORT}','--user-data-dir=/tmp/chrome-e2e-refresh','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try: urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version',timeout=1); break
            except Exception: time.sleep(.2)
        w=wsc(target()); c=C(w); c.call('Page.enable'); c.call('Runtime.enable')
        c.call('Page.navigate',{'url':FRONT+'/login'}); time.sleep(1.5)
        c.ev(f"localStorage.setItem('uams_token',{json.dumps(tok)});localStorage.setItem('uams_user',{json.dumps(json.dumps(user,ensure_ascii=False))});")
        c.call('Page.navigate',{'url':FRONT+'/admin/students'}); time.sleep(4)
        c.ev(HELPERS)
        assert wait(c,"!!document.querySelector('.el-table__row')"), 'student table not loaded'
        before=c.ev("document.querySelectorAll('.el-table__row').length")
        userno='REF90001'; name='刷新测试学生'; name2='刷新测试学生改'
        # cleanup leftover
        st,res=api('/students?keyword='+userno,tok); 
        for row in (res or {}).get('items',[]): api('/students/'+str(row['id']),tok,'DELETE')
        # create
        c.ev("window.__e2e.clickText('新增学生')"); time.sleep(.6); c.ev(HELPERS)
        c.ev(f"window.__e2e.fill('学号',{json.dumps(userno)});window.__e2e.fill('姓名',{json.dumps(name)})")
        c.ev("document.querySelectorAll('.el-dialog .el-select input')[0]?.click()"); time.sleep(.5)
        opt=c.ev("window.__e2e.clickFirstOption()"); time.sleep(.3)
        c.ev("window.__e2e.clickText('确定',document.querySelector('.el-dialog')||document)"); 
        ok=wait(c,f"document.body.innerText.includes({json.dumps(userno)})",10)
        print('REF-001 create visible:',ok,'class_option=',opt)
        assert ok
        total_after=c.ev("document.querySelectorAll('.el-table__row').length")
        # edit
        row_js=f"[...document.querySelectorAll('.el-table__row')].find(r=>r.innerText.includes({json.dumps(userno)}))"
        c.ev(f"(()=>{{const r={row_js};const b=[...r.querySelectorAll('button')].find(x=>x.innerText.trim()==='编辑');b&&b.click()}})()")
        time.sleep(.7); c.ev(HELPERS)
        c.ev(f"window.__e2e.fill('姓名',{json.dumps(name2)})")
        c.ev("window.__e2e.clickText('确定',document.querySelector('.el-dialog')||document)")
        ok=wait(c,f"document.body.innerText.includes({json.dumps(name2)})",10)
        print('REF-002 edit visible:',ok)
        assert ok
        # duplicate failure should keep list and show error
        c.ev("window.__e2e.clickText('新增学生')"); time.sleep(.6); c.ev(HELPERS)
        c.ev(f"window.__e2e.fill('学号',{json.dumps(userno)});window.__e2e.fill('姓名','重复测试')")
        c.ev("document.querySelectorAll('.el-dialog .el-select input')[0]?.click()"); time.sleep(.4); c.ev("window.__e2e.clickFirstOption()")
        c.ev("window.__e2e.clickText('确定',document.querySelector('.el-dialog')||document)")
        time.sleep(1.5); c.ev(HELPERS)
        still= c.ev(f"document.body.innerText.includes({json.dumps(userno)})")
        dialog= c.ev("!!document.querySelector('.el-dialog') && getComputedStyle(document.querySelector('.el-overlay')).display!=='none'")
        print('REF-014 duplicate keeps data/dialog:',still,dialog)
        c.ev("window.__e2e.closeDialog()"); time.sleep(.5)
        # delete
        c.ev(f"(()=>{{const r={row_js};const b=[...r.querySelectorAll('button')].find(x=>x.innerText.trim()==='删除');b&&b.click()}})()")
        time.sleep(.6); c.ev("window.__e2e.confirm()")
        ok=wait(c,f"!document.body.innerText.includes({json.dumps(userno)})",10)
        print('REF-003 delete removed:',ok)
        assert ok
        print('rows before/after',before,total_after,c.ev("document.querySelectorAll('.el-table__row').length"))
        print('STUDENT_E2E_PASS')
    finally:
        ch.terminate()
main()
