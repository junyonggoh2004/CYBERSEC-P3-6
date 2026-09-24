"""Optional hybrid encryption of the complete signed container (ENC1)."""
import io
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .payload import BuiltContainer, VerificationError

MAGIC = b"ENC1"
ALGORITHM = "AES-256-GCM + RSA-OAEP-SHA256"


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def encrypt(container, public_pem):
    key = serialization.load_pem_public_key(public_pem)
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
        raise ValueError("Bob's encryption public key must be RSA, at least 2048 bits.")
    secret, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    wrapped = key.encrypt(secret, oaep())
    header = MAGIC + len(wrapped).to_bytes(2, "big") + wrapped + nonce
    ciphertext = AESGCM(secret).encrypt(nonce, container.raw, header)
    body = header[4:] + ciphertext
    parts = [MAGIC, len(body).to_bytes(4, "big"), body]
    return BuiltContainer(b"".join(parts), parts, container.metadata,
                          container.payload_hash_hex, container.signature_hex)


class PlainStream(io.BytesIO):
    def __init__(self, data, depth):
        super().__init__(data)
        self.num_lsb = depth

    def read(self, size=-1):
        data = super().read(size)
        if size >= 0 and len(data) != size:
            raise ValueError("Truncated decrypted package.")
        return data


def unwrap(stream, private_pem):
    """Return the original stream for signed-only V1/V2 containers."""
    marker = stream.read(4)
    stream.pos_units = 0
    if marker != MAGIC:
        return stream, "Not applicable"
    if not private_pem:
        raise VerificationError("Cannot Verify", "This package is encrypted. Enable decryption and supply Bob's private encryption key.", "DECRYPTION_KEY_REQUIRED")
    try:
        stream.read(4)
        body = stream.read(int.from_bytes(stream.read(4), "big"))
        key = serialization.load_pem_private_key(private_pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("Invalid RSA private key")
        size = int.from_bytes(body[:2], "big")
        if size != key.key_size // 8 or len(body) < 2 + size + 12 + 16:
            raise ValueError("Invalid encrypted envelope")
        wrapped, nonce = body[2:2 + size], body[2 + size:14 + size]
        secret = key.decrypt(wrapped, oaep())
        plain = AESGCM(secret).decrypt(nonce, body[14 + size:], MAGIC + body[:14 + size])
        return PlainStream(plain, stream.num_lsb), "Passed"
    except Exception as exc:
        raise VerificationError("Cannot Verify", "Decryption failed. Bob's private key may be wrong, or the encrypted package may be damaged. No content was released.", "DECRYPTION_FAILED") from exc
