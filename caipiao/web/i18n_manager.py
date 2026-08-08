"""国际化深化：翻译管理、本地化配置、多语言内容。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class TranslationKey:
    key: str
    locale: str
    value: str
    context: str = ""
    updated_at: float = field(default_factory=time.time)
    updated_by: str = ""


@dataclass
class LocaleConfig:
    code: str
    name: str
    native_name: str
    direction: str = "ltr"  # ltr or rtl
    date_format: str = "YYYY-MM-DD"
    time_format: str = "HH:mm"
    number_format: dict[str, str] = field(default_factory=dict)
    currency: str = ""
    enabled: bool = True


@dataclass
class TranslationNamespace:
    name: str
    keys: dict[str, dict[str, str]] = field(default_factory=dict)  # key -> {locale: value}


class I18nManager:
    """国际化管理器：翻译管理、本地化配置。"""

    def __init__(self, data_dir: str = ".caipiao/i18n"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._locales: dict[str, LocaleConfig] = {}
        self._namespaces: dict[str, TranslationNamespace] = {}
        self._load_default_locales()

    def _load_default_locales(self):
        locales = [
            LocaleConfig(code="zh-CN", name="Chinese (Simplified)", native_name="简体中文"),
            LocaleConfig(code="en-US", name="English (US)", native_name="English"),
            LocaleConfig(code="ja-JP", name="Japanese", native_name="日本語"),
            LocaleConfig(code="ko-KR", name="Korean", native_name="한국어"),
            LocaleConfig(code="zh-TW", name="Chinese (Traditional)", native_name="繁體中文"),
        ]
        for locale in locales:
            self._locales[locale.code] = locale

    def get_locales(self) -> list[LocaleConfig]:
        return list(self._locales.values())

    def get_locale(self, code: str) -> LocaleConfig | None:
        return self._locales.get(code)

    def add_locale(self, config: LocaleConfig):
        self._locales[config.code] = config

    def get_or_create_namespace(self, name: str) -> TranslationNamespace:
        if name not in self._namespaces:
            self._namespaces[name] = TranslationNamespace(name=name)
        return self._namespaces[name]

    def set_translation(self, namespace: str, key: str, locale: str, value: str, updated_by: str = ""):
        ns = self.get_or_create_namespace(namespace)
        if key not in ns.keys:
            ns.keys[key] = {}
        ns.keys[key][locale] = value

    def get_translation(self, namespace: str, key: str, locale: str, fallback: str = "") -> str:
        ns = self._namespaces.get(namespace)
        if ns and key in ns.keys:
            return ns.keys[key].get(locale, ns.keys[key].get("en-US", fallback))
        return fallback

    def get_namespace_translations(self, namespace: str, locale: str) -> dict[str, str]:
        ns = self._namespaces.get(namespace)
        if not ns:
            return {}
        return {key: values.get(locale, values.get("en-US", key)) for key, values in ns.keys.items()}

    def export_translations(self, locale: str) -> dict[str, dict[str, str]]:
        result = {}
        for ns_name, ns in self._namespaces.items():
            result[ns_name] = {
                key: values.get(locale, "")
                for key, values in ns.keys.items()
            }
        return result

    def import_translations(self, locale: str, data: dict[str, dict[str, str]]):
        for ns_name, translations in data.items():
            ns = self.get_or_create_namespace(ns_name)
            for key, value in translations.items():
                if key not in ns.keys:
                    ns.keys[key] = {}
                ns.keys[key][locale] = value

    def get_missing_translations(self, base_locale: str = "en-US") -> dict[str, list[str]]:
        missing: dict[str, list[str]] = {}
        for ns_name, ns in self._namespaces.items():
            ns_missing = []
            for key, values in ns.keys.items():
                if base_locale not in values:
                    ns_missing.append(key)
                else:
                    for locale_code in self._locales:
                        if locale_code != base_locale and locale_code not in values:
                            ns_missing.append(f"{key} ({locale_code})")
            if ns_missing:
                missing[ns_name] = ns_missing
        return missing

    def save_to_file(self):
        for ns_name, ns in self._namespaces.items():
            file_path = self._data_dir / f"{ns_name}.json"
            data = {
                "namespace": ns_name,
                "translations": {
                    key: values for key, values in ns.keys.items()
                },
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_file(self, namespace: str):
        file_path = self._data_dir / f"{namespace}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ns = self.get_or_create_namespace(namespace)
            ns.keys.update(data.get("translations", {}))


# 全局 i18n 管理器
_i18n: I18nManager | None = None


def get_i18n_manager() -> I18nManager:
    global _i18n
    if _i18n is None:
        _i18n = I18nManager()
    return _i18n
