"""动作类型管理模块 - 适配器端实现"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MotionType:
    """动作类型定义"""

    id: str
    name: str
    description: str
    keywords: list[str]  # 关键词列表，用于智能匹配


# 预设动作类型定义
MOTION_TYPES: dict[str, MotionType] = {
    "idle": MotionType(
        id="idle",
        name="待机",
        description="空闲和等待时的动作",
        keywords=["待机", "空闲", "等待", "默认"],
    ),
    "speaking": MotionType(
        id="speaking",
        name="说话",
        description="说话和表达时的动作",
        keywords=["说", "讲", "表达", "说话"],
    ),
    "thinking": MotionType(
        id="thinking",
        name="思考",
        description="思考和疑惑的动作",
        keywords=["想", "思考", "思考中", "琢磨", "疑惑", "为什么", "如何"],
    ),
    "happy": MotionType(
        id="happy",
        name="开心",
        description="表达喜悦和高兴的情绪",
        keywords=["开心", "高兴", "快乐", "愉快", "欢乐", "哈哈", "笑", "太好了"],
    ),
    "surprised": MotionType(
        id="surprised",
        name="惊讶",
        description="表达惊讶和意外",
        keywords=["惊讶", "意外", "哇", "天啊", "不会吧", "真的吗", "震惊"],
    ),
    "angry": MotionType(
        id="angry",
        name="生气",
        description="表达愤怒和不满的情绪",
        keywords=["生气", "愤怒", "恼火", "气死", "讨厌", "烦", "不爽"],
    ),
    "sad": MotionType(
        id="sad",
        name="难过",
        description="表达悲伤和难过",
        keywords=["难过", "伤心", "悲伤", "哭", "郁闷", "失落", "痛苦"],
    ),
    "agree": MotionType(
        id="agree",
        name="肯定",
        description="表达同意和肯定",
        keywords=["是的", "对的", "没错", "同意", "肯定", "当然", "确实"],
    ),
    "disagree": MotionType(
        id="disagree",
        name="否定",
        description="表达不同意和否定",
        keywords=["不是", "不对", "错了", "不同意", "否定", "当然不", "没有"],
    ),
    "question": MotionType(
        id="question",
        name="疑问",
        description="表达疑问和询问",
        keywords=["什么", "怎么", "如何", "哪里", "谁", "为什么", "吗", "呢"],
    ),
    "welcome": MotionType(
        id="welcome",
        name="欢迎",
        description="欢迎和打招呼",
        keywords=["欢迎", "你好", "您好", "大家好", "来了", "欢迎回来"],
    ),
    "thanks": MotionType(
        id="thanks",
        name="感谢",
        description="表达感谢和致意",
        keywords=["谢谢", "感谢", "谢了", "多谢", "感谢你", "太感谢了"],
    ),
    "apology": MotionType(
        id="apology",
        name="道歉",
        description="表达歉意和道歉",
        keywords=["对不起", "抱歉", "不好意思", "道歉", "错怪", "抱歉抱歉"],
    ),
    "goodbye": MotionType(
        id="goodbye",
        name="告别",
        description="告别和送别",
        keywords=["再见", "拜拜", "88", "下次见", "回头见", "告别"],
    ),
    "excited": MotionType(
        id="excited",
        name="兴奋",
        description="兴奋和激动的情绪",
        keywords=["兴奋", "激动", "太棒了", "太好了", "万岁", "厉害", "牛"],
    ),
}


class MotionTypeMatcher:
    """动作类型智能匹配器"""

    def __init__(self):
        self.motion_types = MOTION_TYPES

    def match_motion_type(self, text: str) -> str:
        """根据文本内容智能匹配动作类型

        Args:
            text: 待匹配的文本

        Returns:
            匹配的动作类型ID，默认返回 'idle'
        """
        if not text or not text.strip():
            return "idle"

        text = text.strip().lower()

        # 计算每种类型的匹配分数
        scores = {}
        for type_id, motion_type in self.motion_types.items():
            score = 0
            for keyword in motion_type.keywords:
                if keyword.lower() in text:
                    score += len(keyword)  # 关键词越长，分数越高

            if score > 0:
                scores[type_id] = score

        # 返回分数最高的类型
        if scores:
            best_type = max(scores.items(), key=lambda x: x[1])
            logger.debug(
                f"[动作匹配] 文本: {text[:20]}... -> 类型: {best_type[0]} (分数: {best_type[1]})"
            )
            return best_type[0]

        # 默认返回待机
        logger.debug(f"[动作匹配] 文本: {text[:20]}... -> 类型: idle (默认)")
        return "idle"

    def get_motion_type_info(self, type_id: str) -> MotionType | None:
        """获取动作类型信息"""
        return self.motion_types.get(type_id)

    def get_all_motion_types(self) -> list[MotionType]:
        """获取所有动作类型"""
        return list(self.motion_types.values())


# 全局匹配器实例
motion_matcher = MotionTypeMatcher()


def enhance_perform_sequence_with_motion_type(
    sequence: list[dict], motion_type: str
) -> list[dict]:
    """为表演序列添加动作类型信息

    Args:
        sequence: 原始表演序列
        motion_type: 动作类型

    Returns:
        增强后的表演序列
    """
    enhanced_sequence = []

    for item in sequence:
        enhanced_item = item.copy()

        # 为动作和表情添加动作类型信息
        if item.get("type") in ["motion", "expression"]:
            enhanced_item["motionType"] = motion_type

        enhanced_sequence.append(enhanced_item)

    return enhanced_sequence


def infer_motion_type_from_message(message_content: str) -> str:
    """从消息内容推断动作类型的便捷函数

    Args:
        message_content: 消息内容

    Returns:
        推断的动作类型ID
    """
    return motion_matcher.match_motion_type(message_content)
