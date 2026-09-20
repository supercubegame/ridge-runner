"""Extend SDK transport evidence with real-model loss and auth-path checks."""
import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import socket
from unittest.mock import patch

def completion(raw):
    """Do not infer a complete catalog from a model or a missing cursor."""
    if not isinstance(raw, dict) or not isinstance(raw.get("templates"), list):
        return "INVALID"
    if "nextPageToken" not in raw:
        return "UNKNOWN"
    token = raw["nextPageToken"]
    if token == "":
        return "EXPLICIT_END_CANDIDATE"
    if not isinstance(token, str) or not 0 < len(token) <= 2048:
        return "INVALID"
    return "MORE"

def main():
    if any(os.environ.get(k) for k in ("LIGHTNING_USER_ID", "LIGHTNING_API_KEY", "LIGHTNING_AUTH_TOKEN", "GH_TOKEN")):
        raise RuntimeError("FIXTURE_REQUIRES_NO_REAL_CREDENTIALS")
    path = Path("out/studio-probe.json")
    report = json.loads(path.read_text())
    assert report["status"] == "PASS"
    report["status"] = "FAIL"
    checks, attempts = [], []
    def forbidden(*args, **kwargs):
        attempts.append("forbidden")
        raise RuntimeError("FORBIDDEN_SIDE_EFFECT")
    def check(name, result):
        if not result:
            raise AssertionError(name)
        checks.append(name)
    try:
        with patch.object(socket.socket, "connect", forbidden), patch.object(socket, "create_connection", forbidden), patch.object(socket, "getaddrinfo", forbidden):
            from lightning_sdk.lightning_cloud.openapi.api_client import ApiClient
            from lightning_sdk.lightning_cloud.openapi.configuration import Configuration
            from lightning_sdk.lightning_cloud.openapi.models.v1_list_cloud_space_environment_templates_response import V1ListCloudSpaceEnvironmentTemplatesResponse
            from lightning_sdk.lightning_cloud.login import Auth
            import urllib3
            for cls, expected in ((Auth, "3815a32703158c9f8cacc2e50b182783ea317bd7"),
                                  (V1ListCloudSpaceEnvironmentTemplatesResponse, "ae444854d7c7717d4ad828cc13b8a1d9f4af6f38")):
                raw = Path(inspect.getfile(cls)).read_bytes()
                digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                report["source_blobs"][cls.__name__] = digest
                check("exact_source_" + cls.__name__, digest == expected)
            client = ApiClient(Configuration())
            payload = {"templates": [], "nextPageToken": "fixture-next"}
            response = urllib3.HTTPResponse(body=json.dumps(payload).encode(), status=200)
            model = client.deserialize(response, "V1ListCloudSpaceEnvironmentTemplatesResponse")
            check("actual_model_drops_unknown_cursor", model.to_dict() == {"templates": []})
            check("raw_json_preserves_cursor", json.loads(response.data)["nextPageToken"] == "fixture-next")
            check("model_missing_cursor_is_not_complete", completion(model.to_dict()) == "UNKNOWN")
            for name, raw, expected in (
                ("missing", {"templates": []}, "UNKNOWN"),
                ("null", {"templates": [], "nextPageToken": None}, "INVALID"),
                ("empty", {"templates": [], "nextPageToken": ""}, "EXPLICIT_END_CANDIDATE"),
                ("more", payload, "MORE"),
                ("boolean", {"templates": [], "nextPageToken": False}, "INVALID"),
                ("oversize", {"templates": [], "nextPageToken": "x"*2049}, "INVALID"),
                ("shape", {"templates": None}, "INVALID"),
            ):
                check("raw_cursor_" + name, completion(raw) == expected)
            # Pure synthetic values. Explicit env bypass with no disk/browser/token login.
            with patch.object(Auth, "load", forbidden), patch.object(Auth, "save", forbidden), patch.object(Auth, "_run_server", forbidden), patch.object(Auth, "token_login", forbidden):
                auth = Auth(user_id="fixture-user", api_key="fixture-key", auth_token="")
                header = auth.authenticate()
                check("api_key_auth_constructs_basic_without_requests",
                      header == "Basic " + base64.b64encode(b"fixture-user:fixture-key").decode())
                auth.auth_token = "fixture-jwt"
                check("auth_token_has_default_priority", auth.get_auth_header() == "Bearer fixture-jwt")
                check("explicit_api_key_override_avoids_token_priority", auth.get_auth_header(override="api_key") == header)
                client.set_default_header("Authorization", header)
                check("header_set_locally", client.default_headers["Authorization"] == header)
            check("no_network_disk_browser_login_attempts", attempts == [])
        report["status"] = "PASS"
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["failure_hint"] = str(error)[:160]
    finally:
        report["checks"].extend(checks)
        report["test_count"] = len(report["checks"])
        report["response_auth_fixture"] = {"test_count": len(checks), "blocked_side_effect_attempts": len(attempts)}
        report["account_qualification"] = "NOT_RUN"
        report["limitations"] = [
            "Real pinned SDK code with synthetic data and mock pool; no real Lightning request",
            "SDK template model drops unknown fields; absence of cursor does not prove completeness",
            "Original collect_pages helper is a synthetic controller only, not approved for real catalog completeness",
            "Empty nextPageToken is only a candidate ending signal until actual response contract is confirmed",
            "Synthetic auth verifies local header construction, not real credential validity",
            "No account price, quota, org identity or template qualification",
            "Python guards, not OS network isolation",
        ]
        path.write_text(json.dumps(report, indent=2) + "\n")
        print("G0 combined fixture:", report["status"], report["test_count"], "checks")
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
