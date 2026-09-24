"""LangChain chat models for the report and the reputation dimension; the scanner itself never imports this."""
import os

REPORT_MODEL = os.environ.get("COMPANYSCAN_REPORT_MODEL", "openai:gpt-5")
REPUTATION_MODEL = os.environ.get("COMPANYSCAN_REPUTATION_MODEL", "openai:gpt-4o-mini")


def chat_model(name, **kwargs):
    try:
        from langchain.chat_models import init_chat_model
    except ImportError as exc:
        raise ValueError("LLM calls need LangChain: pip install -e '.[llm]'") from exc
    return init_chat_model(name, **kwargs)
