import json, os, re, secrets, socket, subprocess, sys, time
from pathlib import Path
import httpx
import dev

root=Path(__file__).resolve().parents[1]
state_path=root/'.runtime/demo-connection.json'
state=json.loads(state_path.read_text()) if state_path.exists() else {}
action=sys.argv[1] if len(sys.argv)>1 else 'status'
if action not in {'start','status','stop'}:raise SystemExit('Use start, status or stop')
if action=='stop':
    for name in ('tunnel','gateway'):
        if state.get(name):dev.terminate(state[name])
    state_path.write_text('{}',encoding='utf-8')
    print('Demo connection stopped. Local application services were left running.')
    raise SystemExit(0)
if action=='status':
    print(json.dumps({'url':state.get('url'),**{name:bool(state.get(name) and dev.owned(state[name])) for name in ('gateway','tunnel')}},indent=2))
    raise SystemExit(0)
if not (root/'.runtime/cloudflared.exe').is_file():raise SystemExit('Install official cloudflared at .runtime/cloudflared.exe first')
secret_path=root/'.runtime/demo-gateway-key'
if not secret_path.exists(): secret_path.write_text(secrets.token_urlsafe(48),encoding='utf-8')
secret=secret_path.read_text(encoding='utf-8').strip()
cfg=dev.environment()
env={**os.environ,'DATAVAULT_GATEWAY_KEY':secret,'RUST_API_BASE':cfg['RUST_API_BASE']}
options={'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP}
if not state.get('gateway') or not dev.owned(state['gateway']):
    with socket.socket() as sock:
        sock.settimeout(1)
        if sock.connect_ex(('127.0.0.1',8010))==0:
            raise SystemExit('Port 8010 is owned by an untracked process; refusing to replace it.')
    with (root/'logs/demo-gateway.log').open('ab') as log:
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','demo_gateway:app','--app-dir','scripts','--host','127.0.0.1','--port','8010','--no-access-log'],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,**options)
    state['gateway']=dev.identity(proc.pid);state_path.write_text(json.dumps(state,indent=2))
headers={'X-Datavault-Gateway-Key':secret}
for _ in range(30):
    try:
        result=httpx.get('http://127.0.0.1:8010/v1/health',headers=headers,timeout=3)
        if result.status_code==200: break
    except httpx.HTTPError:pass
    time.sleep(1)
else:raise RuntimeError('Demo gateway did not become ready')
assert httpx.get('http://127.0.0.1:8010/v1/health').status_code==401
assert httpx.get('http://127.0.0.1:8010/v1/internal/search',headers=headers).status_code==404
print('Restricted gateway healthy; anonymous and internal requests blocked.',flush=True)
if not state.get('tunnel') or not dev.owned(state['tunnel']):
    with (root/'logs/demo-tunnel.log').open('wb') as log:
        proc=subprocess.Popen([str(root/'.runtime/cloudflared.exe'),'tunnel','--url','http://127.0.0.1:8010','--no-autoupdate','--protocol','http2'],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,**options)
    state['tunnel']=dev.identity(proc.pid);state_path.write_text(json.dumps(state,indent=2))
for _ in range(50):
    text=(root/'logs/demo-tunnel.log').read_text(encoding='utf-8',errors='replace')
    match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',text)
    if match:
        state['url']=match.group(0)
        state_path.write_text(json.dumps(state,indent=2))
        print('Temporary backend URL:',state['url'],flush=True)
        break
    time.sleep(1)
else:raise RuntimeError('Tunnel URL not available; inspect logs/demo-tunnel.log')
