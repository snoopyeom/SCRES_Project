import json
import types
import builtins
from pathlib import Path
from unittest import mock
from aas_pathfinder import upload_aas_documents

class FakeCollection:
    def __init__(self):
        self.calls = []
    def replace_one(self, filter, doc, upsert=False):
        self.calls.append((filter, doc, upsert))

class FakeDB(dict):
    def __getitem__(self, name):
        return self.setdefault(name, FakeCollection())

class FakeClient:
    def __init__(self):
        self.dbs = {}
    def __getitem__(self, name):
        return self.dbs.setdefault(name, FakeDB())

def test_upload_aas_documents(tmp_path):
    sample = {"foo": "bar"}
    (tmp_path / "sample.json").write_text(json.dumps(sample), encoding="utf-8")
    fake_client = FakeClient()
    with mock.patch("aas_pathfinder.MongoClient", return_value=fake_client):
        count = upload_aas_documents(str(tmp_path), "mongodb://localhost", "db", "col")
    assert count == 1
    collection = fake_client["db"]["col"]
    assert collection.calls
    filt, doc, upsert = collection.calls[0]
    assert filt == {"filename": "sample.json"}
    assert doc["json"] == sample
    assert doc["raw"] == json.dumps(sample)
    assert upsert is True
