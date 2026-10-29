import base64,json,os,socket,struct,subprocess,time,urllib.request,urllib.error
from urllib.parse import urlparse
API=os.environ.get('UAMS_E2E_API','http://127.0.0.1:8010/api/v1');FRONT=os.environ.get('UAMS_E2E_FRONT','http://127.0.0.1:5180');PORT=9233
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
  raw=e.read().decode();return e.code,(json.loads(raw) if raw else None)
def login(u,p):
 st,b=api('/auth/login',m='POST',b={'username':u,'real_name':{'admin':'admin','T001':'钱秀兰','20260001':'钱伟'}.get(u,u),'password':p});assert st==200;return b
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
t=login('T001','T001');tok=t['access_token'];user=t['user']
open('/tmp/ref_upload.txt','w').write('uams refresh test')
# cleanup leftovers
st,rows=api('/materials?teaching_class_id=1',tok)
for r in rows or []:
 if r['title'].startswith('REF资料测试'): api('/materials/'+str(r['id']),tok,'DELETE')
ch=subprocess.Popen(['google-chrome','--headless=new','--no-sandbox','--disable-gpu',f'--remote-debugging-port={PORT}','--user-data-dir=/tmp/chrome-e2e-mat','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try:urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version');break
  except:time.sleep(.2)
 c=C(wsc(target()));c.call('Page.enable');c.call('Runtime.enable');time.sleep(1.5)
 c.ev(f"localStorage.setItem('uams_token',{json.dumps(tok)});localStorage.setItem('uams_user',{json.dumps(json.dumps(user,ensure_ascii=False))});")
 c.call('Page.navigate',{'url':FRONT+'/teacher/materials'});time.sleep(4)
 doc=c.call('DOM.getDocument',{'depth':-1});n=c.call('DOM.querySelector',{'nodeId':doc['result']['root']['nodeId'],'selector':'input[type=file]'})
 print('file node',n.get('result',{}).get('nodeId'))
 c.call('DOM.setFileInputFiles',{'nodeId':n['result']['nodeId'],'files':['/tmp/ref_upload.txt']});time.sleep(.8)
 c.ev("(()=>{const el=document.querySelector('input[placeholder=\"资料标题\"]');if(el){const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(el,'REF资料测试刷新');el.dispatchEvent(new Event('input',{bubbles:true}))}})()")
 c.ev("[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='上传资料'&&b.offsetParent!==null)?.click()")
 ok=False
 for _ in range(40):
  time.sleep(.25);txt=c.ev('document.body.innerText') or ''
  if 'REF资料测试刷新' in txt and 'ref_upload' in txt: ok=True;break
 print('REF-013 material upload list refreshed:',ok);assert ok
 # delete
 c.ev("(()=>{const r=[...document.querySelectorAll('.el-table__row')].find(r=>r.innerText.includes('REF资料测试刷新'));const b=r&&[...r.querySelectorAll('button')].find(x=>x.innerText.trim()==='删除');b&&b.click()})()")
 time.sleep(.5)
 c.ev("[...document.querySelectorAll('.el-message-box button')].find(b=>/确定|删除/.test(b.innerText))?.click()")
 ok=False
 for _ in range(40):
  time.sleep(.25);txt=c.ev('document.body.innerText') or ''
  if 'REF资料测试刷新' not in txt: ok=True;break
 print('material delete refreshed:',ok);assert ok
 print('MATERIAL_E2E_PASS')
finally:
 ch.terminate()
 st,rows=api('/materials?teaching_class_id=1',tok)
 for r in rows or []:
  if r['title'].startswith('REF资料测试'): api('/materials/'+str(r['id']),tok,'DELETE')
