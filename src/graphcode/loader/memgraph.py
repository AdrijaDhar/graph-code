from __future__ import annotations

from graphcode.schema import GraphBatch, GraphNode


INDEX_QUERIES = [
    "CREATE INDEX ON :Module(path);",
    "CREATE INDEX ON :Function(qualified_name);",
    "CREATE INDEX ON :Class(qualified_name);",
    "CREATE INDEX ON :Module(org_id);",
]


class MemgraphStore:
    def __init__(self, uri: str, user: str = "", password: str = "") -> None:
        from neo4j import GraphDatabase

        auth = (user, password) if user else None
        self._driver = GraphDatabase.driver(uri, auth=auth)

    def close(self) -> None:
        self._driver.close()

    def ensure_indexes(self) -> None:
        with self._driver.session() as s:
            for q in INDEX_QUERIES:
                try:
                    s.run(q)
                except Exception:
                    pass

    def clear_org(self, org_id: str) -> None:
        with self._driver.session() as s:
            s.run("MATCH (n {org_id: $org}) DETACH DELETE n", org=org_id)

    def delete_module(self, path: str, org_id: str) -> None:
        with self._driver.session() as s:
            s.run(
                "MATCH (n {org_id: $org, path: $path}) DETACH DELETE n",
                org=org_id,
                path=path,
            )

    def load_batch(self, batch: GraphBatch, org_id: str) -> None:
        nodes_by_label: dict[str, list[dict]] = {}
        for n in batch.nodes:
            rec = {"id": n.id, **n.props, "org_id": org_id}
            nodes_by_label.setdefault(n.label, []).append(rec)
        with self._driver.session() as s:
            for label, recs in nodes_by_label.items():
                for chunk in _chunks(recs, 800):
                    s.run(
                        f"UNWIND $nodes AS n MERGE (x:{label} {{id: n.id}}) SET x += n",
                        nodes=chunk,
                    )
            edges = [
                {"type": e.type, "from": e.from_id, "to": e.to_id, **(e.props or {})}
                for e in batch.edges
                if not e.to_id.startswith("unresolved:")
            ]
            for etype in {e["type"] for e in edges}:
                subset = [e for e in edges if e["type"] == etype]
                for chunk in _chunks(subset, 800):
                    s.run(
                        f"""
                        UNWIND $edges AS e
                        MATCH (a {{id: e.from}}), (b {{id: e.to}})
                        MERGE (a)-[r:{etype}]->(b)
                        """,
                        edges=chunk,
                    )

    def hydrate_nodes(self, nodes: list[GraphNode], org_id: str) -> None:
        batch = GraphBatch(nodes=nodes, edges=[])
        self.load_batch(batch, org_id)

    def query(self, cypher: str, **params):
        with self._driver.session() as s:
            return list(s.run(cypher, **params))


def _chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]
