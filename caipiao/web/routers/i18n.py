"""国际化管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import get_current_principal
from ..i18n_manager import LocaleConfig, get_i18n_manager

router = APIRouter(prefix="/i18n", tags=["i18n"])


class LocaleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=10)
    name: str
    native_name: str
    direction: str = "ltr"
    date_format: str = "YYYY-MM-DD"
    time_format: str = "HH:mm"
    currency: str = ""


class TranslationSet(BaseModel):
    namespace: str
    key: str
    locale: str
    value: str


class TranslationImport(BaseModel):
    locale: str
    data: dict[str, dict[str, str]]


@router.get("/locales")
def list_locales(
    principal=Depends(get_current_principal),
):
    mgr = get_i18n_manager()
    return [
        {
            "code": l.code,
            "name": l.name,
            "native_name": l.native_name,
            "direction": l.direction,
            "enabled": l.enabled,
        }
        for l in mgr.get_locales()
    ]


@router.post("/locales")
def create_locale(
    req: LocaleCreate,
    principal=Depends(get_current_principal),
):
    mgr = get_i18n_manager()
    config = LocaleConfig(
        code=req.code,
        name=req.name,
        native_name=req.native_name,
        direction=req.direction,
        date_format=req.date_format,
        time_format=req.time_format,
        currency=req.currency,
    )
    mgr.add_locale(config)
    return {"status": "ok", "code": config.code}


@router.post("/translations")
def set_translation(
    req: TranslationSet,
    principal=Depends(get_current_principal),
):
    mgr = get_i18n_manager()
    mgr.set_translation(req.namespace, req.key, req.locale, req.value, updated_by=principal.id)
    return {"status": "ok"}


@router.get("/translations/{namespace}/{locale}")
def get_translations(
    namespace: str,
    locale: str,
    principal=Depends(get_current_principal),
):
    mgr = get_i18n_manager()
    return mgr.get_namespace_translations(namespace, locale)


@router.get("/export/{locale}")
def export_translations(
    locale: str,
    principal=Depends(get_current_principal),
):
    mgr = get_i18n_manager()
    return mgr.export_translations(locale)


@router.post("/import")
def import_translations(
    req: TranslationImport,
    principal=Depends(get_current_principal),
):
    mgr = get_i18n_manager()
    mgr.import_translations(req.locale, req.data)
    return {"status": "ok"}


@router.get("/missing")
def get_missing(
    base_locale: str = "en-US",
    principal=Depends(get_current_principal),
):
    mgr = get_i18n_manager()
    return mgr.get_missing_translations(base_locale)


@router.post("/save")
def save_translations(
    principal=Depends(get_current_principal),
):
    mgr = get_i18n_manager()
    mgr.save_to_file()
    return {"status": "ok"}
