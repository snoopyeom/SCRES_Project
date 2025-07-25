import json
import logging
from urllib.parse import urlparse
from typing import Dict, List

from pymongo import MongoClient
import paho.mqtt.client as mqtt

from aas_pathfinder import (
    load_machines_from_mongo,
    build_graph_from_aas,
    dijkstra_path,
    Machine,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

FLOW = ["Forging", "Turning", "Milling", "Grinding", "Assembly"]

class StatusEventServer:
    def __init__(self, mongo_uri: str, db: str, col: str, broker_url: str):
        self.mongo_uri = mongo_uri
        self.db = db
        self.col = col
        self.broker_url = broker_url
        self.mqtt = mqtt.Client()
        self.mqtt.on_message = self.on_message

    # ────────────────────────────────────────────────────────────
    def start(self):
        parsed = urlparse(self.broker_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 1883
        self.mqtt.connect(host, port)
        self.mqtt.subscribe("aas/status/#")
        self.mqtt.loop_forever()

    # ────────────────────────────────────────────────────────────
    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            logger.warning("Invalid message payload: %s", msg.payload)
            return
        logger.info("Received event for %s → %s", payload.get("machine"), payload.get("status"))
        self.recalculate()

    # ────────────────────────────────────────────────────────────
    def recalculate(self):
        machines = load_machines_from_mongo(self.mongo_uri, self.db, self.col)
        running = {n: m for n, m in machines.items() if m.status.lower() == "running"}
        if not running:
            logger.info("No running machines available")
            return
        by_process: Dict[str, List[Machine]] = {}
        for m in running.values():
            by_process.setdefault(m.process, []).append(m)
        selected: List[Machine] = []
        for step in FLOW:
            cand = by_process.get(step, [])
            if not cand:
                continue
            if not selected:
                chosen = cand[0]
            else:
                prev = selected[-1]
                chosen = min(cand, key=lambda m: dijkstra_path(build_graph_from_aas({prev.name: prev.coords, m.name: m.coords}), prev.name, m.name)[1])
            selected.append(chosen)

        coords = {m.name: m.coords for m in selected}
        graph = build_graph_from_aas(coords)
        total = 0.0
        for a, b in zip(selected, selected[1:]):
            path, dist = dijkstra_path(graph, a.name, b.name)
            total += dist
            logger.info("%s → %s: %.1f km", a.name, b.name, dist)
        logger.info("Total distance: %.1f km", total)
        try:
            import folium
            m = folium.Map(location=selected[0].coords, zoom_start=5)
            prev = None
            for mach in selected:
                folium.Marker(location=mach.coords, popup=f"{mach.name} ({mach.process})").add_to(m)
                if prev:
                    folium.PolyLine([prev, mach.coords], color="blue").add_to(m)
                prev = mach.coords
            m.save("process_flow.html")
            logger.info("Updated process_flow.html")
        except Exception as exc:
            logger.info("folium not available: %s", exc)

# ────────────────────────────────────────────────────────────
def mark_as_fault(machine_name: str, mongo_uri: str, db: str, col: str) -> None:
    client = MongoClient(mongo_uri)
    collection = client[db][col]
    doc = collection.find_one({"filename": f"{machine_name}.json"})
    if not doc:
        logger.warning("Machine %s not found in DB", machine_name)
        return
    aas = doc.get("json", {})
    updated = False
    for sm in aas.get("submodels", []):
        if sm.get("id", "").endswith(f"Operation_{machine_name}"):
            for elem in sm.get("submodelElements", []):
                if elem.get("idShort") == "MachineStatus":
                    elem["value"] = "Fault"
                    updated = True
    if updated:
        collection.replace_one({"filename": f"{machine_name}.json"}, {"filename": f"{machine_name}.json", "json": aas, "raw": json.dumps(aas)}, upsert=True)
        logger.info("Updated status of %s to Fault", machine_name)
    else:
        logger.warning("MachineStatus not found for %s", machine_name)
