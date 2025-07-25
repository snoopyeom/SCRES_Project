# -*- coding: utf-8 -*-
"""자동화 시뮬레이션 스크립트.

- StatusEventServer를 스레드에서 실행
- 초기 최적 경로 계산 후 5초 대기
- Milling/Turning/Grinding 중 하나를 무작위로 고장 처리하고
  mark_as_fault() 호출 후 MQTT 이벤트 전송
- 이벤트 수신 후 자동 재계산된 경로를 로그 및 파일로 저장
"""

import csv
import json
import logging
import os
import random
import threading
import time

import pymongo

import aas_pathfinder
import event_server

# ────────────────────────────────────────────────────────────
# 간단한 MQTT 브로커/클라이언트 구현
class _Broker:
    def __init__(self):
        self.subs = []

    def subscribe(self, topic, client):
        self.subs.append((topic, client))

    def publish(self, topic, payload):
        for pat, cli in self.subs:
            if pat.endswith('#'):
                prefix = pat[:-1]
                if topic.startswith(prefix):
                    msg = type('Msg', (), {'payload': payload.encode()})
                    if cli.on_message:
                        cli.on_message(cli, None, msg)
            elif pat == topic:
                msg = type('Msg', (), {'payload': payload.encode()})
                if cli.on_message:
                    cli.on_message(cli, None, msg)

BROKER = _Broker()

class FakeMQTTClient:
    def __init__(self, *_, **__):
        self.on_message = None

    def connect(self, host, port=1883, keepalive=60):
        return 0

    def subscribe(self, topic):
        BROKER.subscribe(topic, self)
        return (0, 0)

    def loop_start(self):
        pass

    def loop_forever(self):
        pass

    def publish(self, topic, payload=None, qos=0, retain=False):
        BROKER.publish(topic, payload or '')
        return (0, 0)

# ────────────────────────────────────────────────────────────
# 데이터베이스 클라이언트 공유
DB_CLIENT = pymongo.MongoClient()

def _shared_mongo(*args, **kwargs):
    return DB_CLIENT

aas_pathfinder.MongoClient = _shared_mongo
event_server.MongoClient = _shared_mongo

# MQTT 클라이언트 패치
event_server.mqtt.Client = FakeMQTTClient

# 기본 설정
MONGO_URI = 'mongodb://localhost'
DB_NAME = 'aas'
COL_NAME = 'instances'
BROKER_URL = 'mqtt://localhost'

logging.basicConfig(level=logging.INFO)

# ────────────────────────────────────────────────────────────
def compute_and_save(label: str, html_path: str, csv_path: str):
    machines = aas_pathfinder.load_machines_from_mongo(MONGO_URI, DB_NAME, COL_NAME)
    running = {n: m for n, m in machines.items() if m.status.lower() == 'running'}
    if not running:
        logging.info('No running machines available')
        return
    by_proc = {}
    for m in running.values():
        by_proc.setdefault(m.process, []).append(m)
    flow = ['Forging', 'Turning', 'Milling', 'Grinding', 'Assembly']
    selected = []
    for step in flow:
        cand = by_proc.get(step, [])
        if not cand:
            continue
        if not selected:
            chosen = cand[0]
        else:
            prev = selected[-1]
            chosen = min(
                cand,
                key=lambda m: aas_pathfinder.dijkstra_path(
                    aas_pathfinder.build_graph_from_aas({prev.name: prev.coords, m.name: m.coords}),
                    prev.name,
                    m.name
                )[1]
            )
        selected.append(chosen)

    coords = {m.name: m.coords for m in selected}
    graph = aas_pathfinder.build_graph_from_aas(coords)
    total = 0.0
    rows = []
    for a, b in zip(selected, selected[1:]):
        path, dist = aas_pathfinder.dijkstra_path(graph, a.name, b.name)
        total += dist
        logging.info('%s → %s: %.1f km', a.name, b.name, dist)
        rows.append([a.name, b.name, f'{dist:.2f}'])
    logging.info('Total distance: %.1f km', total)

    # CSV 저장
    write_header = not os.path.exists(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['label', 'from', 'to', 'distance_km'])
        for r in rows:
            writer.writerow([label] + r)
        writer.writerow([label, 'TOTAL', '', f'{total:.2f}'])

    # folium 시각화
    try:
        import folium
        m = folium.Map(location=selected[0].coords, zoom_start=5)
        prev = None
        for mach in selected:
            folium.Marker(location=mach.coords, popup=f'{mach.name} ({mach.process})').add_to(m)
            if prev:
                folium.PolyLine([prev, mach.coords], color='blue').add_to(m)
            prev = mach.coords
        m.save(html_path)
        logging.info('Updated %s', html_path)
    except Exception as exc:
        logging.info('folium not available: %s', exc)

# ────────────────────────────────────────────────────────────
def main():
    # AAS 문서 업로드
    aas_pathfinder.upload_aas_documents('aas_instances', MONGO_URI, DB_NAME, COL_NAME)

    server = event_server.StatusEventServer(MONGO_URI, DB_NAME, COL_NAME, BROKER_URL)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()

    logging.info('Initial path calculation')
    compute_and_save('initial', 'process_flow_simulated.html', 'results_simulated.csv')

    time.sleep(5)

    # 무작위 프로세스 선정 후 고장 처리
    process = random.choice(['Milling', 'Turning', 'Grinding'])
    machines = aas_pathfinder.load_machines_from_mongo(MONGO_URI, DB_NAME, COL_NAME)
    candidates = [m for m in machines.values() if m.process == process]
    if not candidates:
        logging.info('No machine found for process %s', process)
        return
    target = random.choice(candidates)
    logging.info('Faulting machine %s (%s)', target.name, process)
    event_server.mark_as_fault(target.name, MONGO_URI, DB_NAME, COL_NAME)

    payload = json.dumps({'machine': target.name, 'status': 'Fault'})
    server.mqtt.publish(f'aas/status/{target.name}', payload)

    # 처리 시간 대기
    time.sleep(1)

    logging.info('Recalculating after fault')
    compute_and_save('after_fault', 'process_flow_simulated.html', 'results_simulated.csv')

if __name__ == '__main__':
    main()
