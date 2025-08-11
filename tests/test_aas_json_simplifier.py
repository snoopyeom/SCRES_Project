import sys
import os
import logging

# 테스트 환경에서 루트 경로를 import 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from aas_json_simplifier import simplify_aas_document


def test_simplify_aas_document(caplog):
    caplog.set_level(logging.WARNING)
    doc = {
        "filename": "sample.json",
        "assetAdministrationShells": [
            {
                "id": "aas1",
                "submodels": [
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "sm1"}]},
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "missing"}]},
                    {"id": "sm2", "modelType": "Submodel", "submodelElements": []},
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": "sm1"}]},
                ],
            }
        ],
        "submodels": [
            {"id": "sm1", "modelType": "Submodel", "submodelElements": [1]},
            {"id": "sm1", "modelType": "Submodel", "submodelElements": [2]},
            {"id": "sm2", "modelType": "Submodel", "submodelElements": []},
        ],
        "raw": "{}",
    }

    simplified = simplify_aas_document(doc)

    # raw과 최상위 submodels 제거
    assert "raw" not in simplified
    assert "submodels" not in simplified

    # AAS 내 submodels는 실제 Submodel 객체로 대체되고 중복 제거됨
    aas_submodels = simplified["assetAdministrationShells"][0]["submodels"]
    assert len(aas_submodels) == 2
    assert aas_submodels[0]["id"] == "sm1"
    assert aas_submodels[0]["submodelElements"] == [1]
    assert aas_submodels[1]["id"] == "sm2"

    # 존재하지 않는 참조는 경고 후 스킵됨
    assert any("missing" in rec.message for rec in caplog.records)
