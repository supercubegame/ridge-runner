"""Readiness candidate only. No launch, stop, file writes, repair, or keepalive."""
import argparse, http.client, json, math, sys, time

VERSION={'game':'ridge-runner','release':'playtest-35445091317-1',
    'archive_sha256':'ad73d9ba67b3cf31f5c9ab57c84d1eeeb74653f748a73d76b5dc32c9b36192f5'}

def wait(port=8060,timeout=180):
    start=time.monotonic();deadline=start+timeout;attempts=0
    def result(code,reason):
        return code,{'status':'READY' if code==0 else 'NOT_READY','reason':reason,
            'attempts':attempts,'elapsed_seconds':round(time.monotonic()-start,3),
            'scope':'loopback version identity only; not full asset or browser acceptance'}
    if type(port) is not int or not 1<=port<=65535 or not math.isfinite(timeout) or not .1<=timeout<=300:
        return result(2,'INVALID_ARGUMENT')
    while time.monotonic()<deadline:
        attempts+=1
        c=http.client.HTTPConnection('127.0.0.1',port,timeout=min(2,deadline-time.monotonic()))
        try:
            c.request('GET','/version.json',headers={'Cache-Control':'no-cache','Connection':'close'})
            r=c.getresponse()
            if r.status==200:
                body=b''
                while len(body)<=4096:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:return result(3,'DEADLINE')
                    # Bound slow body reads too; do not rely on proxy/environment configuration.
                    r.fp.raw._sock.settimeout(min(2,remaining))
                    chunk=r.read1(min(512,4097-len(body)))
                    if not chunk:break
                    body+=chunk
                    if r.isclosed():break
                if len(body)>4096:return result(2,'VERSION_TOO_LARGE')
                try:value=json.loads(body)
                except (ValueError,UnicodeError):return result(2,'INVALID_VERSION_JSON')
                if value!=VERSION:return result(2,'VERSION_MISMATCH')
                if time.monotonic()>=deadline:return result(3,'DEADLINE')
                return result(0,'MATCHING_EXISTING_SERVICE')
            if r.status not in (404,502,503,504):return result(2,'HTTP_REJECTED')
        except (OSError,http.client.HTTPException):
            pass
        finally:c.close()
        time.sleep(max(0,min(.1,deadline-time.monotonic())))
    return result(3,'DEADLINE')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8060,help='Loopback fixture override; Studio candidate defaults to 8060')
    parser.add_argument('--timeout',type=float,default=180,help='Proposed bounded wait, not a platform SLA')
    args=parser.parse_args()
    code,report=wait(args.port,args.timeout)
    print(json.dumps(report,sort_keys=True))
    sys.exit(code)
