"""智能客服路由：AI 问答和使用指导。"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.requests import Request

from ..db import get_db
from ..deps import get_current_principal
from ..ratelimit import limiter

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    reply: str
    suggestions: list[str] = []
    action: str | None = None


# 知识库：常见问题和回答
KNOWLEDGE_BASE = {
    "生成": {
        "keywords": ["生成", "号码", "generate", "预测"],
        "reply": "在「生成」页面，您可以选择彩种和策略，点击「生成」按钮即可获得推荐号码。支持多种策略：随机、热号、冷号、均衡等。",
        "suggestions": ["如何选择策略？", "什么是后过滤？", "如何保存生成结果？"],
    },
    "回测": {
        "keywords": ["回测", "backtest", "历史", "验证"],
        "reply": "在「回测」页面，您可以对策略进行历史回测验证。设置每期注数和回测期数，系统会自动分析策略的历史表现，包括命中率、盈亏等指标。",
        "suggestions": ["如何提高回测准确率？", "什么是走查式回测？", "如何分析回测结果？"],
    },
    "统计": {
        "keywords": ["统计", "分析", "stats", "频率"],
        "reply": "在「统计」页面，您可以看到开奖数据的全面分析，包括号码频率、热冷号、遗漏值、奇偶比、大小比、和值分布等。还支持数据导出功能。",
        "suggestions": ["如何理解遗漏值？", "什么是热号冷号？", "如何导出数据？"],
    },
    "过滤": {
        "keywords": ["过滤", "filter", "筛选", "规则"],
        "reply": "在「过滤」页面，您可以设置后过滤规则，对生成的号码进行二次筛选。支持多种过滤条件，如和值范围、奇偶比、连号等。",
        "suggestions": ["如何设置过滤规则？", "什么是经验过滤？", "过滤规则如何保存？"],
    },
    "对比": {
        "keywords": ["对比", "compare", "比较", "策略"],
        "reply": "在「对比」页面，您可以同时选择多个策略进行横向对比，分析不同策略的号码分布差异、频率特征等。还支持策略对比回测功能。",
        "suggestions": ["如何选择对比策略？", "什么是 Jaccard 相似度？", "如何进行回测对比？"],
    },
    "收藏": {
        "keywords": ["收藏", "favorite", "保存", "常用"],
        "reply": "在「收藏」页面，您可以收藏常用的策略组合，方便快速使用。点击「收藏当前」按钮即可保存当前选择的策略。",
        "suggestions": ["如何取消收藏？", "收藏可以分享吗？", "如何管理收藏？"],
    },
    "推荐": {
        "keywords": ["推荐", "recommend", "建议", "智能"],
        "reply": "在「推荐」页面，系统会根据您的使用历史和回测结果，智能推荐最适合您的策略。推荐分数基于使用频率、回测表现等因素。",
        "suggestions": ["推荐是如何计算的？", "如何提高推荐准确率？", "推荐可以自定义吗？"],
    },
    "大屏": {
        "keywords": ["大屏", "dashboard", "看板", "数据"],
        "reply": "在「大屏」页面，您可以看到数据可视化看板，包括统计卡片、频率图表、趋势图、冷热信号等。支持全屏展示。",
        "suggestions": ["如何全屏展示？", "数据多久更新一次？", "可以自定义大屏吗？"],
    },
    "多期": {
        "keywords": ["多期", "联合", "关联", "分析"],
        "reply": "在「多期」页面，您可以分析多期号码的关联性，包括共现分析、连续出现、区间轮动等。还提供组合预测建议。",
        "suggestions": ["什么是共现分析？", "如何理解区间轮动？", "组合建议如何使用？"],
    },
    "任务": {
        "keywords": ["任务", "task", "定时", "自动"],
        "reply": "在「任务」页面，您可以创建定时任务，自动执行数据拉取、回测、分析等操作。支持设置执行间隔和启用/禁用。",
        "suggestions": ["如何创建定时任务？", "任务执行失败怎么办？", "可以同时运行多个任务吗？"],
    },
    "策略": {
        "keywords": ["策略", "strategy", "方法", "技巧"],
        "reply": "系统提供多种策略：随机生成、热号策略（基于高频号码）、冷号策略（基于低频号码）、均衡策略（平衡各指标）、ML策略（机器学习预测）等。",
        "suggestions": ["哪种策略最好？", "如何选择适合的策略？", "ML策略如何工作？"],
    },
    "数据": {
        "keywords": ["数据", "data", "开奖", "历史"],
        "reply": "系统会自动从数据源拉取最新开奖数据。您也可以手动拉取：在「统计」页面点击「拉取最新开奖」或「拉取全量历史」。数据支持 CSV 导出。",
        "suggestions": ["数据来源是什么？", "如何手动更新数据？", "数据可以导出吗？"],
    },
    "账户": {
        "keywords": ["账户", "account", "登录", "注册", "密码"],
        "reply": "您可以在登录页面注册新账户或登录已有账户。登录后可以使用所有功能，包括收藏、任务、社区等。管理员可以访问管理后台。",
        "suggestions": ["如何修改密码？", "如何注销账户？", "管理员有什么权限？"],
    },
    "社区": {
        "keywords": ["社区", "community", "分享", "评论", "排行"],
        "reply": "在「社区」功能中，您可以分享自己的预测，查看他人的分享，进行评论和点赞。排行榜展示活跃用户和最受欢迎的预测。",
        "suggestions": ["如何分享预测？", "如何点赞？", "排行榜如何计算？"],
    },
    "安全": {
        "keywords": ["安全", "security", "隐私", "加密"],
        "reply": "系统重视数据安全：密码加密存储、API 访问令牌认证、操作审计日志、敏感信息脱敏。管理员可以查看审计日志。",
        "suggestions": ["如何查看操作日志？", "数据如何加密？", "隐私政策是什么？"],
    },
    "帮助": {
        "keywords": ["帮助", "help", "使用", "教程"],
        "reply": "欢迎使用彩票号码生成器！基本流程：1) 选择彩种 → 2) 选择策略 → 3) 生成号码 → 4) 查看统计 → 5) 回测验证。如需帮助请随时提问！",
        "suggestions": ["功能介绍", "常见问题", "使用技巧"],
    },
    "你好": {
        "keywords": ["你好", "hello", "hi", "在吗"],
        "reply": "您好！我是智能客服助手，可以帮您解答关于彩票号码生成器的使用问题。请问有什么可以帮您的？",
        "suggestions": ["功能介绍", "如何生成号码？", "常见问题"],
    },
    "谢谢": {
        "keywords": ["谢谢", "thanks", "感谢", "thank"],
        "reply": "不客气！如果您还有其他问题，随时可以问我。祝您使用愉快！",
        "suggestions": ["还有什么功能？", "如何联系我们？"],
    },
}

# 默认回复
DEFAULT_REPLY = "抱歉，我暂时无法理解您的问题。您可以尝试以下常见问题，或换个方式描述您的需求。"
DEFAULT_SUGGESTIONS = ["功能介绍", "如何生成号码？", "如何查看统计？", "如何进行回测？", "常见问题"]


def find_answer(message: str) -> tuple[str, list[str], str | None]:
    """根据用户消息查找答案。"""
    message_lower = message.lower()

    # 关键词匹配
    best_match = None
    best_score = 0

    for key, kb_item in KNOWLEDGE_BASE.items():
        score = 0
        for keyword in kb_item["keywords"]:
            if keyword in message_lower:
                score += len(keyword)
        if score > best_score:
            best_score = score
            best_match = kb_item

    if best_match and best_score > 0:
        return best_match["reply"], best_match.get("suggestions", []), None

    # 数字序号匹配
    if re.search(r"第[一二三四五六七八九十]步|步骤|流程", message_lower):
        return (
            "使用流程：\n1. 在「彩种」区域选择您感兴趣的彩种\n2. 在「策略」区域选择生成策略\n3. 点击「生成」按钮获得推荐号码\n4. 查看「统计」页面了解历史数据\n5. 使用「回测」验证策略表现",
            ["如何选择策略？", "什么是后过滤？"],
            None,
        )

    if re.search(r"功能|介绍|有什么", message_lower):
        return (
            "本系统提供以下主要功能：\n• 生成：智能号码生成\n• 统计：开奖数据分析\n• 回测：策略历史验证\n• 过滤：号码二次筛选\n• 对比：策略横向对比\n• 收藏：常用策略保存\n• 推荐：智能策略推荐\n• 大屏：数据可视化\n• 多期：关联性分析\n• 任务：自动化执行",
            ["如何开始使用？", "哪个功能最实用？"],
            None,
        )

    return DEFAULT_REPLY, DEFAULT_SUGGESTIONS, None


@router.post("", response_model=ChatResponse)
@limiter.limit("60/minute")
def chat(
    request: Request,
    msg: ChatMessage,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """智能客服对话接口。"""
    reply, suggestions, action = find_answer(msg.message)
    return ChatResponse(
        reply=reply,
        suggestions=suggestions,
        action=action,
    )
