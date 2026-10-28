import base64,json,os,socket,struct,subprocess,time,urllib.request,urllib.error
from urllib.parse import urlparse
API=os.environ.get('UAMS_E2E_API','http://127.0.0.1:8010/api/v1');FRONT=os.environ.get('UAMS_E2E_FRONT','http://127.0.0.1:5180');PORT=9234
def ensure_test_environment():
    base=API.rsplit('/api/v1',1)[0]
    try:
        with urllib.request.urlopen(base+'/health',timeout=5) as x:
            health=json.loads(x.read().decode())
    except Exception as exc:
        raise SystemExit(f'无法连接隔离测试后端 {base}/health：{exc}')
    if health.get('env')!='testing':
        raise SystemExit(f'拒绝执行：目标环境不是 testing（env={health.get("env")}）')


def api(p,t=None,m='GET',b=None):
 d=json.dumps(b).encode() if b is not None else None;r=urllib.request.Request(API+p,data=d,method=m,headers={'Content-Type':'application/json'} if d else {})
 if t:r.add_header('Authorization','Bearer '+t)
 try:
  with urllib.request.urlopen(r) as x:
   raw=x.read().decode();return x.status,(json.loads(raw) if raw else None)
 except urllib.error.HTTPError as e:
  raw=e.read().decode()
  try:return e.code,json.loads(raw)
  except:return e.code,raw
def login(u,p):
 st,b=api('/auth/login',m='POST',b={'username':u,'password':p});assert st==200,(st,b);return b
def wsc(url):
 u=urlparse(url);s=socket.create_connection((u.hostname,u.port));k=base64.b64encode(os.urandom(16)).decode();s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode());s.recv(4096);return s
def send(s,p):
 b=p.encode();m=os.urandom(4);n=len(b);h=bytes([0x81])+(bytes([0x80|n]) if n<126 else bytes([0x80|126])+struct.pack('>H',n));s.sendall(h+m+bytes(x^m[i%4] for i,x in enumerate(b)))
def recv(s):
 h=s.recv(2);n=h[1]&127
 if n==126:n=struct.unpack('>H',s.recv(2))[0]
 elif n==127:n=struct.unpack('>Q',s.recv(8))[0]
 d=b''
 while len(d)<n:d+=s.recv(n-len(d))
 return d
class C:
 def __init__(s,w):s.w=w;s.i=0
 def call(s,m,p=None):
  s.i+=1;mid=s.i;send(s.w,json.dumps({'id':mid,'method':m,'params':p or {}}))
  while True:
   x=json.loads(recv(s.w))
   if x.get('id')==mid:return x
 def ev(s,e):return s.call('Runtime.evaluate',{'expression':e,'returnByValue':True}).get('result',{}).get('result',{}).get('value')
def target():
 r=urllib.request.Request(f'http://127.0.0.1:{PORT}/json/new?{FRONT}/login',method='PUT');return json.loads(urllib.request.urlopen(r).read())['webSocketDebuggerUrl']
ensure_test_environment()
admin=login('admin','admin123');at=admin['access_token']
teacher=login('T001','T001');tt=teacher['access_token'];tu=teacher['user'];tid=1
# cleanup previous temp class
st,classes=api('/teaching-classes?page_size=200',at)
for c in (classes or {}).get('items',[]):
 if c['code']=='REF-GRADE-01':
  for s in api('/teaching-classes/'+str(c['id'])+'/schedules',at)[1] or []:
   api('/teaching-classes/'+str(c['id'])+'/schedules/'+str(s['id']),at,'DELETE')
  try: api('/teaching-classes/'+str(c['id'])+'/students/2',at,'DELETE')
  except: pass
  try: api('/teaching-classes/'+str(c['id']),at,'DELETE')
  except: pass
st,cls=api('/teaching-classes',at,'POST',{'code':'REF-GRADE-01','task_id':1,'term_id':1,'teacher_id':1,'capacity':5})
print('create class',st,cls if st!=201 else cls.get('id'))
assert st==201
cid=cls['id']
st,sched=api('/teaching-classes/'+str(cid)+'/schedules',at,'POST',{'classroom_id':5,'day_of_week':7,'start_period':1,'end_period':2,'start_week':1,'end_week':16,'week_type':'ALL'})
print('schedule',st)
assert st==201
st,add=api('/teaching-classes/'+str(cid)+'/students',at,'POST',{'student_id':2})
print('add student',st);assert st==201
st,rows=api('/grades/teaching-classes/'+str(cid)+'/init',tt,'POST')
print('init',st,'rows',len(rows) if isinstance(rows,list) else rows);assert st==200 and isinstance(rows,list) and rows
gid=rows[0]['id']
ch=subprocess.Popen(['google-chrome','--headless=new','--no-sandbox','--disable-gpu',f'--remote-debugging-port={PORT}','--user-data-dir=/tmp/chrome-e2e-grade','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try:urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version');break
  except:time.sleep(.2)
 c=C(wsc(target()));c.call('Page.enable');c.call('Runtime.enable');time.sleep(1.5)
 c.ev(f"localStorage.setItem('uams_token',{json.dumps(tt)});localStorage.setItem('uams_user',{json.dumps(json.dumps(tu,ensure_ascii=False))});")
 c.call('Page.navigate',{'url':FRONT+f'/teacher/grades/{cid}'});time.sleep(4)
 # set first 5 visible score inputs to 85 (regular, mid theory/practice, final theory/practice)
 c.ev("""(()=>{const ins=[...document.querySelectorAll('.el-table input')].filter(i=>i.offsetParent!==null);const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}))};ins.slice(0,5).forEach(el=>set(el,85));return ins.length})()""")
 time.sleep(.5)
 c.ev("[...document.querySelectorAll('button')].find(b=>b.innerText.includes('保存草稿')&&b.offsetParent!==null)?.click()")
 ok=False
 for _ in range(40):
  time.sleep(.25)
  st,r=api('/grades/teaching-classes/'+str(cid),tt)
  if isinstance(r,list) and r and r[0].get('regular_score') is not None and r[0].get('total_score') is not None: ok=True;break
 print('REF-007 teacher save persisted/refreshed:',ok);assert ok
 # submit
 c.ev("window.__submitBtn=([...document.querySelectorAll('button')].find(b=>b.innerText.includes('提交审核')&&b.offsetParent!==null));window.__submitBtn&&window.__submitBtn.click()")
 time.sleep(1)
 c.ev("[...document.querySelectorAll('.el-message-box button')].find(b=>/确定|提交/.test(b.innerText))?.click()")
 time.sleep(1)
 print('submit debug body:',(c.ev('document.body.innerText') or '')[-500:].replace('\n',' | '))
 ok=False
 for _ in range(40):
  time.sleep(.25)
  st,r=api('/grades/teaching-classes/'+str(cid),tt)
  if isinstance(r,list) and r and r[0]['status']=='SUBMITTED': ok=True;break
 ui=c.ev('document.body.innerText') or ''
 print('REF-008 submit status refreshed:',ok,'UI待审核:', '待审核' in ui);assert ok
 print('GRADEENTRY_E2E_PASS')
finally:
 ch.terminate()
 # cleanup: reject SUBMITTED -> teacher save draft -> delete draft -> remove student -> schedules -> class
 try:
  api('/grades/reject',at,'POST',{'grade_ids':[gid],'reason':'REF cleanup'})
 except: pass
 try:
  st,g=api('/grades/teaching-classes/'+str(cid),tt)
  if isinstance(g,list) and g and g[0]['status']=='REJECTED':
   row=g[0];fields={k:row.get(k) for k in ('regular_score','mid_score','mid_theory_score','mid_practice_score','final_score','final_theory_score','final_practice_score','theory_makeup_score','practice_makeup_score') if row.get(k) is not None};fields['grade_id']=gid
   api('/grades',tt,'PUT',{'teaching_class_id':cid,'items':[fields]})
  api('/grades/'+str(gid),tt,'DELETE')
 except: pass
 try: api('/teaching-classes/'+str(cid)+'/students/2',at,'DELETE')
 except: pass
 for s in api('/teaching-classes/'+str(cid)+'/schedules',at)[1] or []:
  try:api('/teaching-classes/'+str(cid)+'/schedules/'+str(s['id']),at,'DELETE')
  except: pass
 try: api('/teaching-classes/'+str(cid),at,'DELETE')
 except: pass
