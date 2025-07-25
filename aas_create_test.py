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

# 헬퍼 함수: MLP 생성

def mlp(id_short: str, text: str, lang: str = 'en') -> MultiLanguageProperty:
    """
    주어진 텍스트와 언어로 MultiLanguageProperty를 생성합니다.
    """
    return MultiLanguageProperty(
        id_short=id_short,
        value=LangStringSet({lang: text})
    )

def ref_from_keys(keys):
    """Helper creating ``ModelReference`` from ``keys`` for all SDK versions."""
    if hasattr(ModelReference, "from_keys"):
        return ModelReference.from_keys(keys)
    try:
        return ModelReference(keys=keys)
    except TypeError:
        return ModelReference(keys)

# Submodel 생성 함수들

def create_nameplate_submodel() -> Submodel:
    sm = Submodel(id_="https://example.com/submodel/Nameplate")
    address = SubmodelElementCollection(
        id_short="AddressInformation",
        value=[
            mlp("Street", "Example Street"),
            mlp("Zipcode", "12345"),
            mlp("CityTown", "Example City"),
            mlp("NationalCode", "KR")
        ]
    )
    for elem in [
        Property(id_short="URIOfTheProduct", value_type=datatypes.String, value="http://example.com/product"),
        mlp("ManufacturerName", "DN Solutions"),
        mlp("ManufacturerProductDesignation", "DN-Lathe-5000"),
        address,
        Property(id_short="OrderCodeOfManufacturer", value_type=datatypes.String, value="DN123456"),
        Property(id_short="SerialNumber", value_type=datatypes.String, value="SN20250718"),
        Property(id_short="YearOfConstruction", value_type=datatypes.String, value="2024")
    ]:
        sm.submodel_element.add(elem)
    return sm


def create_category_submodel() -> Submodel:
    sm = Submodel(id_="https://example.com/submodel/Category")
    for elem in [
        Property(id_short="MachineType", value_type=datatypes.String, value="Grinding"),
        Property(id_short="MachineRole", value_type=datatypes.String, value="Finishing")
    ]:
        sm.submodel_element.add(elem)
    return sm


def create_operation_submodel() -> Submodel:
    sm = Submodel(id_="https://example.com/submodel/Operation")
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


def create_technicaldata_submodel() -> Submodel:
    sm = Submodel(id_="https://example.com/submodel/TechnicalData")

    def make_process_block(proc: str):
        general = SubmodelElementCollection(
            id_short=f"{proc}_GeneralInformation",
            value=[
                Property(id_short="ManufacturerName", value_type=datatypes.String, value="DN"),
                mlp("ManufacturerProductDesignation", f"DN {proc} 4000"),
                Property(id_short="ManufacturerArticleNumber", value_type=datatypes.String, value=f"DN{proc[:2].upper()}4000"),
                Property(id_short="ManufacturerOrderCode", value_type=datatypes.String, value="ORD12345")
            ]
        )
        technical = SubmodelElementCollection(
            id_short=f"{proc}_TechnicalPropertyAreas",
            value=[
                Property(id_short="Size", value_type=datatypes.String, value="500,600,700"),
                Property(id_short="GrindingWheelDiameter", value_type=datatypes.Double, value=300.0),
                Property(id_short="MagneticChuckDiameter", value_type=datatypes.Double, value=250.0),
                Property(id_short="MaxSwing", value_type=datatypes.Int, value=450),
                Property(id_short="SpindlePower", value_type=datatypes.Int, value=15),
                Property(id_short="MaxOperatingSpeed", value_type=datatypes.Int, value=2000),
                Property(id_short="Weight", value_type=datatypes.Int, value=1800)
            ]
        )
        return [general, technical]

    for process in ("Grinding", "Forging", "Turning", "Milling"):
        for block in make_process_block(process):
            sm.submodel_element.add(block)
    return sm


def create_documentation_submodel() -> Submodel:
    sm = Submodel(id_="https://example.com/submodel/HandoverDocumentation")
    doc = SubmodelElementCollection(
        id_short="Document",
        value=[
            SubmodelElementCollection(
                id_short="DocumentId",
                value=[
                    Property(id_short="DocumentIdentifier", value_type=datatypes.String, value="DOC001"),
                    Property(id_short="DocumentDomainId", value_type=datatypes.String, value="AAS-DOC")
                ]
            ),
            SubmodelElementCollection(
                id_short="DocumentClassification",
                value=[
                    Property(id_short="ClassId", value_type=datatypes.String, value="DOC001"),
                    mlp("ClassName", "Manual"),
                    Property(id_short="ClassificationSystem", value_type=datatypes.String, value="DIN")
                ]
            ),
            SubmodelElementCollection(
                id_short="DocumentVersion",
                value=[
                    Property(id_short="Language", value_type=datatypes.String, value="en"),
                    mlp("Title", "V1.0"),
                    mlp("Description", "Initial version"),
                    Property(id_short="StatusValue", value_type=datatypes.String, value="Approved"),
                    Property(id_short="StatusDate", value_type=datatypes.String, value="2025-07-18"),
                    Property(id_short="OrganizationShortName", value_type=datatypes.String, value="DN"),
                    Property(id_short="OrganizationOfficialName", value_type=datatypes.String, value="DN Solutions")
                ]
            ),
            SubmodelElementCollection(
                id_short="DigitalFile",
                value=[
                    Property(id_short="FileFormat", value_type=datatypes.String, value="pdf"),
                    Property(id_short="FileName", value_type=datatypes.String, value="manual.pdf")
                ]
            )
        ]
    )
    sm.submodel_element.add(doc)
    return sm


def create_mqttbroker_submodel() -> Submodel:
    """MQTT 브로커 설정 서브모델을 생성합니다."""
    sm = Submodel(id_="https://example.com/submodel/MQTTBrokerConfig")
    for elem in [
        Property(id_short="Address", value_type=datatypes.String, value="mqtt://broker.hivemq.com"),
        Property(id_short="Topic", value_type=datatypes.String, value="aas/status/")
    ]:
        sm.submodel_element.add(elem)
    return sm


def create_basicevent_submodel() -> Submodel:
    """MachineStatus 변경 이벤트를 정의한 서브모델을 생성합니다."""
    sm = Submodel(id_="https://example.com/submodel/StatusEvent")

    event = model.BasicEventElement(
        id_short="StatusChangeEvent",
        observed=ref_from_keys([
            model.Key(type_=model.KeyTypes.SUBMODELELEMENT, value="MachineStatus")
        ]),
        direction="output",
        state="on",
        message_topic="aas/status/Machine001",
        message_broker=ref_from_keys([
            model.Key(type_=model.KeyTypes.SUBMODEL, value="MQTTBrokerConfig")
        ]),
        min_interval="PT1S",
    )
    sm.submodel_element.add(event)
    return sm


def create_full_aas() -> tuple[AssetAdministrationShell, list[Submodel]]:
    asset_info = AssetInformation(
        asset_kind=model.AssetKind.INSTANCE,
        global_asset_id="http://example.com/asset/Machine001"
    )
    submodels = [
        create_nameplate_submodel(),
        create_category_submodel(),
        create_operation_submodel(),
        create_technicaldata_submodel(),
        create_documentation_submodel(),
        create_mqttbroker_submodel(),
        create_basicevent_submodel()
    ]
    aas = AssetAdministrationShell(
        id_="https://example.com/aas/Machine001",
        asset_information=asset_info,
        submodel={ModelReference.from_referable(sm) for sm in submodels}
    )
    return aas, submodels

if __name__ == "__main__":
    aas, submodels = create_full_aas()
    store = DictObjectStore([aas] + submodels)

    print("AAS instance created.")

    # JSON 파일로 저장 (indent=2 적용)
    write_aas_json_file("aas_instance.json", store, indent=2, ensure_ascii=False)
    print("Saved as aas_instance.json")