"""Demo script showcasing the A* search algorithm.

This script replicates the functionality that originally lived in the notebook
``A star algorithm.ipynb``.  It optionally loads Asset Administration Shell (AAS)
JSON files using the BaSyx SDK bundled in ``sdk/`` and then performs an A* search
on a small demo graph.  The found path is displayed both textually and in a
simple ASCII grid so the result can be visualised without additional libraries.
"""

import argparse
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from graph import Graph, Node
from a_star import AStar

# Use the local SDK if available
SDK_DIR = os.path.join(os.path.dirname(__file__), "sdk")
if SDK_DIR not in sys.path:
    sys.path.insert(0, SDK_DIR)

# BaSyx SDK is optional. If it is missing the script will still run
try:
    from basyx.aas.adapter.json import read_aas_json_file
except ImportError:  # basyx library might not be available
    read_aas_json_file = None


def load_aas_files(directory: str):
    """Load all AAS JSON files found in ``directory``.

    Parameters
    ----------
    directory:
        Path containing ``*.json`` files representing Asset Administration
        Shells.
    """

    if read_aas_json_file is None:
        return []

    shells = []
    for name in os.listdir(directory):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            # Suppress noisy warnings emitted by the basyx reader
            with open(path, "r", encoding="utf-8") as f, \
                 redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                shells.append(read_aas_json_file(f))
        except Exception:
            # Ignore malformed AAS files to keep output clean
            continue
    return shells


def build_graph() -> Graph:
    """Construct the demo graph used for the A* example."""
    graph = Graph()
    nodes = ['S', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'T', 'L']
    coords = [
        (1, 1), (1, 2), (1, 4), (2, 1), (2, 2), (2, 3),
        (2, 4), (3, 1), (3, 4), (4, 1), (4, 2), (4, 3), (4, 4)
    ]
    for value, coord in zip(nodes, coords):
        graph.add_node(Node(value, coord))

    edges = [
        ('S', 'B', 4), ('S', 'D', 5), ('B', 'E', 1),
        ('C', 'G', 1), ('D', 'E', 2), ('D', 'H', 3),
        ('E', 'F', 6), ('F', 'G', 4), ('G', 'I', 3),
        ('H', 'J', 1), ('I', 'L', 4), ('J', 'K', 6),
        ('K', 'T', 2), ('T', 'L', 3)
    ]
    for a, b, w in edges:
        graph.add_edge(a, b, w)
    return graph


def visualise_path(graph: Graph, path: list[str]) -> None:
    """Print an ASCII representation of the grid with the found path."""
    coord_map = {n.value: (n.x, n.y) for n in graph.nodes}
    max_x = max(x for x, _ in coord_map.values())
    max_y = max(y for _, y in coord_map.values())
    grid = [["   " for _ in range(max_y)] for _ in range(max_x)]

    for value, (x, y) in coord_map.items():
        marker = f"[{value}]" if value in path else f" {value} "
        grid[x - 1][y - 1] = marker

    for row in grid:
        print(" ".join(row))


def run_demo():
    parser = argparse.ArgumentParser(description="A* search demo")
    parser.add_argument(
        "--aas-dir",
        default="설비 json 파일",
        help="Directory containing AAS JSON files",
    )
    args = parser.parse_args()

    shells = load_aas_files(args.aas_dir)
    if shells:
        print(f"Loaded {len(shells)} AAS file(s) from '{args.aas_dir}'.")

    graph = build_graph()
    alg = AStar(graph, 'S', 'T')
    path, cost = alg.search()
    print(' -> '.join(path))
    print(f'Length of the path: {cost}')
    visualise_path(graph, path)


if __name__ == '__main__':
    run_demo()
