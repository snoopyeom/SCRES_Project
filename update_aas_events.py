import json
import os
import sys

BROKER_SUBMODEL = {
    "idShort": "MQTTBrokerConfig",
    "modelType": "Submodel",
    "submodelElements": [
        {
            "idShort": "BrokerURL",
            "modelType": "Property",
            "value": "mqtt://broker.hivemq.com",
            "valueType": "xs:string"
        },
        {
            "idShort": "TopicBase",
            "modelType": "Property",
            "value": "aas/status/",
            "valueType": "xs:string"
        }
    ]
}

EVENT_TEMPLATE = {
    "idShort": "StatusChangeEvent",
    "modelType": "BasicEventElement",
    "semanticId": {
        "keys": [
            {
                "type": "GlobalReference",
                "value": "https://admin-shell.io/aas/3/0/BasicEventElement"
            }
        ]
    },
    "observed": {
        "keys": [
            {
                "type": "SubmodelElement",
                "value": "MachineStatus"
            }
        ]
    },
    "direction": "output",
    "state": "on",
    "messageTopic": "",
    "messageBroker": {
        "keys": [
            {
                "type": "Submodel",
                "value": "MQTTBrokerConfig"
            }
        ]
    }
}

def patch_aas_file(path: str) -> bool:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    changed = False
    submodels = data.get("submodels", [])

    has_broker = any(
        (sm.get("idShort") == "MQTTBrokerConfig") or
        ("MQTTBrokerConfig" in sm.get("id", ""))
        for sm in submodels
    )
    if not has_broker:
        submodels.append(json.loads(json.dumps(BROKER_SUBMODEL)))
        changed = True

    for sm in submodels:
        sid = sm.get("id", "")
        if "Operation_" in sid:
            machine = sid.split("Operation_")[-1]
            elements = sm.setdefault("submodelElements", [])
            if not any(e.get("idShort") == "StatusChangeEvent" for e in elements):
                evt = json.loads(json.dumps(EVENT_TEMPLATE))
                evt["messageTopic"] = f"aas/status/{machine}"
                elements.append(evt)
                changed = True

    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    return changed

def main(dir_path: str):
    for filename in os.listdir(dir_path):
        if not filename.endswith('.json'):
            continue
        path = os.path.join(dir_path, filename)
        if patch_aas_file(path):
            print(f"Patched {filename}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: update_aas_events.py <directory>")
        sys.exit(1)
    main(sys.argv[1])
