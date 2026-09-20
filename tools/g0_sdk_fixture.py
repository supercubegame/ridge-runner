"""Credential-free generated SDK + actual REST-layer integration fixture."""
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import socket
from urllib.parse import urlencode

from g0_read_policy import Policy, selftest

PIN = "a7709959692a4abdcd152f381585eb1de826923b"
P, O, C = "fixture-project", "fixture-org", "AWS"

class GuardedPool:
    """Candidate pool adapter: prevent implicit redirect/retry below route guard."""
    def __init__(self, policy, backend):
        self.policy, self.backend = policy, backend
    def request(self, method, url, **kw):
        if kw.get("body") is not None or kw.get("encode_multipart"):
            raise ValueError("BODY_FORBIDDEN")
        fields = kw.pop("fields", None)
        final = url
        if fields:
            final += ("&" if "?" in url else "?") + urlencode(fields)
        self.policy.check(method, final)
        kw["redirect"] = False
        kw["retries"] = False
        return self.backend.request(method, final, **kw)

def collect_pages(fetch, max_pages):
    """Synthetic pagination controller. No real catalog read by this fixture."""
    token, seen, items = None, set(), []
    for _ in range(max_pages):
        page = fetch(token)
        if not isinstance(page, dict) or not isinstance(page.get("templates"), list):
            return {"complete": False, "reason": "SHAPE", "items": items}
        items.extend(page["templates"])
        nxt = page.get("nextPageToken")
        if nxt is None or nxt == "":
            return {"complete": True, "reason": "END", "items": items}
        if not isinstance(nxt, str) or not 0 < len(nxt) <= 2048:
            return {"complete": False, "reason": "TOKEN", "items": items}
        if nxt in seen:
            return {"complete": False, "reason": "REPEATED_TOKEN", "items": items}
        seen.add(nxt)
        token = nxt
    return {"complete": False, "reason": "PAGE_BUDGET", "items": items}

def main():
    if any(os.environ.get(k) for k in ("LIGHTNING_USER_ID", "LIGHTNING_API_KEY", "GH_TOKEN")):
        raise RuntimeError("FIXTURE_REQUIRES_NO_CREDENTIALS")
    os.environ["LIGHTNING_DISABLE_VERSION_CHECK"] = "1"
    os.environ["LIGHTNING_DEBUG"] = "0"
    os.environ["DO_NOT_TRACK"] = "1"
    logging.disable(logging.CRITICAL)
    out = Path("out")
    out.mkdir(exist_ok=True)
    report = {"status": "FAIL", "kind": "g0_sdk_transport_fixture", "sdk_source_sha": PIN,
              "platform_requests": 0, "network_attempts": 0, "account_qualification": "NOT_RUN",
              "checks": [], "source_blobs": {}, "routes": []}
    originals = socket.socket.connect, socket.create_connection, socket.getaddrinfo
    def deny(*args, **kwargs):
        report["network_attempts"] += 1
        raise RuntimeError("NETWORK_FORBIDDEN")
    socket.socket.connect = socket.create_connection = socket.getaddrinfo = deny
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append(name)
    try:
        from lightning_sdk.lightning_cloud.openapi.api_client import ApiClient
        from lightning_sdk.lightning_cloud.openapi.configuration import Configuration
        from lightning_sdk.lightning_cloud.openapi.api.cluster_service_api import ClusterServiceApi
        from lightning_sdk.lightning_cloud.openapi.api.cloud_space_environment_template_service_api import CloudSpaceEnvironmentTemplateServiceApi
        from lightning_sdk.lightning_cloud.openapi.rest import RESTClientObject, ApiException
        import urllib3
        for cls, expected in ((ApiClient, "4e2d72cc5b560d704a5286489f0a18ba86bd6eac"),
                              (RESTClientObject, "7e774cfc32006586a63de1ee1298e66434f08566"),
                              (ClusterServiceApi, None), (CloudSpaceEnvironmentTemplateServiceApi, None)):
            raw = Path(inspect.getfile(cls)).read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            report["source_blobs"][cls.__name__] = blob
            if expected:
                check("exact_source_" + cls.__name__, blob == expected)
        report["checks"].extend("policy_" + name for name in selftest())
        class FakePool:
            def __init__(self, status=200):
                self.calls, self.status = [], status
            def request(self, method, url, **kw):
                self.calls.append((method, url, kw))
                return urllib3.HTTPResponse(body=b"{}", status=self.status,
                    headers={"Location": "https://other.invalid/redirect"} if self.status == 302 else {},
                    preload_content=False)
        cfg = Configuration()
        cfg.host = "https://lightning.ai"
        cfg.proxy = None
        cfg.verify_ssl = True
        cfg.debug = False
        client = ApiClient(cfg)
        clusters = ClusterServiceApi(client)
        templates = CloudSpaceEnvironmentTemplateServiceApi(client)
        opts = {"_preload_content": False, "_request_timeout": (3, 5)}
        calls = [
            (clusters.cluster_service_list_project_clusters, {"project_id": P}, "/v1/projects/" + P + "/clusters"),
            (clusters.cluster_service_list_clusters, {"project_id": P, "org_id": O}, "/v1/core/clusters"),
            (clusters.cluster_service_list_default_cluster_accelerators, {"project_id": P, "cloud_provider": C}, "/v1/core/accelerators"),
            (templates.cloud_space_environment_template_service_list_cloud_space_environment_templates, {"org_id": O, "limit": 20}, "/v1/cloudspaces/environment-templates"),
            (templates.cloud_space_environment_template_service_list_managed_cloud_space_environment_templates, {"org_id": O, "limit": 20, "page_token": "fixture +/="}, "/v1/cloudspaces/environment-templates/managed"),
        ]
        # Observe stock REST behavior without ever creating a socket.
        raw_pool = FakePool()
        client.rest_client.pool_manager = raw_pool
        calls[0][0](**calls[0][1], **opts)
        check("stock_rest_no_explicit_redirect_retry_flags",
              len(raw_pool.calls) == 1 and
              "redirect" not in raw_pool.calls[0][2] and "retries" not in raw_pool.calls[0][2])
        for index, (method, args, path) in enumerate(calls):
            backend = FakePool()
            client.rest_client.pool_manager = GuardedPool(Policy(P, O, C), backend)
            result = method(**args, **opts)
            check("generated_route_" + str(index), result.status == 200 and len(backend.calls) == 1
                  and backend.calls[0][0] == "GET" and backend.calls[0][1].split("?")[0] == cfg.host + path)
            kw = backend.calls[0][2]
            check("transport_flags_" + str(index), kw["redirect"] is False and kw["retries"] is False
                  and kw["timeout"].connect_timeout == 3 and kw["timeout"].read_timeout == 5)
            report["routes"].append({"method": method.__name__, "fixture_url": backend.calls[0][1]})
        for status in (302, 429, 503):
            backend = FakePool(status)
            client.rest_client.pool_manager = GuardedPool(Policy(P, O, C), backend)
            try:
                calls[0][0](**calls[0][1], **opts)
            except ApiException as error:
                check("http_" + str(status) + "_single_backend_attempt", error.status == status and len(backend.calls) == 1
                      and backend.calls[0][2]["redirect"] is False and backend.calls[0][2]["retries"] is False)
            else:
                raise AssertionError("HTTP_FAILURE_NOT_REJECTED")
        bad = [
            ("POST", cfg.host + "/v1/projects/" + P + "/clusters", {}),
            ("DELETE", cfg.host + "/v1/projects/" + P + "/clusters", {}),
            ("GET", "https://other.invalid/v1/projects/" + P + "/clusters", {}),
            ("GET", cfg.host + "/v1/core/clusters", {"fields": [("projectId", P), ("orgId", "other")]}),
            ("GET", cfg.host + "/v1/core/clusters?projectId=" + P, {"fields": [("projectId", P), ("orgId", O)]}),
            ("GET", cfg.host + "/v1/keepalive", {}),
            ("GET", cfg.host + "/v1/projects/" + P + "/clusters", {"body": "{}"}),
        ]
        for index, (method, url, kw) in enumerate(bad):
            backend = FakePool()
            guard = GuardedPool(Policy(P, O, C), backend)
            try:
                guard.request(method, url, **kw)
            except ValueError:
                check("adapter_block_" + str(index), not backend.calls)
            else:
                raise AssertionError("UNSAFE_ACCEPTED")
        backend = FakePool()
        client.rest_client.pool_manager = GuardedPool(Policy(P, O, C, max_reads=1), backend)
        calls[0][0](**calls[0][1], **opts)
        try:
            calls[0][0](**calls[0][1], **opts)
        except ValueError:
            check("generated_call_budget", len(backend.calls) == 1)
        else:
            raise AssertionError("BUDGET_NOT_ENFORCED")
        check("pagination_complete", collect_pages(lambda t: {"templates": [], "nextPageToken": "n" if t is None else ""}, 2)["complete"])
        check("pagination_budget_incomplete", collect_pages(lambda t: {"templates": [], "nextPageToken": "n"}, 1)["reason"] == "PAGE_BUDGET")
        check("pagination_repeat_incomplete", collect_pages(lambda t: {"templates": [], "nextPageToken": "n"}, 3)["reason"] == "REPEATED_TOKEN")
        check("pagination_invalid_token", collect_pages(lambda t: {"templates": [], "nextPageToken": 1}, 3)["reason"] == "TOKEN")
        check("pagination_invalid_shape", collect_pages(lambda t: {"templates": None}, 3)["reason"] == "SHAPE")
        check("zero_network_attempts", report["network_attempts"] == 0)
        report["status"] = "PASS"
    except Exception as error:
        report["error_type"] = type(error).__name__
        # No credentials or real responses exist in this fixture; keep failure terse.
        report["failure_hint"] = str(error)[:200]
    finally:
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = originals
        report["test_count"] = len(report["checks"])
        report["limitations"] = [
            "Synthetic data and pool backend; no real Lightning HTTP request",
            "No account authentication, org resolution, price, quota or template qualification",
            "Candidate Python guard, not OS network isolation",
            "Pagination response field remains subject to real response schema verification",
        ]
        (out / "studio-probe.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
