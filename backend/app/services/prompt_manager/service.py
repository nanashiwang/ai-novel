from pathlib import Path

PROMPT_ROOT = Path(__file__).resolve().parents[2] / "prompts"


class PromptManager:
    def load(self, key: str) -> str:
        path = PROMPT_ROOT / f"{key}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "你是 NovelFlow AI 的小说生产工作流节点，请严格遵守故事圣经、人物状态与世界观规则。"


prompt_manager = PromptManager()
