"""Bounded G0 account metadata reads; no Studio object or platform writes."""
import base64
import contextlib
import datetime
import hashlib
import http.client
import json
import logging
import math
import os
from pathlib import Path
import re
import signal
import socket
import sys
import time
from urllib.parse import urlsplit, parse_qsl, urlencode, quote

PROJECT = "01hrhh1avmp22zbv37depwjkp8"
STUDIO = "01m2watakghqmc1fnymkg5czax"
HOST = "https://lightning.ai"
CAP = 1048576

class Scope:
    def __init__(self):
        self.org = self.cluster = self.provider = None
        self.sent = self.blocked = 0
        self.deadline = time.monotonic() + 100
    def check(self, method, url, consume=True):
        u = urlsplit(url)
        pairs = parse_qsl(u.query, keep_blank_values=True)
        q = dict(pairs)
        ok = method == "GET" and u.scheme == "https" and u.netloc == "lightning.ai" and not u.fragment and len(q) == len(pairs)
        p = u.path
        if p in ("/v1/projects/"+PROJECT, "/v1/projects/"+PROJECT+"/cloudspaces/"+STUDIO):
            match = not q
        elif p == "/v1/projects/"+PROJECT+"/clusters":
            match = self.org is not None and not q
        elif p == "/v1/core/clusters":
            match = self.org is not None and q == {"orgId":self.org, "projectId":PROJECT}
        elif p == "/v1/core/accelerators":
            match = self.provider is not None and q == {"cloudProvider":self.provider,"projectId":PROJECT}
        elif self.cluster and p == "/v1/core/clusters/"+quote(self.cluster,safe="")+"/accelerators":
            match = self.org is not None and q == {"orgId":self.org}
        elif p in ("/v1/cloudspaces/environment-templates","/v1/cloudspaces/environment-templates/managed"):
            match = self.org is not None and q == {"orgId":self.org,"limit":"20"}
        else:
            match = False
        if not ok or not match or time.monotonic() > self.deadline:
            self.blocked += 1
            raise ValueError("SCOPE_BLOCK")
        if consume:
            if self.sent >= 12:
                raise ValueError("READ_BUDGET")
            self.sent += 1

class Pool:
    def __init__(self, scope, backend):
        self.scope, self.backend = scope, backend
    def request(self, method, url, **kw):
        if kw.get("body") is not None or kw.get("encode_multipart"):
            raise ValueError("BODY_BLOCK")
        fields = kw.pop("fields", None)
        if fields:
            url += ("&" if "?" in url else "?") + urlencode(fields)
        self.scope.check(method,url)
        kw.update(redirect=False,retries=False,preload_content=False)
        return self.backend.request(method,url,**kw)

def label(v):
    return v if isinstance(v,str) and re.fullmatch(r"[A-Za-z0-9_.:/ -]{1,100}",v) else None

def boolean(v):
    return v if type(v) is bool else None

def number(v):
    if v is None:
        return {"state":"MISSING","value":None}
    if type(v) not in (int,float) or not math.isfinite(v) or v < 0:
        return {"state":"INVALID","value":None}
    return {"state":"EXPLICIT_ZERO" if v == 0 else "PRESENT","value":v}

def cpu_rows(raw):
    rows = raw.get("accelerator")
    if not isinstance(rows,list):
        raise ValueError("ACCELERATOR_SHAPE")
    result = []
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("ACCELERATOR_ROW")
        res = row.get("resources") or {}
        if not isinstance(res,dict):
            raise ValueError("RESOURCE_SHAPE")
        ids = [row.get(k) for k in ("slug","slugMultiCloud","instanceId")]
        # Candidate selection only: no automatic eligibility assertion.
        if not any(isinstance(x,str) and "cpu" in x.lower() for x in ids) and not (res.get("gpu") in (0,"0") and res.get("cpu") is not None):
            continue
        record = {k:label(row.get(k)) for k in ("slug","slugMultiCloud","instanceId","provider","quotaCheckedAt")}
        record.update({k:boolean(row.get(k)) for k in ("enabled","outOfCapacity","isTierRestricted","nonOndemand","nonSpot")})
        record["prices"] = {k:number(row.get(k)) for k in ("cost","originalCost","spotPrice")}
        record["resources"] = {k:(str(res[k]) if type(res.get(k)) in (int,float,str) and re.fullmatch(r"[0-9.]{1,20}",str(res[k])) else None) for k in ("cpu","gpu","memory")}
        record["exact_cpu4_slug"] = any(x == "cpu-4" for x in ids)
        record["free_eligibility"] = "UNKNOWN"
        result.append(record)
    return {"candidate_count":len(result),"rows":result[:20],"output_truncated":len(result)>20,"catalog_complete":"UNKNOWN"}

def template_summary(raw):
    rows = raw.get("templates")
    if not isinstance(rows,list):
        raise ValueError("TEMPLATE_SHAPE")
    output = []
    for row in rows[:20]:
        if not isinstance(row,dict):
            raise ValueError("TEMPLATE_ROW")
        c = row.get("config") or {}
        if not isinstance(c,dict):
            raise ValueError("TEMPLATE_CONFIG")
        script = c.get("setupScriptText")
        output.append({
            "id":label(row.get("id")),"managedId":label(row.get("managedId")),
            "disabled":boolean(row.get("disabled")),
            "defaultMachine":label(c.get("defaultMachine")),
            "allowedMachines":[label(x) for x in c["allowedMachines"][:20]] if isinstance(c.get("allowedMachines"),list) else None,
            "environmentType":label(c.get("environmentType")),
            "machineImageVersion":label(c.get("machineImageVersion")),
            "setup_script_present":bool(script) if isinstance(script,str) else None,
            "setup_script_sha256":hashlib.sha256(script.encode()).hexdigest() if isinstance(script,str) and script else None,
        })
    return {"returned_count":len(rows),"output_truncated":len(rows)>20,"rows":output,
            "cursor_present":"nextPageToken" in raw,"has_more":bool(raw["nextPageToken"]) if isinstance(raw.get("nextPageToken"),str) else None,
            "catalog_complete":"UNKNOWN","pages_read":1}

def apis():
    from lightning_sdk.lightning_cloud.openapi.api_client import ApiClient
    from lightning_sdk.lightning_cloud.openapi.configuration import Configuration
    from lightning_sdk.lightning_cloud.openapi.api.projects_service_api import ProjectsServiceApi
    from lightning_sdk.lightning_cloud.openapi.api.cloud_space_service_api import CloudSpaceServiceApi
    from lightning_sdk.lightning_cloud.openapi.api.cluster_service_api import ClusterServiceApi
    from lightning_sdk.lightning_cloud.openapi.api.cloud_space_environment_template_service_api import CloudSpaceEnvironmentTemplateServiceApi
    cfg = Configuration()
    cfg.host, cfg.proxy, cfg.verify_ssl, cfg.debug = HOST, None, True, False
    client = ApiClient(cfg)
    return client, ProjectsServiceApi(client), CloudSpaceServiceApi(client), ClusterServiceApi(client), CloudSpaceEnvironmentTemplateServiceApi(client)

def read(method, **kw):
    response = method(**kw,_preload_content=False,_request_timeout=(3,7))
    try:
        data = response.read(CAP+1,decode_content=False)
        if len(data)>CAP:
            raise ValueError("RESPONSE_SIZE")
        obj = json.loads(data)
        if not isinstance(obj,dict):
            raise ValueError("RESPONSE_OBJECT")
        return obj
    finally:
        response.close()
        response.release_conn()

def fixture():
    from unittest.mock import patch
    checks = []
    def check(n,b):
        if not b:raise AssertionError(n)
        checks.append(n)
    def deny(*a,**k):raise AssertionError("NETWORK")
    with patch.object(socket.socket,"connect",deny),patch.object(socket,"getaddrinfo",deny):
        import urllib3
        client, projects, studios, clusters, templates = apis()
        class Fake:
            def __init__(self):self.calls=[]
            def request(self,m,u,**kw):
                self.calls.append((m,u,kw))
                return urllib3.HTTPResponse(body=b"{}",status=200,preload_content=False)
        scope=Scope();scope.org="fixture-org";scope.cluster="fixture-cluster";scope.provider="AWS"
        fake=Fake();client.rest_client.pool_manager=Pool(scope,fake)
        for name,method,kw in [
            ("project",projects.projects_service_get_project,{"id":PROJECT}),
            ("studio",studios.cloud_space_service_get_cloud_space,{"project_id":PROJECT,"id":STUDIO}),
            ("non_global_accelerators",clusters.cluster_service_list_cluster_accelerators,{"id":scope.cluster,"org_id":scope.org}),
        ]:
            check("generated_"+name,read(method,**kw)=={})
        check("all_mock_requests_guarded",len(fake.calls)==3 and all(x[2]["redirect"] is False and x[2]["retries"] is False for x in fake.calls))
        good=HOST+"/v1/projects/"+PROJECT
        for i,(method,url) in enumerate([("POST",good),("DELETE",good),("GET",good+"x"),("GET",good+"?x=1"),("GET",good.replace("https","http")),("GET",good.replace("lightning.ai","other.invalid")),("GET",HOST+"/v1/core/clusters?orgId=other&projectId="+PROJECT),("GET",HOST+"/v1/projects/"+PROJECT+"/secrets"),("GET",HOST+"/v1/keepalive")]):
            try:scope.check(method,url)
            except ValueError:checks.append("scope_reject_"+str(i))
            else:raise AssertionError("BLOCK")
        s=Scope()
        for _ in range(12):s.check("GET",good)
        try:s.check("GET",good)
        except ValueError:checks.append("budget")
        else:raise AssertionError("BUDGET")
        s=Scope();s.deadline=0
        try:s.check("GET",good)
        except ValueError:checks.append("deadline")
        else:raise AssertionError("DEADLINE")
        check("missing_cost",number(None)["state"]=="MISSING")
        check("zero_cost_not_missing",number(0)["state"]=="EXPLICIT_ZERO")
        check("bool_not_price",number(False)["state"]=="INVALID")
        check("string_not_price",number("0")["state"]=="INVALID")
        raw={"accelerator":[{"slug":"cpu-4","cost":0,"resources":{"cpu":"4","gpu":"0"},"token":"sentinel"}]}
        x=cpu_rows(raw);check("exact_cpu4",x["rows"][0]["exact_cpu4_slug"])
        check("free_unknown",x["rows"][0]["free_eligibility"]=="UNKNOWN")
        check("missing_flags_unknown",x["rows"][0]["enabled"] is None)
        check("drop_unlisted_machine_data","sentinel" not in json.dumps(x))
        x=template_summary({"templates":[{"id":"fixture","description":"secret-description","config":{"setupScriptText":"secret-script"}}]})
        check("drop_script_and_description",all(v not in json.dumps(x) for v in ("secret-script","secret-description")))
        check("template_completeness_unknown",x["catalog_complete"]=="UNKNOWN")
        check("template_script_presence",x["rows"][0]["setup_script_present"] is True)
    Path("out").mkdir(exist_ok=True)
    Path("out/g0-account-gate.json").write_text(json.dumps({"status":"PASS","checks":checks,"test_count":len(checks),"platform_requests":0},indent=2))
    print("PASS",len(checks),"account-probe gate checks")

def main():
    report={"kind":"g0_account_read_v1","status":"FAIL","qualification":"NOT_PASSED",
            "started_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "public_url_requests":0,"platform_writes":0,"keepalive_calls":0,"free_parallel_eligibility":"UNKNOWN"}
    scope=Scope();stage="credentials";original=http.client.HTTPConnection.putrequest
    tokens=[]
    def wire(conn,method,url,*args,**kwargs):
        import urllib3.connection
        if not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)) or conn.host!="lightning.ai":
            raise ValueError("WIRE_HOST")
        scope.check(method,HOST+url if url.startswith("/") else url,consume=False)
        return original(conn,method,url,*args,**kwargs)
    def alarm(*args):raise TimeoutError("TOTAL_DEADLINE")
    signal.signal(signal.SIGALRM,alarm);signal.alarm(110)
    try:
        uid,key=(os.environ.get(k,"") for k in ("LIGHTNING_USER_ID","LIGHTNING_API_KEY"))
        if not uid or not key:raise ValueError("MISSING_CREDENTIALS")
        tokens=[uid,key,base64.b64encode((uid+":"+key).encode("ascii")).decode()]
        http.client.HTTPConnection.putrequest=wire
        stage="sdk"
        client,projects,studios,clusters,templates=apis()
        client.set_default_header("Authorization","Basic "+tokens[2])
        client.set_default_header("Accept-Encoding","identity")
        client.rest_client.pool_manager=Pool(scope,client.rest_client.pool_manager)
        stage="project"
        project=read(projects.projects_service_get_project,id=PROJECT)
        if project.get("id")!=PROJECT or project.get("name")!="vision-model" or project.get("ownerType")!="organization":
            raise ValueError("PROJECT_IDENTITY")
        scope.org=label(project.get("ownerId"))
        if not scope.org:raise ValueError("ORG_MISSING")
        report["project_identity_verified"]=True
        report["organization_resolved"]=True
        stage="studio"
        studio=read(studios.cloud_space_service_get_cloud_space,project_id=PROJECT,id=STUDIO)
        if studio.get("id")!=STUDIO or studio.get("name")!="peaceful-dewdney-424" or studio.get("projectId")!=PROJECT:
            raise ValueError("STUDIO_IDENTITY")
        scope.cluster=label(studio.get("clusterId"))
        if not scope.cluster:raise ValueError("CLUSTER_MISSING")
        report["studio_identity_verified"]=True
        # No state classification is inferred from this metadata lookup.
        stage="clusters"
        lists=[read(clusters.cluster_service_list_project_clusters,project_id=PROJECT),
               read(clusters.cluster_service_list_clusters,project_id=PROJECT,org_id=scope.org)]
        matches=[]
        for data in lists:
            if not isinstance(data.get("clusters"),list):raise ValueError("CLUSTER_LIST_SHAPE")
            matches.extend(x for x in data["clusters"] if isinstance(x,dict) and x.get("id")==scope.cluster)
        if not matches:raise ValueError("CLUSTER_UNMATCHED")
        specs=[x.get("spec") for x in matches]
        if not all(isinstance(x,dict) for x in specs) or any(x!=specs[0] for x in specs):
            raise ValueError("CLUSTER_SPEC_AMBIGUOUS")
        spec=specs[0];typ=spec.get("clusterType")
        from lightning_sdk.lightning_cloud.openapi.models.v1_cluster_type import V1ClusterType
        from lightning_sdk.lightning_cloud.openapi.models.v1_cloud_provider import V1CloudProvider
        global_account=typ==V1ClusterType.GLOBAL
        report["cloud_account"]={"id":scope.cluster,"cluster_type":label(typ),"matched_entries":len(matches)}
        stage="cpu_catalog"
        if global_account:
            driver=spec.get("driver")
            if driver==V1CloudProvider.LIGHTNING:
                scope.provider=V1CloudProvider.LIGHTNING_AGGREGATE
            elif driver==V1CloudProvider.DGX:
                scope.provider=V1CloudProvider.DGX
            else:
                providers=[getattr(V1CloudProvider,v) for k,v in (("awsV1","AWS"),("googleCloudV1","GCP"),("lambdaLabsV1","LAMBDA_LABS"),("voltageParkV1","VOLTAGE_PARK"),("nebiusV1","NEBIUS"),("machineV1","MACHINE")) if spec.get(k)]
                if len(providers)!=1:raise ValueError("PROVIDER_AMBIGUOUS")
                scope.provider=providers[0]
            report["cloud_account"]["provider"]=label(scope.provider)
            raw=read(clusters.cluster_service_list_default_cluster_accelerators,project_id=PROJECT,cloud_provider=scope.provider)
        else:
            if typ!=V1ClusterType.BYOC:raise ValueError("CLUSTER_TYPE_UNKNOWN")
            raw=read(clusters.cluster_service_list_cluster_accelerators,id=scope.cluster,org_id=scope.org)
        report["cpu_catalog"]=cpu_rows(raw)
        report["template_catalogs"]={}
        for kind,method in [("managed",templates.cloud_space_environment_template_service_list_managed_cloud_space_environment_templates),("organization",templates.cloud_space_environment_template_service_list_cloud_space_environment_templates)]:
            stage="templates_"+kind
            report["template_catalogs"][kind]=template_summary(read(method,org_id=scope.org,limit=20))
        report["status"]="READS_COMPLETED"
    except Exception as error:
        report.update(failure_stage=stage,error_type=type(error).__name__)
        if type(getattr(error,"status",None)) is int:report["http_status"]=error.status
    finally:
        signal.alarm(0);http.client.HTTPConnection.putrequest=original
        report["network"]={"get_attempts":scope.sent,"blocked":scope.blocked,"max_attempts":12}
        report["ended_at_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
        report["limitations"]=["Point-in-time catalog, not allocation guarantee","No billing balance or paid plan queried","Missing values never mean allowed or free","First template pages only; completeness unknown","No template script execution or resource creation","GET effects on idle detection not proven absent"]
        text=json.dumps(report,indent=2)
        if any(t and t in text for t in tokens):raise RuntimeError("REDACTION_REFUSED")
        Path("out").mkdir(exist_ok=True)
        Path("out/studio-probe.json").write_text(text+"\n")
        print("G0 account read:",report["status"],"stage:",stage,"GET attempts:",scope.sent)
    return 0 if report["status"]=="READS_COMPLETED" else 1

if __name__=="__main__":
    os.environ.update(LIGHTNING_DISABLE_VERSION_CHECK="1",LIGHTNING_DEBUG="0",DO_NOT_TRACK="1")
    logging.disable(logging.CRITICAL)
    if "--self-test" in sys.argv:fixture()
    else:
        with open(os.devnull,"w") as sink,contextlib.redirect_stderr(sink):
            sys.exit(main())
