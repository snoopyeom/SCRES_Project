from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import logging
from typing import Any, Dict

logger = logging.getLogger("AAS_Converter")
logging.basicConfig(level=logging.INFO)

# Ensure the bundled SDK is importable and loaded only from ``sdk``.  We defer
# importing the BaSyx modules until runtime so this file does not depend on any
# globally installed packages.
SDK_DIR = os.path.join(os.path.dirname(__file__), "sdk")
if SDK_DIR not in sys.path:
    sys.path.insert(0, SDK_DIR)

aas = None
AssetAdministrationShellEnvironment = None  # type: ignore
write_aas_json_file = None
aas_provider = None


def _require_sdk() -> None:
    """Import the bundled BaSyx SDK on demand."""
    global aas, AssetAdministrationShellEnvironment, write_aas_json_file, aas_provider
    if aas is not None:
        return
    try:
        from basyx.aas import model as aas_mod
        from basyx.aas.environment import AssetAdministrationShellEnvironment as AASEnv  # type: ignore
        from basyx.aas.adapter.json import write_aas_json_file as write_json
        from basyx.aas.model import provider as aas_provider_mod
    except Exception as exc:  # pragma: no cover - import errors
        raise RuntimeError("BaSyx SDK is required to run this script") from exc
    aas = aas_mod
    AssetAdministrationShellEnvironment = AASEnv  # type: ignore
    write_aas_json_file = write_json
    aas_provider = aas_provider_mod
    if AssetAdministrationShellEnvironment is None and aas_provider is not None:
        class AssetAdministrationShellEnvironment(aas_provider.DictObjectStore):  # type: ignore
            def __init__(self, *, asset_administration_shells=None, submodels=None, concept_descriptions=None):
                super().__init__()
                for obj in asset_administration_shells or []:
                    self.add(obj)
                for obj in submodels or []:
                    self.add(obj)
                for obj in concept_descriptions or []:
                    self.add(obj)
        logger.info("ℹ️ using fallback AssetAdministrationShellEnvironment")
    logger.info("✅ BaSyx SDK imported from local bundle")


# Mapping for category/type to process names
TYPE_PROCESS_MAP = {
    "Hot Former": "Forging",
    "CNC LATHE": "Turning",
    "Vertical Machining Center": "Milling",
    "Horizontal Machining Center": "Milling",
    "Flat surface grinder": "Grinding",
    "Cylindrical grinder": "Grinding",
    "Assembly System": "Assembly",
}

# Property name normalization map
PROPERTY_NAME_MAP = {
    "Spindle_motor": "SpindlePower",
    "SpindleMotor": "SpindlePower",
    "SpindleMotorPower": "SpindlePower",
    "Spindle_Speed": "MaxOperatingSpeed",
    "SpindleSpeed": "MaxOperatingSpeed",
    "Travel_distance": "AxisTravel",
    "Swing_overbed": "SwingOverBed",
    "Distance_between_centers": "MaxTurningLength",
}


def _ident(data: Any, fallback_id: str = "http://example.com/dummy-id") -> Any:
    if aas is None:
        return None
    if isinstance(data, dict):
        ident = str(data.get("id", "")).strip()
        id_type = data.get("idType", "Custom")
    else:
        ident = str(data).strip()
        id_type = "Custom"
    if not ident:
        ident = fallback_id
    ident = ident.replace(" ", "_")
    try:
        return aas.Identifier(id=ident, id_type=id_type)
    except TypeError:
        try:
            return aas.Identifier(ident)
        except Exception:
            return ident


def _create(cls, *args, id_: Any = None, id_short: str | None = None, identification: Any = None, **kwargs):
    if identification is not None and not id_:
        id_ = identification
    if not id_ or str(id_).strip() == "":
        fallback_id = f"auto-id--{uuid.uuid4()}"
        logger.warning("[ID Fallback] %s using generated id %s", cls.__name__, fallback_id)
        id_ = fallback_id

    if cls.__name__ == "AssetAdministrationShell":
        if "asset_information" not in kwargs:
            raise ValueError("AssetAdministrationShell requires asset_information argument.")
        return cls(
            asset_information=kwargs["asset_information"],
            id_=id_,
            id_short=id_short,
            display_name=kwargs.get("display_name"),
            category=kwargs.get("category"),
            description=kwargs.get("description"),
            administration=kwargs.get("administration"),
            submodel=kwargs.get("submodel"),
            derived_from=kwargs.get("derived_from"),
            embedded_data_specifications=kwargs.get("embedded_data_specifications", ()),
            extension=kwargs.get("extension", ()),
        )

    if cls.__name__ == "AssetInformation":
        return cls(
            asset_kind=kwargs.get("asset_kind"),
            global_asset_id=kwargs.get("global_asset_id"),
            specific_asset_id=kwargs.get("specific_asset_id", ()),
            asset_type=kwargs.get("asset_type"),
            default_thumbnail=kwargs.get("default_thumbnail"),
        )

    try:
        return cls(id_=id_, id_short=id_short, *args, **kwargs)
    except TypeError as exc:
        logger.warning("[TypeError] %s: %s", cls.__name__, exc)
        obj = cls(*args, **kwargs)
        if not hasattr(obj, "identification"):
            return obj
        if getattr(obj, "id", None) is None:
            setattr(obj, "id", id_)
        if getattr(obj, "identification", None) is None:
            setattr(obj, "identification", id_)
        if id_short is not None and getattr(obj, "id_short", None) is None:
            setattr(obj, "id_short", id_short)
        return obj


def _prop(id_short: str, value: Any, value_type: Any = "string") -> Any:
    """Create a Property with the correct BaSyx datatype.

    ``convert_to_aas`` previously forwarded ``value_type`` strings directly to
    :class:`basyx.aas.model.submodel.Property`.  Newer versions of the BaSyx
    SDK expect the actual datatype classes instead of plain strings which lead
    to ``TypeError: isinstance() arg 2 must be a type`` during conversion.  This
    helper accepts either a string such as ``"string"`` or a datatype class and
    resolves it accordingly so it works with all SDK versions.
    """

    if aas is None:
        return None

    if isinstance(value_type, str):
        # Map common string names (e.g. "string", "integer") to the BaSyx
        # datatype classes expected by Property
        lookup_key = f"xs:{value_type}"
        value_type = aas.datatypes.XSD_TYPE_CLASSES.get(
            lookup_key, aas.datatypes.String
        )

    return aas.Property(id_short=id_short, value=value, value_type=value_type)


def _mlp(id_short: str, value: str) -> Any:
    if aas is None:
        return None
    return aas.MultiLanguageProperty(id_short=id_short, value={"en": value})


def _collection(id_short: str, elements: list[Any]) -> Any:
    if aas is None:
        return None
    col = aas.SubmodelElementCollection(id_short=id_short)
    col.value.extend(elements)
    return col


def _list(id_short: str, elements: list[Any]) -> Any:
    if aas is None:
        return None
    sel = aas.SubmodelElementList(id_short=id_short)
    sel.value.extend(elements)
    return sel


def _normalize_id_short(name: str) -> str:
    if name in PROPERTY_NAME_MAP:
        return PROPERTY_NAME_MAP[name]
    parts = name.replace("_", " ").split()
    return "".join(p.capitalize() for p in parts)


def _convert_category(sm: Dict[str, Any], *, fallback_prefix: str) -> Any:
    machine_type = ""
    machine_role = ""
    for elem in sm.get("submodelElements", []):
        sid = elem.get("idShort")
        if sid == "Type":
            machine_type = elem.get("value", "")
        elif sid == "Role":
            machine_role = elem.get("value", "")
    elements = [
        _prop("MachineType", machine_type),
        _prop("MachineRole", machine_role),
    ]
    ident = _ident(sm.get("identification", {}), fallback_id=f"{fallback_prefix}/Category")
    submodel = _create(aas.Submodel, id_=getattr(ident, "id", None), id_short="Category", identification=ident)
    for elem in elements:
        submodel.submodel_element.add(elem)
    return submodel


def _convert_operation(sm: Dict[str, Any], *, fallback_prefix: str) -> Any:
    status = ""
    for elem in sm.get("submodelElements", []):
        if elem.get("idShort") == "Machine_Status":
            status = elem.get("value", "")
            break
    elements = [
        _prop("MachineStatus", status),
        _prop("ProcessOrder", 0, "integer"),
        _prop("ProcessID", ""),
        _prop("ReplacedAASID", ""),
        _prop("Candidate", False, "boolean"),
        _prop("Selected", False, "boolean"),
    ]
    ident = _ident(sm.get("identification", {}), fallback_id=f"{fallback_prefix}/Operation")
    submodel = _create(aas.Submodel, id_=getattr(ident, "id", None), id_short="Operation", identification=ident)
    for elem in elements:
        submodel.submodel_element.add(elem)
    return submodel


def _convert_nameplate(sm: Dict[str, Any], *, fallback_prefix: str) -> Any:
    manufacturer = ""
    address = ""
    for elem in sm.get("submodelElements", []):
        sid = elem.get("idShort")
        if sid in {"Company", "Manufacturer"}:
            manufacturer = elem.get("value", "")
        elif sid in {"Physical_address", "Address"}:
            address = elem.get("value", "")

    parts = [p.strip() for p in address.split(",")]
    street = parts[0] if parts else ""
    city = parts[1] if len(parts) > 1 else ""
    national = parts[2] if len(parts) > 2 else ""

    addr_info = _collection(
        "AddressInformation",
        [
            _mlp("Street", street),
            _mlp("Zipcode", ""),
            _mlp("CityTown", city),
            _mlp("NationalCode", national),
        ],
    )

    elements = [
        _prop("URIOfTheProduct", ""),
        _mlp("ManufacturerName", manufacturer),
        _mlp("ManufacturerProductDesignation", ""),
        addr_info,
        _prop("OrderCodeOfManufacturer", ""),
        _prop("SerialNumber", ""),
        _prop("YearOfConstruction", ""),
    ]
    ident = _ident(sm.get("identification", {}), fallback_id=f"{fallback_prefix}/Nameplate")
    submodel = _create(aas.Submodel, id_=getattr(ident, "id", None), id_short="Nameplate", identification=ident)
    for elem in elements:
        submodel.submodel_element.add(elem)
    return submodel


def _convert_technical_data(sm: Dict[str, Any], process: str, *, fallback_prefix: str) -> Any:
    tech_props = []
    for elem in sm.get("submodelElements", []):
        tech_props.append(_prop(_normalize_id_short(elem.get("idShort", "")), elem.get("value")))

    technical_area = _collection("TechnicalPropertyAreas", tech_props)
    general_info = _collection(
        "GeneralInformation",
        [
            _prop("ManufacturerName", ""),
            _mlp("ManufacturerProductDesignation", ""),
            _prop("ManufacturerArticleNumber", ""),
            _prop("ManufacturerOrderCode", ""),
        ],
    )
    process_smc = _collection(process or "Process", [general_info, technical_area])
    ident = _ident(sm.get("identification", {}), fallback_id=f"{fallback_prefix}/TechnicalData")
    submodel = _create(aas.Submodel, id_=getattr(ident, "id", None), id_short="TechnicalData", identification=ident)
    submodel.submodel_element.add(process_smc)
    return submodel


def _convert_documentation(sm: Dict[str, Any], *, fallback_prefix: str) -> Any:
    documents = []
    for elem in sm.get("submodelElements", []):
        digital_file = _collection(
            "DigitalFile",
            [_prop("FileFormat", ""), _prop("FileName", elem.get("value"))],
        )
        doc_version = _collection(
            "DocumentVersion",
            [
                _prop("Language", "en"),
                _prop("Version", ""),
                _mlp("Title", elem.get("idShort")),
                _mlp("Description", ""),
                _prop("StatusValue", ""),
                _prop("StatusSetDate", "", "date"),
                _prop("OrganizationShortName", ""),
                _prop("OrganizationOfficialName", ""),
                _list("DigitalFiles", [digital_file]),
            ],
        )
        versions = _list("DocumentVersions", [doc_version])
        doc = _collection(
            "Document",
            [
                _collection(
                    "DocumentId",
                    [
                        _prop("DocumentIdentifier", elem.get("idShort")),
                        _prop("DocumentDomainId", ""),
                    ],
                ),
                _list("DocumentClassifications", []),
                versions,
            ],
        )
        documents.append(doc)
    docs_list = _list("Documents", documents)
    ident = _ident(sm.get("identification", {}), fallback_id=f"{fallback_prefix}/HandoverDocumentation")
    submodel = _create(aas.Submodel, id_=getattr(ident, "id", None), id_short="HandoverDocumentation", identification=ident)
    submodel.submodel_element.add(docs_list)
    return submodel


_CONVERTERS = {
    "Category": _convert_category,
    "Operational_Data": _convert_operation,
    "Nameplate": _convert_nameplate,
    "Documentation": _convert_documentation,
    "Technical_Data": _convert_technical_data,
}


def convert_file(path: str) -> Any:
    _require_sdk()

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(text)

    submodels_list: list[Any] = []
    concepts_list: list[Any] = []

    base_name = os.path.splitext(os.path.basename(path))[0]
    prefix = f"http://example.com/{base_name}"

    shell_data = data.get("assetAdministrationShells", [{}])[0]

    asset_ref = shell_data.get("asset", {}).get("keys", [{}])[0].get("value", "")
    asset_ident = _ident(asset_ref, fallback_id=f"{prefix}/asset")
    asset_info = _create(aas.AssetInformation, asset_kind="Instance", global_asset_id=asset_ident)

    shell_ident = _ident(shell_data.get("identification", {}), fallback_id=f"{prefix}/aas")
    shell = _create(
        aas.AssetAdministrationShell,
        id_=getattr(shell_ident, "id", None),
        id_short=shell_data.get("idShort", base_name),
        identification=shell_ident,
        asset_information=asset_info,
    )

    # Extract process name from Category submodel
    process = ""
    for sm in data.get("submodels", []):
        if sm.get("idShort") == "Category":
            for elem in sm.get("submodelElements", []):
                if elem.get("idShort") == "Type":
                    val = elem.get("value")
                    if isinstance(val, str):
                        process = TYPE_PROCESS_MAP.get(val, "")
            break

    # Convert submodels
    for sm in data.get("submodels", []):
        sid = sm.get("idShort")
        conv = _CONVERTERS.get(sid)
        if not conv:
            continue
        if sid == "Technical_Data":
            new_sm = conv(sm, process=process, fallback_prefix=prefix)
        else:
            new_sm = conv(sm, fallback_prefix=prefix)
        submodels_list.append(new_sm)
        # ``submodel`` is a mutable collection which is implemented as a
        # ``set`` in older versions of the BaSyx SDK.  Using ``append`` here
        # raises ``AttributeError`` when ``submodel`` is a set, therefore we
        # use ``add`` which works for both ``set`` and ``list`` like
        # implementations.  Add a proper ``ModelReference`` so the SDK does not
        # fail with ``TypeError``.
        shell.submodel.add(aas.ModelReference.from_referable(new_sm))

    # ConceptDescriptions would be converted here if needed
    for _cd in data.get("conceptDescriptions", []):
        pass

    env = AssetAdministrationShellEnvironment(
        asset_administration_shells=[shell],
        submodels=submodels_list,
        concept_descriptions=concepts_list,
    )
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert legacy AAS JSON files using the bundled BaSyx SDK")
    parser.add_argument("input_dir", help="Directory with legacy JSON files")
    parser.add_argument("output_dir", help="Directory to write converted files")
    args = parser.parse_args()

    _require_sdk()
    os.makedirs(args.output_dir, exist_ok=True)
    for name in os.listdir(args.input_dir):
        if not name.lower().endswith(".json"):
            continue
        inp = os.path.join(args.input_dir, name)
        outp = os.path.join(args.output_dir, name)
        try:
            env = convert_file(inp)
        except Exception as e:  # pragma: no cover - runtime errors
            print(f"Failed to convert {name}: {e}")
            import traceback
            traceback.print_exc()
            continue
        with open(outp, "w", encoding="utf-8") as f:
            write_aas_json_file(f, env)
        print(f"Converted {name} -> {outp}")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
