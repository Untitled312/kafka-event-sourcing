import hashlib
import json
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import structlog

log = structlog.get_logger()

_SIGNING_KEY: Ed25519PrivateKey | None = None


def _get_signing_key() -> Ed25519PrivateKey:
    global _SIGNING_KEY
    if _SIGNING_KEY is None:
        key_env = os.getenv("ED25519_PRIVATE_KEY")
        if key_env:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            _SIGNING_KEY = load_pem_private_key(key_env.encode(), password=None)
        else:
            _SIGNING_KEY = Ed25519PrivateKey.generate()
            pub_hex = _SIGNING_KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
            log.warning("dev_mode_ed25519_key_generated", public_key_hex=pub_hex)
    return _SIGNING_KEY


def compute_hash(prev_hash: bytes, action: str, payload: dict) -> bytes:
    try:
        payload_canonical = json.dumps(
            payload,
            sort_keys=True,          
            separators=(',', ':'),   
            ensure_ascii=False      
        )
    except (TypeError, ValueError) as e:
        log.error("payload_serialization_failed", payload_type=type(payload).__name__, error=str(e))
        raise
    
    payload_bytes = payload_canonical.encode('utf-8')
    action_bytes = action.encode('utf-8')
    
    data = prev_hash + payload_bytes + action_bytes
    return hashlib.sha256(data).digest()


def sign_event(data: bytes) -> bytes:
    key = _get_signing_key()
    signature = key.sign(data)
    
    if len(signature) != 64:
        log.critical("ed25519_signature_length_mismatch", got=len(signature), expected=64)
        raise ValueError(f"Ed25519 signature must be exactly 64 bytes, got {len(signature)}")
    
    return signature


def verify_signature(public_key_bytes: bytes, data: bytes, signature: bytes) -> bool:
    try:
        pub_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        pub_key.verify(signature, data)
        return True
    except Exception as e:
        log.debug("signature_verification_failed", error=str(e))
        return False


def get_public_key_hex() -> str:
    key = _get_signing_key().public_key()
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()