"""Phone mode: PIN gate for other devices, this PC always allowed, lockout."""
import pytest

import phone_access
import web_server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(phone_access, "SETTINGS_FILE", tmp_path / "phone.json")
    phone_access._fails.clear()
    return web_server.app.test_client()


def test_this_pc_needs_no_pin(client):
    r = client.get("/api/phone", environ_base={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200 and len(r.get_json()["pin"]) == 6


def test_phone_must_type_pin(client):
    phone = {"REMOTE_ADDR": "192.168.1.50"}
    assert client.get("/", environ_base=phone).status_code == 302
    assert client.get("/api/research", environ_base=phone).status_code == 401
    r = client.post("/phone-login", data={"pin": "000000" if phone_access.load()["pin"] != "000000" else "111111"}, environ_base=phone)
    assert b"Wrong PIN" in r.data
    r = client.post("/phone-login", data={"pin": phone_access.load()["pin"]}, environ_base=phone)
    assert r.status_code == 302
    assert client.get("/api/research", environ_base=phone).status_code == 200
    assert client.get("/api/phone", environ_base=phone).status_code == 403  # settings only on the PC


def test_lockout_after_five_wrong(client):
    addr = "192.168.1.77"
    for _ in range(5):
        phone_access.check_pin(addr, "x")
    assert phone_access.locked(addr)
    assert not phone_access.check_pin(addr, phone_access.load()["pin"])


def test_new_pin_logs_phones_out(client):
    old = phone_access.token()
    phone_access.new_pin()
    assert phone_access.token() != old
