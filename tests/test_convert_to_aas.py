import sys
import os

# 🔥 경로 먼저 추가해줘야 아래 import가 작동함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import types
import importlib
import convert_to_aas

class Dummy:
    def __init__(self, id=None, identification=None, id_short=None):
        self.id = id
        self.identification = identification
        self.id_short = id_short

def make_fake_aas(identifier):
    fake = types.SimpleNamespace()
    fake.Identifier = identifier
    return fake

def test_ident_class(monkeypatch):
    class Identifier:
        def __init__(self, id, id_type):
            self.id = id
            self.id_type = id_type
    fake_aas = make_fake_aas(Identifier)
    monkeypatch.setattr(convert_to_aas, "aas", fake_aas)

    ident = convert_to_aas._ident("foo")
    assert isinstance(ident, Identifier)
    assert ident.id == "foo"
    assert ident.id_type == "Custom"

    obj = convert_to_aas._create(Dummy, id_short="x", identification=ident)
    assert isinstance(obj, Dummy)
    assert obj.identification is ident


def test_ident_str_alias(monkeypatch):
    fake_aas = make_fake_aas(str)
    monkeypatch.setattr(convert_to_aas, "aas", fake_aas)

    ident = convert_to_aas._ident("bar")
    assert ident == "bar"

    obj = convert_to_aas._create(Dummy, id_short="x", identification=ident)
    assert isinstance(obj, Dummy)
    assert obj.identification == "bar"
