"""插件管理路由：查看、启用、禁用、安装插件。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import require_admin
from ..plugin_manager import get_plugin_manager

router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginMetaOut(BaseModel):
    id: str
    name: str
    version: str
    description: str
    author: str
    enabled: bool
    hooks: list[str]


class PluginInstall(BaseModel):
    plugin_dir: str = Field(description="插件目录路径")


@router.get("", response_model=list[PluginMetaOut])
def list_plugins(
    principal=Depends(require_admin),
):
    """获取所有插件列表（管理员）。"""
    pm = get_plugin_manager()
    plugins = pm.get_plugins()
    return [
        PluginMetaOut(
            id=p.id,
            name=p.name,
            version=p.version,
            description=p.description,
            author=p.author,
            enabled=p.enabled,
            hooks=p.hooks,
        )
        for p in plugins
    ]


@router.post("/{plugin_id}/enable")
def enable_plugin(
    plugin_id: str,
    principal=Depends(require_admin),
):
    """启用插件（管理员）。"""
    pm = get_plugin_manager()
    if not pm.enable_plugin(plugin_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "插件不存在")
    return {"status": "ok", "message": f"插件 {plugin_id} 已启用"}


@router.post("/{plugin_id}/disable")
def disable_plugin(
    plugin_id: str,
    principal=Depends(require_admin),
):
    """禁用插件（管理员）。"""
    pm = get_plugin_manager()
    if not pm.disable_plugin(plugin_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "插件不存在")
    return {"status": "ok", "message": f"插件 {plugin_id} 已禁用"}


@router.post("/install")
def install_plugin(
    req: PluginInstall,
    principal=Depends(require_admin),
):
    """安装插件（管理员）。"""
    pm = get_plugin_manager()
    if not pm.install_plugin(req.plugin_dir):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "安装失败，请检查目录")
    return {"status": "ok", "message": "插件安装成功"}


@router.delete("/{plugin_id}")
def uninstall_plugin(
    plugin_id: str,
    principal=Depends(require_admin),
):
    """卸载插件（管理员）。"""
    pm = get_plugin_manager()
    if not pm.uninstall_plugin(plugin_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "插件不存在")
    return {"status": "ok", "message": f"插件 {plugin_id} 已卸载"}
