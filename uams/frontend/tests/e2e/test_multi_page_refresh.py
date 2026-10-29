import base64,json,os,socket,struct,subprocess,time,urllib.request,urllib.error
from urllib.parse import urlparse
API=os.environ.get('UAMS_E2E_API','http://127.0.0.1:8010/api/v1'); FRONT=os.environ.get('UAMS_E2E_FRONT','http://127.0.0.1:5180'); PORT=9231
def ensure_test_environment():
    base=API.rsplit('/api/v1',1)[0]
    try:
        with urllib.request.urlopen(base+'/health',timeout=5) as x:
            health=json.loads(x.read().decode())
    except Exception as exc:
        raise SystemExit(f'无法连接隔离测试后端 {base}/health：{exc}')
    if health.get('env')!='testing':
        raise SystemExit(f'拒绝执行：目标环境不是 testing（env={health.get("env")}）')


def api(path,tok=None,method='GET',body=None):
 d=json.dumps(body).encode() if body is not None else None
 r=urllib.request.Request(API+path,data=d,method=method,headers={'Content-Type':'application/json'} if d else {})
 if tok:r.add_header('Authorization','Bearer '+tok)
 try:
  with urllib.request.urlopen(r,timeout=15) as x:
   raw=x.read().decode();return x.status,(json.loads(raw) if raw else None)
 except urllib.error.HTTPError as e:
  raw=e.read().decode()
  try:return e.code,json.loads(raw)
  except:return e.code,raw
def login(u,p):
 st,b=api('/auth/login',method='POST',body={'username':u,'real_name':{'admin':'admin','T001':'钱秀兰','20260001':'钱伟'}.get(u,u),'password':p});assert st==200,(st,b);return b
def wsc(url):
 u=urlparse(url);s=socket.create_connection((u.hostname,u.port),timeout=10);k=base64.b64encode(os.urandom(16)).decode()
 s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
 if b'101' not in s.recv(4096):raise RuntimeError('ws')
 return s
def send(s,p,op=1):
 b=p.encode();m=os.urandom(4);n=len(b);h=bytes([0x80|op])
 h+=bytes([0x80|n]) if n<126 else (bytes([0x80|126])+struct.pack('>H',n) if n<65536 else bytes([0x80|127])+struct.pack('>Q',n))
 s.sendall(h+m+bytes(x^m[i%4] for i,x in enumerate(b)))
def recv(s):
 h=s.recv(2);op=h[0]&15;n=h[1]&127
 if n==126:n=struct.unpack('>H',s.recv(2))[0]
 elif n==127:n=struct.unpack('>Q',s.recv(8))[0]
 d=b''
 while len(d)<n:d+=s.recv(n-len(d))
 if op==9:send(s,d,10);return recv(s)
 return op,d
class C:
 def __init__(s,w):s.w=w;s.i=0
 def call(s,m,p=None):
  s.i+=1;mid=s.i;send(s.w,json.dumps({'id':mid,'method':m,'params':p or {}}))
  while True:
   op,d=recv(s.w)
   if op==1:
    x=json.loads(d)
    if x.get('id')==mid:return x
 def ev(s,e,aw=False):
  r=s.call('Runtime.evaluate',{'expression':e,'returnByValue':True,'awaitPromise':aw})
  return r.get('result',{}).get('result',{}).get('value')
def target():
 r=urllib.request.Request(f'http://127.0.0.1:{PORT}/json/new?about:blank',method='PUT')
 with urllib.request.urlopen(r) as x:return json.loads(x.read().decode())['webSocketDebuggerUrl']
HELPERS='''
window.__e={q:(s,r=document)=>r.querySelector(s),set:(el,v)=>{if(!el)return false;const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true},
byLabel:l=>{const it=[...document.querySelectorAll('.el-form-item')].find(i=>i.querySelector('.el-form-item__label')?.innerText.trim().startsWith(l));return it?.querySelector('input,textarea')||null},
fill:(l,v)=>window.__e.set(window.__e.byLabel(l),v),vis:e=>!!e&&e.offsetParent!==null,
click:(t,root=document)=>{const es=[...root.querySelectorAll('button,a,.el-tabs__item,.el-select-dropdown__item')].filter(window.__e.vis);const e=es.find(x=>(x.innerText||'').trim().includes(t));if(e){e.click();return true}return false},
opt:()=>{const es=[...document.querySelectorAll('.el-select-dropdown__item')].filter(window.__e.vis);if(es[0]){es[0].click();return es[0].innerText}return ''},
confirm:()=>{const b=[...document.querySelectorAll('.el-message-box button')].find(x=>/确定|删除|通过/.test(x.innerText||''));if(b){b.click();return true}return false},
rowBtn:(txt,btn)=>{const r=[...document.querySelectorAll('.el-table__row')].find(x=>(x.innerText||'').includes(txt));if(!r)return false;const b=[...r.querySelectorAll('button')].find(x=>(x.innerText||'').trim().includes(btn));if(b){b.click();return true}return false}
}
'''
def wait(c,e,t=8):
 end=time.time()+t
 while time.time()<end:
  try:
   if c.ev(e):return True
  except:pass
  time.sleep(.25)
 return False
def main():
 ensure_test_environment()
 admin=login('admin','admin123');at=admin['access_token'];au=admin['user']
 stu=login('20260001','20260001');stok=stu['access_token'];suser=stu['user']
 def drop_test_selection():
  for x in api('/course-selections/mine?semester=2026-2027-1',stok)[1] or []:
   if x['teaching_class_id']==7:
    try: api('/course-selections/'+str(x['id']),stok,'DELETE')
    except: pass
 def ensure_grade_approved():
  approved=api('/grades/approved?semester=2026-2027-1',at)[1] or []
  if any(x['id']==1 for x in approved): return
  tt=login('T001','T001')['access_token']
  rows=api('/grades/teaching-classes/1',tt)[1]; g=next(x for x in rows if x['id']==1)
  if g['status']=='REJECTED':
   fields={k:g.get(k) for k in ('regular_score','mid_score','mid_theory_score','mid_practice_score','final_score','final_theory_score','final_practice_score','theory_makeup_score','practice_makeup_score') if g.get(k) is not None};fields['grade_id']=1
   api('/grades',tt,'PUT',{'teaching_class_id':1,'items':[fields]})
   api('/grades/teaching-classes/1/submit',tt,'POST')
  elif g['status']=='DRAFT':
   api('/grades/teaching-classes/1/submit',tt,'POST')
  try: api('/grades/approve',at,'POST',{'grade_ids':[1]})
  except: pass
 drop_test_selection(); ensure_grade_approved()
 ch=subprocess.Popen(['google-chrome','--headless=new','--no-sandbox','--disable-gpu',f'--remote-debugging-port={PORT}','--user-data-dir=/tmp/chrome-e2e-refresh2','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 temp_term=None;temp_ann=None;selected=False
 try:
  for _ in range(50):
   try:urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version',timeout=1);break
   except:time.sleep(.2)
  w=wsc(target());c=C(w);c.call('Page.enable');c.call('Runtime.enable')
  def as_admin():
   c.call('Page.navigate',{'url':FRONT+'/login'});time.sleep(1.2)
   c.ev(f"localStorage.setItem('uams_token',{json.dumps(at)});localStorage.setItem('uams_user',{json.dumps(json.dumps(au,ensure_ascii=False))});")
  def as_student():
   c.call('Page.navigate',{'url':FRONT+'/login'});time.sleep(1.2)
   c.ev(f"localStorage.setItem('uams_token',{json.dumps(stok)});localStorage.setItem('uams_user',{json.dumps(json.dumps(suser,ensure_ascii=False))});")
  def nav(path):
   c.call('Page.navigate',{'url':FRONT+path});time.sleep(3);c.ev(HELPERS)
  # ---------- course create/delete ----------
  as_admin();nav('/admin/courses');c.ev(HELPERS)
  assert wait(c,"!!document.querySelector('.el-table__row')"),'courses not loaded'
  code='REF-C-9001';st,res=api('/courses?keyword='+code,at)
  for r in (res or {}).get('items',[]):api('/courses/'+str(r['id']),at,'DELETE')
  c.ev("window.__e.click('新增课程')");time.sleep(.6);c.ev(HELPERS)
  c.ev(f"window.__e.fill('课程代码',{json.dumps(code)});window.__e.fill('课程名称','刷新测试课程')")
  c.ev("document.querySelectorAll('.el-dialog .el-select input')[0]?.click()");time.sleep(.4);c.ev("window.__e.opt()")
  c.ev("window.__e.click('确定',document.querySelector('.el-dialog')||document)")
  ok=wait(c,f"document.body.innerText.includes({json.dumps(code)})",10)
  print('REF-004 course create visible:',ok);assert ok
  c.ev(f"window.__e.rowBtn({json.dumps(code)},'删除')");time.sleep(.5);c.ev("window.__e.confirm()")
  ok=wait(c,f"!document.body.innerText.includes({json.dumps(code)})",10)
  print('course delete visible:',ok);assert ok
  # ---------- teaching capacity edit ----------
  nav('/admin/teaching');c.ev(HELPERS);assert wait(c,"document.body.innerText.includes('CS101-2026-2027-1-01')",10)
  c.ev("window.__e.rowBtn('CS101-2026-2027-1-01','编辑')");time.sleep(.7);c.ev(HELPERS)
  c.ev("window.__e.fill('容量','41')")
  c.ev("window.__e.click('确定',document.querySelector('.el-dialog')||document)")
  ok=wait(c,"document.body.innerText.includes('/41')",10)
  print('REF-005 class capacity refreshed:',ok);assert ok
  # restore
  c.ev("window.__e.rowBtn('CS101-2026-2027-1-01','编辑')");time.sleep(.6);c.ev(HELPERS)
  c.ev("window.__e.fill('容量','40')");c.ev("window.__e.click('确定',document.querySelector('.el-dialog')||document)");time.sleep(1)
  # ---------- term create/activate ----------
  st,term=api('/terms',at,'POST',{'name':'REF刷新测试学期','academic_year':'2027-2028','semester':2,'start_date':'2027-02-20','end_date':'2027-07-10','status':'PLANNED'})
  print('term create',st)
  if st==201:
   temp_term=term['id'];nav('/admin/terms');c.ev(HELPERS);time.sleep(1)
   # 编辑学期名称：验证保存后表格行同步刷新
   c.ev("window.__e.rowBtn('REF刷新测试学期','编辑')");time.sleep(.6);c.ev(HELPERS)
   c.ev("window.__e.fill('学期名称','REF刷新测试学期改')")
   c.ev("window.__e.click('确定',document.querySelector('.el-dialog')||document)")
   ok=wait(c,"document.body.innerText.includes('REF刷新测试学期改')",10)
   print('REF-006 term edit row refreshed:',ok);assert ok
   # 已有 ACTIVE 学期时，激活应被后端拒绝且不改变当前学期（失败不污染状态）
   c.ev("window.__e.rowBtn('REF刷新测试学期改','激活')");time.sleep(.6);c.ev("window.__e.confirm()")
   time.sleep(1.2)
   st2,active=api('/terms/active',at)
   print('REF-006 activation blocked keeps active:',(active.get('id') if isinstance(active,dict) else None)==1)
  # ---------- announcement publish ----------
  st,ann=api('/announcements',at,'POST',{'title':'REF刷新测试公告','content':'refresh test','target_type':'ALL'})
  if st==201:
   temp_ann=ann['id'];nav('/admin/announcements');c.ev(HELPERS);assert wait(c,"document.body.innerText.includes('REF刷新测试公告')",10)
   c.ev("window.__e.rowBtn('REF刷新测试公告','发布')");time.sleep(1)
   ok=wait(c,"document.body.innerText.includes('REF刷新测试公告') && document.body.innerText.includes('已发布')",10)
   print('REF-012 announcement publish refreshed:',ok);assert ok
  # ---------- student selection ----------
  drop_test_selection()
  as_student();nav('/student/selection');c.ev(HELPERS);time.sleep(1)
  has_avail=c.ev("document.body.innerText.includes('CS401')")
  print('selection available:',has_avail)
  assert has_avail
  c.ev("[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='选课'&&window.__e.vis(b))?.click()")
  time.sleep(.6);c.ev("window.__e.confirm()");time.sleep(2);c.ev(HELPERS)
  c.ev("window.__e.click('我的选课')");time.sleep(.8);c.ev(HELPERS)
  mine=c.ev("document.body.innerText") or ''
  ok='软件工程' in mine
  st,mine_api=api('/course-selections/mine?semester=2026-2027-1',stok)
  ok_api=any(x['teaching_class_id']==7 for x in mine_api or [])
  print('REF-010 selection updated in mine tab:',ok,'api:',ok_api);assert ok and ok_api
  # drop the selected 软件工程 item in mine tab
  c.ev("[...document.querySelectorAll('.mine-item')].find(i=>i.innerText.includes('软件工程'))?.querySelector('button')?.click()")
  time.sleep(.6);c.ev("window.__e.confirm()");time.sleep(2);c.ev(HELPERS)
  st,mine_api=api('/course-selections/mine?semester=2026-2027-1',stok)
  ok_api=not any(x['teaching_class_id']==7 for x in mine_api or [])
  c.ev("window.__e.click('我的选课')");time.sleep(.5)
  mine=c.ev("document.body.innerText") or ''
  ok_ui='软件工程' not in mine
  print('REF-011 drop refreshed:',ok_ui,'api:',ok_api);assert ok_api
  # ---------- grade approval ----------
  # unapprove -> teacher resubmit -> admin UI approve
  st,b=api('/grades/1/unapprove',at,'POST',{'reason':'REF e2e'});print('unapprove',st)
  if st==200:
   teacher=login('T001','T001');tt=teacher['access_token']
   rows=api('/grades/teaching-classes/1',tt)[1]
   g=next(x for x in rows if x['id']==1)
   fields={k:g.get(k) for k in ('regular_score','mid_score','mid_theory_score','mid_practice_score','final_score','final_theory_score','final_practice_score','theory_makeup_score','practice_makeup_score') if g.get(k) is not None}
   fields['grade_id']=1
   st_save,_=api('/grades',tt,'PUT',{'teaching_class_id':1,'items':[fields]})
   st_sub,_=api('/grades/teaching-classes/1/submit',tt,'POST')
   print('teacher save/submit',st_save,st_sub)
   as_admin();nav('/admin/grades');c.ev(HELPERS);assert wait(c,"document.body.innerText.includes('20260001')",10)
   c.ev("window.__e.rowBtn('20260001','通过')")
   time.sleep(.5);c.ev("window.__e.confirm()")
   ok=False
   for _ in range(60):
    time.sleep(.3)
    st2,g=api('/grades/approved?semester=2026-2027-1',at)
    if isinstance(g,list) and any(x['id']==1 for x in g): ok=True;break
   time.sleep(1)
   pending_ui=c.ev("document.body.innerText") or ''
   print('REF-009 grade approve refreshed:',ok,'pending row gone:', '20260001' not in pending_ui);assert ok
  print('REFRESH2_DONE')
 finally:
  # restore/cleanup
  try:
   api('/terms/1/activate',at,'POST')
  except: pass
  # ensure grade 1 restored to APPROVED if test interrupted
  try:
   st,b=api('/grades/approved?semester=2026-2027-1',at)
   if not any(x['id']==1 for x in b): api('/grades/approve',at,'POST',{'grade_ids':[1]})
  except: pass
  if temp_term:
   try:api('/terms/'+str(temp_term),at,'DELETE')
   except: pass
  if temp_ann:
   try:api('/announcements/'+str(temp_ann),at,'DELETE')
   except: pass
  try: drop_test_selection()
  except: pass
  try:
   rows=api('/grades/approved?semester=2026-2027-1',at)[1]
   if not any(x['id']==1 for x in rows or []):
    api('/grades/approve',at,'POST',{'grade_ids':[1]})
  except: pass
  ch.terminate()
main()
