"""Read two known template candidates; mock creation only, never cloud writes."""
import base64
import datetime
import hashlib
import http.client
import io
import json
import logging
import os
from pathlib import Path
import signal
import socket
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qsl
import g0_account_read as prev

TEMPLATES = ("cet_01jwy93dw1g29nd9ta86nfxy4h","cet_01jz17475rka18x4swrebtjxev")
EXPECTED = dict(zip(TEMPLATES,("0","01")))
PREFIX="/v1/cloudspaces/environment-templates/"

class Scope:
    def __init__(self):
        self.org=None
        self.sent=self.blocked=0
        self.end=time.monotonic()+50
    def check(self,method,url,consume=True):
        u=urlsplit(url);pairs=parse_qsl(u.query,keep_blank_values=True);q=dict(pairs)
        ok=method=="GET" and u.scheme=="https" and u.netloc=="lightning.ai" and not u.fragment and len(q)==len(pairs)
        route=(u.path=="/v1/projects/"+prev.PROJECT and not q) or (self.org is not None and u.path in [PREFIX+x for x in TEMPLATES] and q=={"orgId":self.org,"projectId":prev.PROJECT})
        if not ok or not route or time.monotonic()>self.end:
            self.blocked+=1
            raise ValueError("SCOPE")
        if consume:
            if self.sent>=3:raise ValueError("BUDGET")
            self.sent+=1

classUnused = None

def fixture():
    if any(os.environ.get(x) for x in ("LIGHTNING_USER_ID","LIGHTNING_API_KEY","LIGHTNING_AUTH_TOKEN","GH_TOKEN")):
        raise ValueError("NO_CREDENTIALS")
    report={"kind":"g0_template_fixture","status":"FAIL","platform_requests":0,"checks":[]}
    def check(name,ok):
        if not ok:raise AssertionError(name)
        report["checks"].append(name)
    def deny(*a,**k):raise AssertionError("NETWORK_FORBIDDEN")
    try:
        with patch.object(socket.socket,"connect",deny),patch.object(socket,"getaddrinfo",deny):
            import inspect
            import urllib3
            from lightning_sdk.api.studio_api import StudioApi
            from lightning_sdk.lightning_cloud.openapi import CloudSpaceServiceCreateCloudSpaceBody
            from lightning_sdk.lightning_cloud.openapi.models.v1_cluster_accelerator import V1ClusterAccelerator
            client,projects,studios,clusters,templates=prev.apis()
            source=Path(inspect.getfile(StudioApi)).read_bytes()
            blob=hashlib.sha1(b"blob "+str(len(source)).encode()+b"\0"+source).hexdigest()
            check("exact_studio_api_source",blob=="82bd20339de3b827a552ec756a7cff28e3ed35b0")
            calls=[]
            class MockCreate:
                def cloud_space_service_create_cloud_space(self,body,project):
                    calls.append(("create",client.sanitize_for_serialization(body)))
                    return SimpleNamespace(id="fixture-studio",cluster_id="fixture-cloud")
                def cloud_space_service_create_lightning_run(self,**kw):
                    calls.append(("run",client.sanitize_for_serialization(kw["body"])))
            # Bypass constructor; execute only reviewed create method with fake client.
            obj=object.__new__(StudioApi);obj._client=MockCreate()
            obj.create_studio("fixture-name","fixture-project",cloud_account="fixture-cloud",disable_secrets=True,
                              cloud_space_environment_template_id="fixture-template")
            check("high_level_two_mock_calls",[x[0] for x in calls]==["create","run"])
            check("high_level_omits_compute", "computeName" not in calls[0][1])
            check("high_level_omits_spot", "spot" not in calls[0][1])
            check("high_level_disables_secrets",calls[0][1]["disableSecrets"] is True)
            check("second_request_local_source",calls[1][1]=={"clusterId":"fixture-cloud","localSource":True})
            check("high_level_signature_no_machine","machine" not in inspect.signature(StudioApi.create_studio).parameters)
            body=CloudSpaceServiceCreateCloudSpaceBody(name="fixture-name",cluster_id="fixture-cloud",
                compute_name="cpu-4",spot=False,disable_secrets=True,cloud_space_environment_template_id="fixture-template")
            serialized=client.sanitize_for_serialization(body)
            check("low_level_explicit_cpu4",serialized["computeName"]=="cpu-4")
            check("low_level_explicit_nonspot",serialized["spot"] is False)
            report["creation_mock"]={"high_level_create_keys":sorted(calls[0][1]),"high_level_run_keys":sorted(calls[1][1]),
                                     "explicit_body":serialized,"backend_acceptance":"NOT_TESTED"}
            report["price_property_docs"]={n:(getattr(V1ClusterAccelerator,n).fget.__doc__ or "").strip() for n in ("cost","original_cost","spot_price")}
            class FakePool:
                def request(self,m,u,**kw):
                    check("detail_redirect_retry_disabled",kw["redirect"] is False and kw["retries"] is False)
                    return urllib3.HTTPResponse(body=io.BytesIO(b"{}"),status=200,preload_content=False)
            scope=Scope();scope.org="fixture-org"
            client.rest_client.pool_manager=prev.Pool(scope,FakePool())
            raw=prev.read(templates.cloud_space_environment_template_service_get_cloud_space_environment_template,
                          id=TEMPLATES[0],org_id=scope.org,project_id=prev.PROJECT)
            check("generated_detail_route",raw=={} and scope.sent==1)
            for i,(method,url) in enumerate([
                ("POST",prev.HOST+PREFIX+TEMPLATES[0]),
                ("GET",prev.HOST+PREFIX+"wrong?orgId=fixture-org&projectId="+prev.PROJECT),
                ("GET",prev.HOST+PREFIX+TEMPLATES[0]+"?orgId=wrong&projectId="+prev.PROJECT),
                ("GET",prev.HOST+"/v1/projects/"+prev.PROJECT+"/cloudspaces/"+prev.STUDIO),
                ("GET",prev.HOST+"/v1/projects/"+prev.PROJECT+"/secrets")]):
                try:scope.check(method,url)
                except ValueError:report["checks"].append("blocked_"+str(i))
                else:raise AssertionError("BLOCK")
            for _ in range(2):scope.check("GET",prev.HOST+"/v1/projects/"+prev.PROJECT)
            try:scope.check("GET",prev.HOST+"/v1/projects/"+prev.PROJECT)
            except ValueError:report["checks"].append("three_request_budget")
            else:raise AssertionError("BUDGET")
            report["status"]="PASS"
    except Exception as e:
        report.update(error_type=type(e).__name__,failure_hint=str(e)[:180])
    report["test_count"]=len(report["checks"])
    Path("out").mkdir(exist_ok=True)
    Path("out/g0-template-fixture.json").write_text(json.dumps(report,indent=2)+"\n")
    print("Template fixture",report["status"],report["test_count"])
    return 0 if report["status"]=="PASS" else 1

def main():
    report={"kind":"g0_template_detail_read","status":"FAIL","qualification":"NOT_PASSED",
            "started_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "platform_writes":0,"studio_reads":0,"public_url_requests":0,"templates":[]}
    scope=Scope();stage="credentials";tokens=[]
    original=http.client.HTTPConnection.putrequest
    def wire(conn,method,url,*a,**kw):
        import urllib3.connection
        if conn.host!="lightning.ai" or not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)):
            raise ValueError("WIRE")
        scope.check(method,prev.HOST+url if url.startswith("/") else url,False)
        return original(conn,method,url,*a,**kw)
    def deadline(*a):raise TimeoutError("DEADLINE")
    signal.signal(signal.SIGALRM,deadline);signal.alarm(60)
    try:
        uid,key=[os.environ.get(n,"") for n in ("LIGHTNING_USER_ID","LIGHTNING_API_KEY")]
        if not uid or not key:raise ValueError("CREDENTIALS")
        tokens=[uid,key,base64.b64encode((uid+":"+key).encode("ascii")).decode()]
        http.client.HTTPConnection.putrequest=wire
        client,projects,studios,clusters,templates=prev.apis()
        client.set_default_header("Authorization","Basic "+tokens[2])
        client.set_default_header("Accept-Encoding","identity")
        client.rest_client.pool_manager=prev.Pool(scope,client.rest_client.pool_manager)
        stage="project"
        project=prev.read(projects.projects_service_get_project,id=prev.PROJECT)
        if project.get("id")!=prev.PROJECT or project.get("name")!="vision-model" or project.get("ownerType")!="organization":
            raise ValueError("IDENTITY")
        scope.org=prev.label(project.get("ownerId"))
        if not scope.org:raise ValueError("ORG")
        for template_id in TEMPLATES:
            stage="template_"+EXPECTED[template_id]
            raw=prev.read(templates.cloud_space_environment_template_service_get_cloud_space_environment_template,
                          id=template_id,org_id=scope.org,project_id=prev.PROJECT)
            if raw.get("id")!=template_id or raw.get("managedId")!=EXPECTED[template_id]:
                raise ValueError("TEMPLATE_IDENTITY")
            item=prev.template_summary({"templates":[raw]})["rows"][0]
            c=raw.get("config")
            if not isinstance(c,dict):raise ValueError("CONFIG")
            # Distinguish omitted, null, empty and actual values. No arbitrary text.
            item["field_states"]={k:("MISSING" if k not in c else "NULL" if c[k] is None else "EMPTY" if c[k] in ("",[]) else "PRESENT") for k in ("defaultMachine","allowedMachines","setupScriptText","machineImageVersion")}
            report["templates"].append(item)
        report["status"]="READS_COMPLETED"
    except Exception as e:
        report.update(failure_stage=stage,error_type=type(e).__name__)
        if type(getattr(e,"status",None)) is int:report["http_status"]=e.status
    finally:
        signal.alarm(0);http.client.HTTPConnection.putrequest=original
        report.update(get_attempts=scope.sent,blocked=scope.blocked,ended_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        report["limitations"]=["Two known candidates only, not exhaustive catalog","No backend create, launch or billing test","Empty defaults do not guarantee CPU choice","No Studio read or public endpoint request"]
        text=json.dumps(report,indent=2)
        if any(t and t in text for t in tokens):raise RuntimeError("REDACTION")
        Path("out").mkdir(exist_ok=True);Path("out/studio-probe.json").write_text(text+"\n")
    return 0 if report["status"]=="READS_COMPLETED" else 1

if __name__=="__main__":
    os.environ.update(LIGHTNING_DISABLE_VERSION_CHECK="1",LIGHTNING_DEBUG="0",DO_NOT_TRACK="1")
    logging.disable(logging.CRITICAL)
    sys.exit(fixture() if "--self-test" in sys.argv else main())
