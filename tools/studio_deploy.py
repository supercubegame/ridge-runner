#!/usr/bin/env python3
"""Reuse the strict SSH probe and send only a fixed, tested deployment program."""
import json
import pathlib
import subprocess
import sys
import urllib.request
import studio_diagnostics
from studio_remote import VERSION, validate_url

probe = studio_diagnostics.probe
original = probe.command
deployment = None

def run(args, **kwargs):
    global deployment
    result = original(args, **kwargs)
    if args[0] != "ssh" or result.returncode or deployment is not None:
        return result
    replies = [x.split("=", 1)[1] for x in result.stdout.splitlines() if x.startswith("RIDGE_PROBE_JSON=")]
    if len(replies) != 1:
        return result
    prereqs = json.loads(replies[0])
    # An occupied port is reviewed by the deployer: reuse only an exact release.
    required = ("linux", "x86_64", "python_compatible", "curl", "disk_1g_available")
    if not all(prereqs.get(k) is True for k in required):
        deployment = {"status": "FAIL", "stage": "prerequisites"}
        return result
    try:
        source = pathlib.Path(__file__).with_name("studio_remote.py").read_text()
        remote = subprocess.run(args[:-1] + ["python3 -"], input=source, capture_output=True,
                                text=True, timeout=200, env=kwargs.get("env"))
        lines = [x.split("=", 1)[1] for x in remote.stdout.splitlines() if x.startswith("RIDGE_DEPLOY_JSON=")]
        if len(lines) != 1:
            deployment = {"status": "FAIL", "stage": "remote_reply", "exit_code": remote.returncode}
        else:
            received = json.loads(lines[0])
            # Only the fixed remote script's structured result is retained, never raw output.
            allowed = {"status", "stage", "checks", "asset_count", "release", "preview_url",
                       "preview_registration", "preview_error_type", "error_type", "error_code"}
            deployment = {k: v for k, v in received.items() if k in allowed}
            if remote.returncode:
                deployment["status"] = "FAIL"
            if deployment.get("preview_url"):
                deployment["preview_url"] = validate_url(deployment["preview_url"])
    except subprocess.TimeoutExpired:
        deployment = {"status": "UNVERIFIED", "stage": "remote_timeout"}
    except Exception as e:
        deployment = {"status": "FAIL", "stage": "remote_reply", "error_type": type(e).__name__}
    return result

def main():
    probe.command = run
    ssh_code = probe.main()
    report = probe.report
    report["deployment"] = deployment or {"status": "NOT_RUN"}
    report["public_http"] = "NOT_VERIFIED"
    if not ssh_code and deployment and deployment.get("status") == "PASS" and deployment.get("preview_url"):
        try:
            url = validate_url(deployment["preview_url"])
            with urllib.request.urlopen(url + "/version.json", timeout=30) as r:
                if r.headers.get_content_type() != "application/json" or json.load(r) != VERSION:
                    raise ValueError("Public endpoint did not return the exact release")
            report["public_http"] = "PASS"
            pathlib.Path("out/preview-url.txt").write_text(url)
        except Exception as error:
            report["public_http_error_type"] = type(error).__name__
    complete = not ssh_code and deployment and deployment.get("status") == "PASS" and report["public_http"] == "PASS"
    report["status"] = "PASS" if complete else "FAIL"
    pathlib.Path("out/studio-probe.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Deployment:", report["deployment"].get("status"), "public HTTP:", report["public_http"])
    return 0 if complete else 1

if __name__ == "__main__":
    sys.exit(main())
