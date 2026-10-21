"""人设与提示词。

一个 2B 的小模型，指令遵循能力有限，所以提示词要短、要具体、要用正向约束，
并且明确规定「不许编数据」——校园场景里编错课表比不回答更糟。
"""

from __future__ import annotations

from .base import Message

SYSTEM_PROMPT = """你是「奶娃」，长春理工大学的校园助手，运行在学生自己的手机上。

说话要求：
1. 用简洁的中文口语回答，一般不超过 120 字，不要用 Markdown 星号和井号。
2. 涉及课表、考试、成绩时，只能依据下面「校园数据」里给出的内容回答，绝不编造课程、时间、地点。
3. 数据里没有的，就直说没有查到，并告诉用户可以换个问法或先去「登录」绑定学号。
4. 不知道的就说不知道，不要猜测学校规定。
5. 语气自然、亲切，像同校的学长学姐，不用「亲」「宝子」这类词。

隐私要求：永远不要重复用户的学号、密码、身份证号，也不要输出个人身份信息。"""


def build_messages(
    user_text: str,
    campus_data: str = "",
    history: list[dict[str, str]] | None = None,
    max_history: int = 6,
) -> list[Message]:
    """组装一轮对话上下文。

    ``campus_data`` 是工具查到的真实数据（课表 / 考试），以纯文本注入，
    小模型不需要理解 JSON，越直白越好。
    """
    system = SYSTEM_PROMPT
    if campus_data:
        system = system + "\n\n【校园数据】\n" + campus_data.strip() + "\n【校园数据结束】"

    messages = [Message("system", system)]
    for item in (history or [])[-max_history:]:
        role = item.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        content = (item.get("content") or "").strip()
        if content:
            messages.append(Message(role, content[:600]))
    messages.append(Message("user", user_text.strip()))
    return messages


def offline_reply(campus_data: str, user_text: str) -> str:
    """没有模型可用时的确定性回复（保证 App 永远能给出有用答案）。"""
    if campus_data.strip():
        return campus_data.strip()
    return (
        "本地模型还没准备好，云端模型也没配置，我现在答不了开放问题。\n"
        "不过课表和考试这类查询可以直接用：先在「我的」里登录学号，再问我"
        "「今天有什么课」「这周考试安排」就行。"
    )
