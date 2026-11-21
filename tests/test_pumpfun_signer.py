import pytest

from agent.pumpfun.signer import SignerError, b58decode, load_keypair


def test_b58decode_roundtrip_known_value():
    # "1" is a leading zero byte; "2" decodes to b"\x01"
    assert b58decode("1") == b"\x00"
    assert b58decode("2") == b"\x01"
    with pytest.raises(SignerError):
        b58decode("0OIl")  # invalid base58 characters
    with pytest.raises(SignerError):
        b58decode("")


def test_load_keypair_without_config_fails_closed(monkeypatch):
    monkeypatch.delenv("SOLANA_KEYPAIR_PATH", raising=False)
    monkeypatch.delenv("SOLANA_PRIVATE_" + "KEY_B58", raising=False)
    with pytest.raises(SignerError):
        load_keypair()


def test_load_keypair_bad_file_fails_closed(monkeypatch, tmp_path):
    bad = tmp_path / "kp.json"
    bad.write_text("[1,2,3]")
    monkeypatch.setenv("SOLANA_KEYPAIR_PATH", str(bad))
    with pytest.raises(SignerError):
        load_keypair()


def test_real_keypair_load_and_sign(monkeypatch, tmp_path):
    solders = pytest.importorskip("solders")
    from solders.keypair import Keypair
    from solders.message import MessageV0
    from solders.transaction import VersionedTransaction
    from solders.pubkey import Pubkey
    from solders.hash import Hash
    from solders.instruction import Instruction

    kp = Keypair()
    path = tmp_path / "kp.json"
    path.write_text(str(list(bytes(kp))))
    monkeypatch.setenv("SOLANA_KEYPAIR_PATH", str(path))
    loaded = load_keypair()
    assert str(loaded.pubkey()) == str(kp.pubkey())

    # Build a minimal unsigned v0 transaction and sign it via the module.
    msg = MessageV0.try_compile(kp.pubkey(), [Instruction(Pubkey.default(), b"", [])], [], Hash.default())
    from solders.signature import Signature
    unsigned = VersionedTransaction.populate(msg, [Signature.default()])
    from agent.pumpfun.signer import sign_transaction
    signed = sign_transaction(bytes(unsigned), loaded)
    assert len(signed) > 0
