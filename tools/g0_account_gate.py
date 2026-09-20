"""No-credential gate driver with stream-backed fake HTTP responses."""
import io
import json
import logging
import os
from pathlib import Path
from unittest.mock import patch
for name in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY','LIGHTNING_AUTH_TOKEN','GH_TOKEN'):
    if os.environ.get(name):
        raise RuntimeError('GATE_REQUIRES_NO_CREDENTIALS')
os.environ.update(LIGHTNING_DISABLE_VERSION_CHECK='1',LIGHTNING_DEBUG='0',DO_NOT_TRACK='1')
logging.disable(logging.CRITICAL)
import urllib3
import g0_account_read as probe
original = urllib3.HTTPResponse
def stream_response(*args, **kwargs):
    if isinstance(kwargs.get('body'), bytes):
        kwargs['body'] = io.BytesIO(kwargs['body'])
    return original(*args, **kwargs)
try:
    with patch.object(urllib3, 'HTTPResponse', stream_response):
        probe.fixture()
except Exception as error:
    # Synthetic gate only: no account credentials or platform responses exist here.
    Path('out').mkdir(exist_ok=True)
    Path('out/studio-probe.json').write_text(json.dumps({'kind':'g0_account_gate_failure','status':'FAIL','account_qualification':'NOT_RUN','platform_requests':0,'error_type':type(error).__name__,'failure_hint':str(error)[:200]},indent=2))
    raise
