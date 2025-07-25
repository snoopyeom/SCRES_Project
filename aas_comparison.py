import argparse
import csv
import logging
import time
import random
from typing import List, Tuple, Dict, Any
import json
import os

# AAS 업로드·로딩 함수, Machine 클래스, Graph 빌드 함수, haversine 함수 임포트
from aas_pathfinder import (
    upload_aas_documents,
    load_machines_from_mongo,
    build_graph_from_aas,
    haversine,
    Machine,
)
from graph import Graph
from a_star import AStar

logger = logging.getLogger(__name__)

def select_machines(machines: Dict[str, Machine]) -> List[Machine]:
    """공정 순서(flow)에 따라 가장 가까운 머신을 선택"""
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
            # 이전 머신과 거리 최솟값인 머신 선택
            chosen = min(
                candidates,
                key=lambda m: haversine(prev.coords[0], prev.coords[1], m.coords[0], m.coords[1]),
            )
        selected.append(chosen)
        # 이미 선택된 머신은 후보군에서 제거
        by_process[step] = [c for c in candidates if c != chosen]
    return selected

def path_distance(graph: Graph, path: List[str]) -> float:
    """주어진 노드 경로의 총 거리 계산"""
    total = 0.0
    for a, b in zip(path, path[1:]):
        node = graph.find_node(a)
        for neigh, w in node.neighbors:
            if neigh.value == b:
                total += w
                break
    return total

def run_astar(graph: Graph, start: str, goal: str) -> Tuple[List[str], float, int, float]:
    """A* 알고리즘 실행 및 결과 반환"""
    alg = AStar(graph, start, goal)
    t0 = time.perf_counter()
    path, cost = alg.search()
    t1 = time.perf_counter()
    return path, cost, alg.number_of_steps, t1 - t0

def run_dijkstra(graph: Graph, start: str, goal: str) -> Tuple[List[str], float, int, float]:
    """다익스트라 알고리즘 실행 및 결과 반환"""
    from heapq import heappush, heappop

    start_node = graph.find_node(start)
    goal_node = graph.find_node(goal)
    queue = [(0.0, start_node)]
    dist = {start_node.value: 0.0}
    prev: Dict[str, str] = {}
    visited = set()
    steps = 0
    t0 = time.perf_counter()

    while queue:
        d, node = heappop(queue)
        if node.value in visited:
            continue
        visited.add(node.value)
        steps += 1
        if node == goal_node:
            break
        for neigh, w in node.neighbors:
            nd = d + w
            if nd < dist.get(neigh.value, float("inf")):
                dist[neigh.value] = nd
                prev[neigh.value] = node.value
                heappush(queue, (nd, neigh))
    t1 = time.perf_counter()

    if goal_node.value not in dist:
        return [], float("inf"), steps, t1 - t0

    # 경로 재구성
    path = [goal]
    cur = goal
    while cur != start:
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return path, dist[goal], steps, t1 - t0

def ga_shortest_path_process_based(
    machines: Dict[str, Machine],
    process_flow: List[str],
    graph: Graph,
    generations: int = 50,
    pop_size: int = 30,
    mutation_rate: float = 0.1,
) -> Tuple[List[str], float, int, float]:
    """유전 알고리즘을 이용한 공정 기반 최단 경로 탐색"""
    by_process: Dict[str, List[str]] = {}
    for m in machines.values():
        by_process.setdefault(m.process, []).append(m.name)

    def random_individual() -> List[int]:
        return [random.randint(0, len(by_process[proc]) - 1) for proc in process_flow]

    def decode_individual(ind: List[int]) -> List[str]:
        return [by_process[proc][idx] for proc, idx in zip(process_flow, ind)]

    def fitness(ind: List[int]) -> float:
        return path_distance(graph, decode_individual(ind))

    def crossover(p1: List[int], p2: List[int]) -> List[int]:
        point = random.randint(1, len(p1) - 1)
        return p1[:point] + p2[point:]

    def mutate(ind: List[int]) -> None:
        i = random.randint(0, len(ind) - 1)
        proc = process_flow[i]
        choices = list(range(len(by_process[proc])))
        if len(choices) <= 1:
            return
        choices.remove(ind[i])
        ind[i] = random.choice(choices)

    # 초기 개체군 생성
    population = [random_individual() for _ in range(pop_size)]
    t0 = time.perf_counter()
    for _ in range(generations):
        population.sort(key=fitness)
        next_gen = population[:2]  # 엘리트 보존
        while len(next_gen) < pop_size:
            p1, p2 = random.sample(population[:10], 2)
            child = crossover(p1, p2)
            if random.random() < mutation_rate:
                mutate(child)
            next_gen.append(child)
        population = next_gen
    t1 = time.perf_counter()

    # 최적 개체 추출
    best = min(population, key=fitness)
    best_path = decode_individual(best)
    return best_path, fitness(best), generations, t1 - t0

def sequential_search(
    graph: Graph,
    nodes: List[str],
    algo_func,
) -> Tuple[List[str], float, int, float]:
    """여러 구간(segment)을 순서대로 알고리즘 실행하여 전체 경로 반환"""
    full_path = [nodes[0]]
    total_dist = 0.0
    total_steps = 0
    total_time = 0.0
    for a, b in zip(nodes, nodes[1:]):
        seg_path, seg_dist, seg_steps, seg_time = algo_func(graph, a, b)
        if not seg_path:
            seg_path = [a, b]
        full_path.extend(seg_path[1:])
        total_dist += seg_dist
        total_steps += seg_steps
        total_time += seg_time
    return full_path, total_dist, total_steps, total_time

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare path finding algorithms")
    parser.add_argument("--aas-dir", help="AAS JSON 파일이 있는 디렉토리")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017", help="MongoDB URI")
    parser.add_argument("--db", default="test_db", help="MongoDB 데이터베이스 이름")
    parser.add_argument("--collection", default="aas_documents", help="MongoDB 컬렉션 이름")
    parser.add_argument("--algorithm", choices=["all", "astar", "dijkstra", "ga"], default="all")
    parser.add_argument("--generations", type=int, default=50, help="GA 세대 수")
    parser.add_argument("--population", type=int, default=30, help="GA 개체 수")
    parser.add_argument("--mutation", type=float, default=0.1, help="GA 돌연변이 확률")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ─── 업로드 단계 ─────────────────────────────────────────
    if args.aas_dir:
        count = upload_aas_documents(
            upload_dir=args.aas_dir,
            mongo_uri=args.mongo_uri,
            db_name=args.db,
            collection_name=args.collection
        )
        logger.info("MongoDB에 %d개 문서를 업로드했습니다.", count)
    # ────────────────────────────────────────────────────────

    # 머신 로드 (verbose=True로 디버깅 출력 활성화)
    machines = load_machines_from_mongo(
        mongo_uri=args.mongo_uri,
        db_name=args.db,
        collection_name=args.collection,
        verbose=True
    )
    if not machines:
        logger.info("No machines loaded")
        return

    selected = select_machines(machines)
    if len(selected) < 2:
        logger.info("Not enough machines for path finding")
        return

    # 전체 머신 좌표로 그래프 구성
    coords = {m.name: m.coords for m in machines.values()}
    graph = build_graph_from_aas(coords)
    node_names = [m.name for m in selected]

    results = []
    # A*
    if args.algorithm in ("all", "astar"):
        path, cost, steps, tm = sequential_search(graph, node_names, run_astar)
        results.append(["astar", path, cost, tm, True, steps])
    # Dijkstra
    if args.algorithm in ("all", "dijkstra"):
        path, cost, steps, tm = sequential_search(graph, node_names, run_dijkstra)
        results.append(["dijkstra", path, cost, tm, True, steps])
    # GA
    if args.algorithm in ("all", "ga"):
        process_flow = ["Forging", "Turning", "Milling", "Grinding"]
        path, cost, iters, tm = ga_shortest_path_process_based(
            machines=machines,
            process_flow=process_flow,
            graph=graph,
            generations=args.generations,
            pop_size=args.population,
            mutation_rate=args.mutation
        )
        results.append(["ga", path, cost, tm, True, iters])

    # CSV로 결과 저장
    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["algorithm", "path", "distance_km", "time_s", "optimal", "iterations"])
        for r in results:
            writer.writerow(r)

    # 콘솔 출력
    header = ["algorithm", "path", "distance_km", "time_s", "optimal", "iterations"]
    print("\t".join(header))
    for alg, path, dist, tm, opt, iters in results:
        print(f"{alg}\t{path}\t{dist:.2f}\t{tm:.4f}\t{str(opt).upper()}\t{iters}")

    # 로깅 출력
    for alg, path, dist, tm, opt, iters in results:
        logger.info(
            "%s: path=%s distance=%.1fkm time=%.4fs optimal=%s iterations=%s",
            alg,
            " -> ".join(path),
            dist,
            tm,
            opt,
            iters
        )

if __name__ == "__main__":
    main()
