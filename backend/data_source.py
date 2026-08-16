"""Thin dispatcher that lets agent.py call run_query()/get_schema() without
knowing whether it's talking to the demo SQLite file or (later) a Fabric SQL
endpoint. Swap backends by setting DATA_SOURCE=demo|fabric — no changes
needed anywhere else (agent, API, either UI).
"""
from backend import config, sqlite_source

_BACKENDS = {"demo": sqlite_source}


def _backend():
    if config.DATA_SOURCE == "fabric":
        from backend import fabric_client
        return fabric_client
    if config.DATA_SOURCE in _BACKENDS:
        return _BACKENDS[config.DATA_SOURCE]
    raise ValueError(f"Unknown DATA_SOURCE '{config.DATA_SOURCE}'. Expected 'demo' or 'fabric'.")


def get_schema() -> dict:
    return _backend().get_schema()


def run_query(sql: str) -> dict:
    return _backend().run_query(sql)


def active_source_name() -> str:
    return config.DATA_SOURCE
