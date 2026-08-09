import hashlib
import hmac

from app.services.webhooks import canonical_payload, event_matches, sign_payload


def test_event_patterns() -> None:
    assert event_matches(["release.*"], "release.deployed")
    assert event_matches(["release.failed"], "release.failed")
    assert event_matches(["*"], "project.created")
    assert not event_matches(["release.deployed"], "release.failed")


def test_signature_uses_canonical_json_and_hmac_sha256() -> None:
    payload = canonical_payload({"z": 1, "a": "value"})
    assert payload == b'{"a":"value","z":1}'
    expected = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    assert sign_payload("secret", payload) == f"sha256={expected}"
