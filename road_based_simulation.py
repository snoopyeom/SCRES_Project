# -*- coding: utf-8 -*-
"""실제 도로망을 이용한 경로 탐색 실험 스크립트.

- aas_pathfinder에서 기계 위치를 읽어 출발지와 도착지를 지정.
- osmnx를 이용하여 도로망 기반 최단 경로를 계산.
- folium을 이용해 경로를 시각화하고 road_map.html로 저장.
- 총 이동 거리(km)와 경로상의 노드 좌표 리스트를 출력.
"""

import logging

import folium
import osmnx as ox

import aas_pathfinder

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "test_db"
COL_NAME = "aas_documents"

logging.basicConfig(level=logging.INFO)


def main():
    machines = aas_pathfinder.load_machines_from_mongo(MONGO_URI, DB_NAME, COL_NAME)
    running = [m for m in machines.values() if m.status.lower() == "running"]
    if len(running) < 2:
        logging.info("실행 중인 기계가 2대 이상 필요합니다.")
        return

    start, end = running[0], running[1]

    lat1, lon1 = start.coords
    lat2, lon2 = end.coords
    north = max(lat1, lat2) + 0.01
    south = min(lat1, lat2) - 0.01
    east = max(lon1, lon2) + 0.01
    west = min(lon1, lon2) - 0.01

    logging.info("OpenStreetMap 데이터 다운로드 중...")
    G = ox.graph_from_bbox(north, south, east, west, network_type="drive")

    orig_node = ox.nearest_nodes(G, lon1, lat1)
    dest_node = ox.nearest_nodes(G, lon2, lat2)
    route = ox.shortest_path(G, orig_node, dest_node, weight="length")

    route_coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route]
    distance_m = sum(ox.utils_graph.get_route_edge_attributes(G, route, "length"))
    distance_km = distance_m / 1000.0
    print(f"총 경로 거리: {distance_km:.2f} km")
    print("경로 노드 좌표:")
    for lat, lon in route_coords:
        print(f"({lat:.6f}, {lon:.6f})")

    fmap = ox.plot_route_folium(G, route, route_color="blue", route_width=5)
    folium.Marker(location=start.coords, popup=f"Start: {start.name}").add_to(fmap)
    folium.Marker(location=end.coords, popup=f"End: {end.name}").add_to(fmap)
    fmap.save("road_map.html")
    logging.info("road_map.html 저장 완료")


if __name__ == "__main__":
    main()
