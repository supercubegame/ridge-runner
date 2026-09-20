"""No-credential gate driver: use actual stream-backed fake HTTP responses."""
import io
import logging
import os
from unittest.mock import patch
for name in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY','LIGHTNING_AUTH_TOKEN','GH_TOKEN'):
    if os.environ.get(name):
        raise RuntimeError('GATE_REQUIRES_NO_CREDENTIALS')
os.environ.update(LIGHTNING_DISABLE_VERSION_CHECK='1',LIGHTNING_DEBUG='0',DO_NOT_TRACK='1')
logging.disable(logging.CRITICAL)
import urllib3
import g0_account_read as probe

# urllib3 HTTPResponse(body=bytes) caches .data but has no stream for .read().
# Convert only the fixture body to BytesIO; never wrap production responses.
original = urllib3.HTTPResponse
def stream_response(*args, **kwargs):
    body = kwargs.get('body')
    if isinstance(body, bytes):
        kwargs['body'] = io.BytesIO(body)
    return original(*args, **kwargs)
with patch.object(urllib3, 'HTTPResponse', stream_response):
    probe.fixture()
