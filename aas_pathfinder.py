import argparse
import json
import logging
import os
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Tuple, List, Optional, Any


from dataclasses import dataclass
from pymongo import MongoClient

from graph import Graph, Node
from a_star import AStar

logger = logging.getLogger("__main__")

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderServiceError
except Exception:
    Nominatim = None
    GeocoderServiceError = Exception

# 좌표 조회에 외부 네트워크가 필요한데, 실행 환경에 따라 geopy 사용이
# 불가능한 경우가 많다. 경로 최적화를 안정적으로 수행하기 위해 사용되는
# 모든 주소의 위도/경도 값을 미리 정의한다. 값은 대략적인 위치만 알면
# 되므로 소수점 세 자리 정도의 정밀도로 기입하였다.
ADDRESS_COORDS: Dict[str, Tuple[float, float]] = {
    "6666 W 66th St, Chicago, Illinois": (41.772, -87.782),
    "2904 Scott Blvd, Santa Clara, California": (37.369, -121.972),
    "2019 Wood-Bridge Blvd, Bowling Green, Ohio": (41.374, -83.650),
    "240 E Rosecrans Ave, Gardena, California": (33.901, -118.282),
    "196 Alwine Rd, Saxonburg, Pennsylvania": (40.757, -79.819),
    "450 Whitney Road West": (43.069, -77.470),
    "931 Merwin Road, Pennsylvania": (40.590, -79.620),
    "5349 W 161st St, Cleveland, Ohio": (41.416, -81.832),
    "323 E Roosevelt Ave, Zeeland, Michigan": (42.812, -86.004),
    "1043 Kaiser Rd SW, Olympia, Washington": (47.042, -122.942),
    "7081 International Dr, Louisville, Kentucky": (38.137, -85.741),
    "11755 S Austin Ave, Alsip, Illinois": (41.681, -87.736),
    "11663 McKinney Rd, Titusville, Pennsylvania": (41.605, -79.652),
    "6811 E Mission Ave, Spokane Valley, Washington": (47.666, -117.315),
    "10908 County Rd 419, Texas": (30.588, -96.214),
}

IRDI_PROCESS_MAP = {
    "0173-1#01-AKJ741#017": "Turning",
    "0173-1#01-AKJ783#017": "Milling",
    "0173-1#01-AKJ867#017": "Grinding",
}

TYPE_PROCESS_MAP = {
    "Hot Former": "Forging",
    "CNC LATHE": "Turning",
    "Vertical Machining Center": "Milling",
    "Horizontal Machining Center": "Milling",
    "Flat surface grinder": "Grinding",
    "Cylindrical grinder": "Grinding",
    "Assembly System": "Assembly",
    "그라인더": "Grinding",
    "단조": "Forging",
    "밀링": "Milling",
    "선반": "Turning",
}

@dataclass
class Machine:
    name: str
    process: str
    coords: Tuple[float, float]
    status: str
    data: Optional[Dict[str, Any]] = None  # ← 이 줄 추가

# ────────────────────────────────────────────────────────────────
# AAS 문서 업로드 함수 추가
def upload_aas_documents(upload_dir: str, mongo_uri: str, db_name: str, collection_name: str) -> int:
    """올바르게 파싱된 JSON 구조를 MongoDB에 업로드하고, raw 필드도 함께 저장합니다."""
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]

    uploaded = 0
    for filename in os.listdir(upload_dir):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(upload_dir, filename)

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()

            try:
                content = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.warning("⚠️ %s JSON 파싱 실패: %s", filename, exc)
                continue

            # 간단한 JSON이라도 그대로 업로드한다. 테스트용으로 최소한의 구조만 있어도 허용.
            if not isinstance(content, dict):
                logger.warning("⚠️ %s JSON 구조가 객체가 아님", filename)
                continue

            # 구조 업로드 (raw와 파싱된 json 동시 저장)
            document = {
                "filename": filename,
                "json": content,
                "raw": raw,
            }

            collection.replace_one({"filename": filename}, document, upsert=True)
            uploaded += 1

        except Exception as e:
            logger.warning("⚠️ %s 업로드 중 예외 발생: %s", filename, str(e))

    logger.info("✅ 총 %d개 문서 업로드 완료", uploaded)
    return uploaded



# ────────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────────
def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """주소 문자열을 위도/경도로 변환한다.

    1. 미리 정의한 ``ADDRESS_COORDS`` 사전을 우선 조회한다.
    2. geopy가 설치된 경우 Nominatim 서비스를 이용하여 조회한다.
       (실행 환경에 따라 네트워크 오류가 발생할 수 있으므로 실패하면 ``None``을 반환)
    """
    if not address:
        return None

    # 사전에서 우선 검색
    if address in ADDRESS_COORDS:
        return ADDRESS_COORDS[address]

    if not Nominatim:
        return None

    geolocator = Nominatim(user_agent="aas_locator")
    try:
        loc = geolocator.geocode(address)
        if loc:
            return (loc.latitude, loc.longitude)
    except GeocoderServiceError:
        pass
    return None

def _find_address(elements, depth=0):
    prefix = "  " * depth

    for elem in elements:
        id_short = elem.get("idShort", "").lower()
        # print(f"{prefix}🔍 [depth {depth}] 탐색 중 idShort: {id_short}")

        if id_short == "addressinformation":
            value_list = elem.get("value", [])
            if isinstance(value_list, list):
                for item in value_list:
                    sub_id = item.get("idShort", "").lower()
                    if sub_id == "street":
                        sub_val = item.get("value")
                        # print(f"{prefix}    🏡 Street 값: {sub_val}")
                        if isinstance(sub_val, list):
                            for s in sub_val:
                                if isinstance(s, dict) and "text" in s:
                                    # print(f"{prefix}    ✅ Street → text: {s['text']}")
                                    return s["text"]

        if isinstance(elem.get("submodelElements"), list):
            # print(f"{prefix}↘️ 재귀 진입: {id_short}")
            addr = _find_address(elem["submodelElements"], depth + 1)
            if addr:
                return addr

    # print(f"{prefix}⛔ [depth {depth}] 주소 미발견 종료")
    return None




def explore_address_structure(elements, depth=0):
    prefix = "  " * depth
    for elem in elements:
        id_short = elem.get("idShort", "")
        # print(f"{prefix}🔎 idShort: {id_short}")
        if "value" in elem:
            val = elem["value"]
            # print(f"{prefix}📦 value type: {type(val)}, value: {val}")
        if "submodelElements" in elem:
            # print(f"{prefix}🔁 재귀 진입 → {id_short}")
            explore_address_structure(elem["submodelElements"], depth + 1)






def _find_name(elements):
    for elem in elements:
        if elem.get("idShort") in ["MachineName", "Name"]:
            val = elem.get("value")
            if isinstance(val, str):
                return val
            if isinstance(val, list) and isinstance(val[0], dict):
                return val[0].get("text")
        if isinstance(elem.get("submodelElements"), list):
            name = _find_name(elem["submodelElements"])
            if name:
                return name
    return None

# ────────────────────────────────────────────────────────────────
def _find_process(elements: List[Dict[str, Any]]) -> str:
    """
    SubmodelElement 목록에서 프로세스 정보를 찾아 반환.
    - idShort: MachineType 또는 ProcessID
    - value: TYPE_PROCESS_MAP, IRDI_PROCESS_MAP 양쪽 모두 소문자 키로 비교
    """
    # 소문자 키 매핑 준비
    type_map = {k.lower(): v for k, v in TYPE_PROCESS_MAP.items()}
    irdi_map = {k.lower(): v for k, v in IRDI_PROCESS_MAP.items()}

    for elem in elements:
        key = elem.get("idShort", "").lower()
        val = elem.get("value")
        # MachineType 또는 ProcessID 요소일 때
        if key in ("machinetype", "processid"):
            if isinstance(val, str):
                lv = val.strip().lower()
                # IRDI 우선 매핑
                if lv in irdi_map:
                    return irdi_map[lv]
                # TYPE 매핑
                if lv in type_map:
                    return type_map[lv]
        # 중첩된 요소 재귀 탐색
        if isinstance(elem.get("submodelElements"), list):
            proc = _find_process(elem["submodelElements"])
            if proc and proc != "Unknown":
                return proc

    return "Unknown"
# ────────────────────────────────────────────────────────────────

def load_machines_from_mongo(
    mongo_uri: str,
    db_name: str,
    collection_name: str,
    verbose: bool = False
) -> Dict[str, Machine]:
    """
    MongoDB에서 AAS 문서를 읽어 Machine 객체로 변환합니다.
    - submodel.id의 URL 끝부분을 키로 사용해 인덱싱
    - Nameplate → 주소, Category → 프로세스, Operation → 상태 추출
    """
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
    machines: Dict[str, Machine] = {}

    for doc in collection.find():
        aas = doc.get("json", {})
        shells = aas.get("assetAdministrationShells", [])
        if not shells:
            continue
        shell = shells[0]

        # 1) 머신 이름: idShort 우선, 없으면 id URL 끝부분
        raw_id = shell.get("idShort") or shell.get("id", "")
        name = raw_id.split("/")[-1]

        # 2) submodels를 URL 끝부분(소문자)으로 인덱싱
        submodels_index: Dict[str, List[Dict[str, Any]]] = {}
        for sm in aas.get("submodels", []):
            sm_id = sm.get("id", "")
            key = sm_id.split("/")[-1].lower()
            submodels_index[key] = sm.get("submodelElements", [])

        if verbose:
            print(f"[DEBUG] Found submodels: {list(submodels_index.keys())}")

        address = None
        process = "Unknown"
        status = "unknown"

        # 3) Nameplate_<name> → 주소 추출
        np_key = next((k for k in submodels_index if k.startswith(f"nameplate_{name.lower()}")), None)
        if np_key:
            address = _find_address(submodels_index[np_key])

        # 4) Category_<name> → 프로세스 추출
        cat_key = next((k for k in submodels_index if k.startswith(f"category_{name.lower()}")), None)
        if cat_key:
            proc = _find_process(submodels_index[cat_key])
            if proc:
                process = proc

        # 5) Operation_<name> → 상태 추출
        op_key = next((k for k in submodels_index if k.startswith(f"operation_{name.lower()}")), None)
        if op_key:
            st = _find_status(submodels_index[op_key])
            if st:
                status = st

        # 6) 주소 → 좌표 변환
        coords = geocode_address(address) if address else None
        if not coords:
            if verbose:
                print(f"[DEBUG] 좌표 변환 실패: {address}")
            continue

        # 7) Machine 객체 생성
        machines[name] = Machine(
            name=name,
            process=process,
            coords=coords,
            status=status,
            data=aas
        )

    return machines

def _find_status(elements: List[Dict[str, Any]]) -> Optional[str]:
    """
    Operation 서브모델의 MachineStatus(idShort='MachineStatus') 값을 찾아 반환
    재귀적으로 submodelElements도 탐색합니다.
    """
    for elem in elements:
        if elem.get("idShort", "").lower() == "machinestatus":
            return elem.get("value", "unknown")
        if isinstance(elem.get("submodelElements"), list):
            st = _find_status(elem["submodelElements"])
            if st:
                return st
    return None


# ────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def build_graph_from_aas(coords: Dict[str, Tuple[float, float]]) -> Graph:
    graph = Graph()
    for name, (lat, lon) in coords.items():
        graph.add_node(Node(name, (lat, lon)))
    names = list(coords.keys())
    for i, a in enumerate(names):
        lat1, lon1 = coords[a]
        for b in names[i + 1:]:
            lat2, lon2 = coords[b]
            dist = haversine(lat1, lon1, lat2, lon2)
            graph.add_edge(a, b, dist)
    return graph

def dijkstra_path(graph: Graph, start: str, goal: str) -> Tuple[List[str], float]:
    from heapq import heappush, heappop

    start_node = graph.find_node(start)
    goal_node = graph.find_node(goal)
    queue = [(0.0, start_node)]
    dist = {start_node.value: 0.0}
    prev: Dict[str, str] = {}
    visited = set()

    while queue:
        d, node = heappop(queue)
        if node.value in visited:
            continue
        visited.add(node.value)
        if node == goal_node:
            break
        for neigh, w in node.neighbors:
            nd = d + w
            if nd < dist.get(neigh.value, float("inf")):
                dist[neigh.value] = nd
                prev[neigh.value] = node.value
                heappush(queue, (nd, neigh))

    if goal_node.value not in dist:
        return [], float("inf")

    path = [goal]
    cur = goal
    while cur != start:
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return path, dist[goal]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload-dir", type=str, help="AAS JSON 파일이 있는 디렉토리")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="test_db")
    parser.add_argument("--collection", default="aas_documents")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)

    if args.upload_dir:
        num = upload_aas_documents(args.upload_dir, args.mongo_uri, args.db, args.collection)
        logger.info("%d documents uploaded", num)

    machines = load_machines_from_mongo(args.mongo_uri, args.db, args.collection)
    if not machines:
        logger.info("No running machines with valid locations found.")
        return

    by_process: Dict[str, List[Machine]] = {}
    for m in machines.values():
        by_process.setdefault(m.process, []).append(m)

    flow = ["Forging", "Turning", "Milling", "Grinding", "Assembly"]
    selected: List[Machine] = []
    for step in flow:
        candidates = by_process.get(step, [])
        if not candidates:
            continue
        if not selected:
            chosen = candidates[0]
        else:
            prev = selected[-1]
            chosen = min(candidates, key=lambda m: haversine(prev.coords[0], prev.coords[1], m.coords[0], m.coords[1]))
        selected.append(chosen)

    coords = {m.name: m.coords for m in selected}
    graph = build_graph_from_aas(coords)
    total_dist = 0.0
    for a, b in zip(selected, selected[1:]):
        path, d = dijkstra_path(graph, a.name, b.name)
        total_dist += d
        logger.info("%s → %s: %.1f km", a.name, b.name, d)
    logger.info("Total distance: %.1f km", total_dist)

    try:
        import folium
        m = folium.Map(location=selected[0].coords, zoom_start=5)
        prev = None
        for mach in selected:
            folium.Marker(location=mach.coords, popup=f"{mach.name} ({mach.process}) - {mach.status}").add_to(m)
            if prev:
                folium.PolyLine([prev, mach.coords], color="blue").add_to(m)
            prev = mach.coords
        m.save("process_flow.html")
        logger.info("Saved flow visualisation to 'process_flow.html'.")
    except Exception:
        logger.info("folium not available; skipping visualisation.")

if __name__ == "__main__":
    main()
    