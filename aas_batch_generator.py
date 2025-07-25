import os
import pandas as pd
import re
from basyx.aas import model
from basyx.aas.model import (
    datatypes,
    MultiLanguageProperty,
    Submodel,
    SubmodelElementCollection,
    Property,
    AssetInformation,
    AssetAdministrationShell,
    ModelReference
)
from basyx.aas.model.base import LangStringSet
from basyx.aas.model.provider import DictObjectStore
from basyx.aas.adapter.json import write_aas_json_file


def sanitize_id_short(s: str) -> str:
    s = re.sub(r'[^A-Za-z0-9_]', '_', str(s))
    if not re.match(r'^[A-Za-z]', s):
        s = "X_" + s
    return s

from basyx.aas.model.base import KeyTypes


def _infer_ref_class(key_type: KeyTypes):
    """Map ``KeyTypes`` to the corresponding basyx model class."""
    return {
        KeyTypes.SUBMODEL: model.Submodel,
        KeyTypes.SUBMODELELEMENT: model.SubmodelElement,
        KeyTypes.PROPERTY: model.Property,
    }.get(key_type, model.Referable)


def ref_from_keys(keys):
    """Return a ``ModelReference`` built from ``keys``.

    ``basyx`` 버전마다 ``ModelReference`` 초기화 방식이 달라 이를 호환하기
    위해 사용되는 헬퍼 함수이다. ``ModelReference.from_keys``가 존재하면 그걸
    사용하고, 그렇지 않은 경우에는 타입을 추정하여 ``ModelReference``를 직접
    생성한다.
    """
    if hasattr(ModelReference, "from_keys"):
        return ModelReference.from_keys(keys)

    ref_cls = _infer_ref_class(keys[-1].type_)
    return ModelReference(tuple(keys), ref_cls)

def mlp(id_short: str, text: str, lang: str = 'en') -> MultiLanguageProperty:
    return MultiLanguageProperty(id_short=id_short, value=LangStringSet({lang: str(text)}))


# 1. 데이터 로딩
folder = "./데이터(정리본)"
output_folder = "./aas_instances"
os.makedirs(output_folder, exist_ok=True)

files = {
    "단조": "공작기계_단조.csv",
    "밀링": "공작기계_밀링.csv",
    "선반": "공작기계_선반.csv",
    "그라인더": "공작기계_그라인더.csv"
}

dfs = {}
for name, fname in files.items():
    path = os.path.join(folder, fname)
    try:
        df = pd.read_csv(path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding='cp949')
    df["_category"] = name
    dfs[name] = df

df_all = pd.concat(dfs.values(), ignore_index=True)


# 2. Submodel 생성 함수들
def make_nameplate_submodel(row, uid) -> Submodel:
    sm = Submodel(id_=f"https://example.com/submodel/Nameplate_{uid}")
    address = SubmodelElementCollection(
        id_short="AddressInformation",
        value=[
            mlp("Street", row.get("Location", "N/A")),
            mlp("Zipcode", "00000"),
            mlp("CityTown", "N/A"),
            mlp("NationalCode", "KR")
        ]
    )
    for elem in [
        Property(id_short="URIOfTheProduct", value_type=datatypes.String, value="http://example.com/product"),
        mlp("ManufacturerName", row.get("Brand", "Unknown")),
        mlp("ManufacturerProductDesignation", row.get("name", "Unnamed")),
        address,
        Property(id_short="OrderCodeOfManufacturer", value_type=datatypes.String, value="NA"),
        Property(id_short="SerialNumber", value_type=datatypes.String, value=row.get("Equipment", "NoID")),
        Property(id_short="YearOfConstruction", value_type=datatypes.String, value="2024")
    ]:
        sm.submodel_element.add(elem)
    return sm


def make_category_submodel(row, uid) -> Submodel:
    sm = Submodel(id_=f"https://example.com/submodel/Category_{uid}")
    for elem in [
        Property(id_short="MachineType", value_type=datatypes.String, value=row.get("_category", "Unknown")),
        Property(id_short="MachineRole", value_type=datatypes.String, value="Production")
    ]:
        sm.submodel_element.add(elem)
    return sm


def make_operation_submodel(uid) -> Submodel:
    sm = Submodel(id_=f"https://example.com/submodel/Operation_{uid}")
    for elem in [
        Property(id_short="MachineStatus", value_type=datatypes.String, value="Running"),
        Property(id_short="ProcessOrder", value_type=datatypes.Int, value=1),
        Property(id_short="ProcessID", value_type=datatypes.String, value="P001"),
        Property(id_short="ReplacedAASID", value_type=datatypes.String, value="None"),
        Property(id_short="Candidate", value_type=datatypes.Boolean, value=True),
        Property(id_short="Selected", value_type=datatypes.Boolean, value=False)
    ]:
        sm.submodel_element.add(elem)
    return sm


def make_technicaldata_submodel(row, uid) -> Submodel:
    sm = Submodel(id_=f"https://example.com/submodel/TechnicalData_{uid}")
    proc = sanitize_id_short(row["_category"])
    tech_data = SubmodelElementCollection(id_short=f"{proc}_TechnicalPropertyAreas", value=[])

    for col, val in row.items():
        if col not in {"Type", "Equipment", "name", "Brand", "Location", "Company", "_category"} and pd.notna(val):
            col_clean = sanitize_id_short(col.replace(" ", "_"))
            tech_data.value.add(Property(id_short=col_clean, value_type=datatypes.String, value=str(val)))

    sm.submodel_element.add(tech_data)
    return sm


def make_documentation_submodel(uid) -> Submodel:
    sm = Submodel(id_=f"https://example.com/submodel/HandoverDocumentation_{uid}")
    sm.submodel_element.add(SubmodelElementCollection(
        id_short="Document",
        value=[
            Property(id_short="FileName", value_type=datatypes.String, value="manual.pdf")
        ]
    ))
    return sm


def make_mqttbroker_submodel(uid) -> Submodel:
    """Create MQTT broker configuration submodel."""
    sm = Submodel(id_=f"https://example.com/submodel/MQTTBrokerConfig_{uid}", id_short="MQTTBrokerConfig")
    for elem in [
        Property(id_short="Address", value_type=datatypes.String, value="mqtt://broker.hivemq.com"),
        Property(id_short="Topic", value_type=datatypes.String, value=f"aas/status/{uid}")
    ]:
        sm.submodel_element.add(elem)
    return sm


def make_event_submodel(uid) -> Submodel:
    """Create BasicEventElement submodel for machine status changes."""
    sm = Submodel(id_=f"https://example.com/submodel/StatusEvent_{uid}")
    event = model.BasicEventElement(
        id_short="StatusChangeEvent",
        observed=ref_from_keys([
            model.Key(type_=model.KeyTypes.SUBMODEL, value=f"https://example.com/submodel/Operation_{uid}"),
            model.Key(type_=model.KeyTypes.PROPERTY, value="MachineStatus"),
        ]),
        direction="output",
        state="on",
        message_topic=f"aas/status/{uid}",
        message_broker=ref_from_keys([
            model.Key(type_=model.KeyTypes.SUBMODEL, value=f"https://example.com/submodel/MQTTBrokerConfig_{uid}")
        ]),
        min_interval="PT1S",
    )
    sm.submodel_element.add(event)
    return sm


# 3. AAS 인스턴스 생성 및 개별 JSON 저장
for i, row in df_all.iterrows():
    equipment_id_raw = str(row["Equipment"])
    equipment_id = sanitize_id_short(equipment_id_raw)
    uid = f"{equipment_id}_{i}"

    aas_id = f"https://example.com/aas/{uid}"
    asset_id = f"http://example.com/asset/{uid}"

    submodels = [
        make_nameplate_submodel(row, uid),
        make_category_submodel(row, uid),
        make_operation_submodel(uid),
        make_technicaldata_submodel(row, uid),
        make_documentation_submodel(uid),
        make_mqttbroker_submodel(uid),
        make_event_submodel(uid)
    ]

    aas = AssetAdministrationShell(
        id_=aas_id,
        asset_information=AssetInformation(
            asset_kind=model.AssetKind.INSTANCE,
            global_asset_id=asset_id
        ),
        submodel={ModelReference.from_referable(sm) for sm in submodels}
    )

    store = DictObjectStore([aas] + submodels)
    output_path = os.path.join(output_folder, f"{uid}.json")
    write_aas_json_file(output_path, store, indent=2, ensure_ascii=False)

print("✅ 총 103개의 AAS 인스턴스를 aas_instances 폴더에 개별 JSON 파일로 저장했습니다.")
