import pytest
from cryptography.fernet import Fernet

from woassi.shared.application.ports import SecretDecryptionError
from woassi.shared.infrastructure.crypto import FernetSecretCipher


def new_key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip() -> None:
    cipher = FernetSecretCipher([new_key()])
    secret = "EAAG-meta-token-é"
    encrypted = cipher.encrypt(secret)
    assert secret not in encrypted
    assert cipher.decrypt(encrypted) == secret


def test_same_secret_gives_different_ciphertexts() -> None:
    cipher = FernetSecretCipher([new_key()])
    assert cipher.encrypt("x") != cipher.encrypt("x")


def test_rotation_keeps_old_values_readable() -> None:
    old, new = new_key(), new_key()
    encrypted_before = FernetSecretCipher([old]).encrypt("token")

    rotated = FernetSecretCipher([new, old])

    assert rotated.decrypt(encrypted_before) == "token"


def test_new_values_use_the_first_key() -> None:
    old, new = new_key(), new_key()
    encrypted = FernetSecretCipher([new, old]).encrypt("token")

    assert FernetSecretCipher([new]).decrypt(encrypted) == "token"
    with pytest.raises(SecretDecryptionError):
        FernetSecretCipher([old]).decrypt(encrypted)


def test_rotate_lets_the_old_key_be_dropped() -> None:
    old, new = new_key(), new_key()
    encrypted = FernetSecretCipher([old]).encrypt("token")

    reencrypted = FernetSecretCipher([new, old]).rotate(encrypted)

    assert FernetSecretCipher([new]).decrypt(reencrypted) == "token"


@pytest.mark.parametrize("ciphertext", ["", "not-a-token"])
def test_invalid_ciphertext(ciphertext: str) -> None:
    with pytest.raises(SecretDecryptionError):
        FernetSecretCipher([new_key()]).decrypt(ciphertext)


def test_a_key_is_required() -> None:
    with pytest.raises(ValueError):
        FernetSecretCipher([])


def test_malformed_key_fails_at_startup() -> None:
    with pytest.raises(ValueError):
        FernetSecretCipher(["too-short"])
