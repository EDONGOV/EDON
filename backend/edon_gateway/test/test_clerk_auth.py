import json

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from edon_gateway.middleware import auth as auth_module


def _build_token():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "test_kid"
    token = jwt.encode(
        {
            "sub": "user_123",
            "email": "user@example.com",
            "iss": "https://clerk.example",
            "aud": "edon-prod",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    return token, public_jwk


def test_verify_clerk_token_valid(monkeypatch):
    token, public_jwk = _build_token()

    class DummyResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"keys": [public_jwk]}

    def fake_get(*_args, **_kwargs):
        return DummyResp()

    auth_module._JWKS_CACHE["keys"] = None
    auth_module._JWKS_CACHE["fetched_at"] = 0

    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example")
    monkeypatch.setenv("CLERK_AUDIENCE", "edon-prod")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.example/jwks")
    monkeypatch.setattr(auth_module.requests, "get", fake_get)

    claims = auth_module.verify_clerk_token(token)
    assert claims is not None
    assert claims["sub"] == "user_123"


def test_verify_clerk_token_invalid(monkeypatch):
    auth_module._JWKS_CACHE["keys"] = None
    auth_module._JWKS_CACHE["fetched_at"] = 0

    class DummyResp:
        status_code = 404

        def raise_for_status(self):
            raise RuntimeError("not found")

        def json(self):
            return {}

    def fake_get(*_args, **_kwargs):
        return DummyResp()

    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.example/jwks")
    monkeypatch.setattr(auth_module.requests, "get", fake_get)

    claims = auth_module.verify_clerk_token("invalid.token.here")
    assert claims is None
