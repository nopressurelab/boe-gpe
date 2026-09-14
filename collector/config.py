"""Loading and validation of the JSON configuration files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR_ENV = "BOLETINES_CONFIG_DIR"
DEFAULT_CONFIG_DIR = "config"


class ConfigError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc


class Config:
    """Bundles sources.json, classification.json and site.json."""

    def __init__(self, root: Path, config_dir: Path):
        self.root = root
        self.config_dir = config_dir
        self.sources_doc = _read_json(config_dir / "sources.json")
        self.classification = _read_json(config_dir / "classification.json")
        self.site_doc = _read_json(config_dir / "site.json")
        self._validate()

    # -- access ----------------------------------------------------------
    @property
    def defaults(self) -> dict[str, Any]:
        return self.sources_doc.get("defaults", {})

    @property
    def sources(self) -> list[dict[str, Any]]:
        return [s for s in self.sources_doc.get("sources", []) if s.get("enabled", True)]

    @property
    def all_sources(self) -> list[dict[str, Any]]:
        return list(self.sources_doc.get("sources", [])) + list(
            self.sources_doc.get("pending_sources", []))

    @property
    def site(self) -> dict[str, Any]:
        return self.site_doc.get("site", {})

    @property
    def build(self) -> dict[str, Any]:
        return self.site_doc.get("build", {})

    @property
    def ui(self) -> dict[str, Any]:
        return self.site_doc.get("ui", {})

    @property
    def base_url(self) -> str:
        url = os.environ.get("SITE_BASE_URL") or self.site.get("base_url", "")
        return url.rstrip("/")

    @property
    def data_dir(self) -> Path:
        return self.root / self.build.get("data_dir", "data")

    @property
    def output_dir(self) -> Path:
        return self.root / self.build.get("output_dir", "public")

    def source_by_id(self, source_id: str) -> dict[str, Any] | None:
        for source in self.all_sources:
            if source.get("id") == source_id:
                return source
        return None

    # -- validation ------------------------------------------------------
    def _validate(self) -> None:
        seen: set[str] = set()
        for source in self.all_sources:
            sid = source.get("id")
            if not sid:
                raise ConfigError("A source in sources.json has no 'id'")
            if sid in seen:
                raise ConfigError(f"Duplicate source id: {sid}")
            seen.add(sid)
            if not source.get("adapter"):
                raise ConfigError(f"Source '{sid}' declares no 'adapter'")
        topics = self.classification.get("topics", [])
        if not topics:
            raise ConfigError("classification.json defines no topics")
        topic_ids: set[str] = set()
        for topic in topics:
            tid = topic.get("id")
            if not tid:
                raise ConfigError("A topic in classification.json has no 'id'")
            if tid in topic_ids:
                raise ConfigError(f"Duplicate topic id: {tid}")
            topic_ids.add(tid)
        if not self.site.get("title"):
            raise ConfigError("site.json does not define site.title")


def load(root: Path | str = ".", config_dir: Path | str | None = None) -> Config:
    root_path = Path(root).resolve()
    if config_dir is None:
        config_dir = os.environ.get(CONFIG_DIR_ENV, DEFAULT_CONFIG_DIR)
    config_path = Path(config_dir)
    if not config_path.is_absolute():
        config_path = root_path / config_path
    return Config(root_path, config_path)
