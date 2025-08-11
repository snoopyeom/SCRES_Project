import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def simplify_aas_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """AAS JSON 문서를 MongoDB 저장용 간결한 구조로 변환한다.

    - 최상위 ``raw`` 필드를 제거한다.
    - 최상위 ``submodels`` 배열에서 ID->Submodel 사전을 구성한다.
    - 각 AAS의 ``submodels``가 ModelReference인 경우 실제 Submodel 객체로 대체한다.
    - 중복 정의/참조된 Submodel은 첫 번째만 유지하고 나머지는 경고 후 무시한다.
    - 참조만 있고 실체가 없는 Submodel은 경고를 남기고 스킵한다.
    """
    # ``raw`` 제거
    doc = {k: v for k, v in doc.items() if k != "raw"}

    # 최상위 submodels 매핑
    top_submodels = doc.pop("submodels", []) or []
    submodel_map: Dict[str, Dict[str, Any]] = {}
    for sm in top_submodels:
        if not isinstance(sm, dict):
            continue
        sm_id = sm.get("id")
        if not sm_id:
            logger.warning("⚠️ ID가 없는 Submodel 정의 무시")
            continue
        if sm_id in submodel_map:
            logger.warning("⚠️ 중복 Submodel ID %s 무시", sm_id)
            continue
        submodel_map[sm_id] = sm

    aas_list = doc.get("assetAdministrationShells", [])
    if not isinstance(aas_list, list):
        return doc

    for aas in aas_list:
        if not isinstance(aas, dict):
            continue
        sm_entries = aas.get("submodels", []) or []
        new_submodels: List[Dict[str, Any]] = []
        seen_ids = set()
        for entry in sm_entries:
            submodel_obj = None
            if isinstance(entry, dict) and entry.get("type") == "ModelReference":
                submodel_id = None
                for key in entry.get("keys", []):
                    if key.get("type") == "Submodel":
                        submodel_id = key.get("value")
                        break
                if submodel_id:
                    submodel_obj = submodel_map.get(submodel_id)
                    if submodel_obj is None:
                        logger.warning("⚠️ 참조된 Submodel %s 미존재", submodel_id)
                else:
                    logger.warning("⚠️ ModelReference에 Submodel key 없음")
            elif isinstance(entry, dict) and entry.get("id"):
                # 이미 Submodel 객체인 경우
                submodel_obj = entry
            else:
                logger.warning("⚠️ 알 수 없는 submodel 항목 무시: %s", entry)
            if submodel_obj is None:
                continue
            sm_id = submodel_obj.get("id")
            if sm_id in seen_ids:
                logger.warning("⚠️ 중복 Submodel 참조 %s 무시", sm_id)
                continue
            seen_ids.add(sm_id)
            new_submodels.append(submodel_obj)
        aas["submodels"] = new_submodels

    return doc
