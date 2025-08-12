import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aas_pathfinder import load_machines_from_mongo, upload_aas_documents

class FakeCollection:
    def __init__(self):
        self.calls = []
        self.data = {}

    def replace_one(self, filter, doc, upsert=False):
        self.calls.append((filter, doc, upsert))
        key = filter.get("filename")
        if key:
            self.data[key] = doc

    def find(self):
        return list(self.data.values())

class FakeDB(dict):
    def __getitem__(self, name):
        return self.setdefault(name, FakeCollection())

class FakeClient:
    def __init__(self):
        self.dbs = {}
    def __getitem__(self, name):
        return self.dbs.setdefault(name, FakeDB())

def test_upload_aas_documents(tmp_path):
    sample = {
        "assetAdministrationShells": [
            {
                "id": "aas1",
                "submodels": [
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "sm1"}]}
                ],
            }
        ],
        "submodels": [
            {"id": "sm1", "modelType": "Submodel", "submodelElements": []}
        ],
        "raw": "should be removed"
    }
    (tmp_path / "sample.json").write_text(json.dumps(sample), encoding="utf-8")
    fake_client = FakeClient()
    with mock.patch("aas_pathfinder.MongoClient", return_value=fake_client):
        count = upload_aas_documents(str(tmp_path), "mongodb://localhost", "db", "col")
    assert count == 1
    collection = fake_client["db"]["col"]
    assert collection.calls
    filt, doc, upsert = collection.calls[0]
    assert filt == {"filename": "sample.json"}
    assert "json" in doc and doc["json"]["assetAdministrationShells"]
    assert "raw" not in doc["json"]
    assert "submodels" not in doc["json"]
    aas_submodels = doc["json"]["assetAdministrationShells"][0]["submodels"]
    assert aas_submodels[0]["id"] == "sm1"
    assert upsert is True


def test_upload_then_load(tmp_path):
    sample = {
        "assetAdministrationShells": [
            {
                "id": "aas1",
                "submodels": [
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "Nameplate_aas1"}]},
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "Category_aas1"}]},
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "Operation_aas1"}]},
                ],
            }
        ],
        "submodels": [
            {"id": "Nameplate_aas1", "modelType": "Submodel", "submodelElements": []},
            {"id": "Category_aas1", "modelType": "Submodel", "submodelElements": []},
            {"id": "Operation_aas1", "modelType": "Submodel", "submodelElements": []},
        ],
    }
    (tmp_path / "sample.json").write_text(json.dumps(sample), encoding="utf-8")
    fake_client = FakeClient()
    with mock.patch("aas_pathfinder.MongoClient", return_value=fake_client):
        upload_aas_documents(str(tmp_path), "mongodb://localhost", "db", "col")
        with mock.patch("aas_pathfinder.geocode_address", return_value=(0.0, 0.0)):
            with mock.patch("aas_pathfinder._find_address", return_value="addr"):
                with mock.patch("aas_pathfinder._find_process", return_value="proc"):
                    with mock.patch("aas_pathfinder._find_status", return_value="run"):
                        machines = load_machines_from_mongo("mongodb://localhost", "db", "col")

    assert "aas1" in machines
    machine = machines["aas1"]
    stored = fake_client["db"]["col"].data["sample.json"]["json"]
    assert machine.data == stored
