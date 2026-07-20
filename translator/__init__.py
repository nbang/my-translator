"""my-translator: provider-agnostic Chinese->Vietnamese web-novel translation toolkit.

Layers:
- translator.llm     : model-agnostic chat client + role routing
- translator.skills  : reusable, schema-described translation skills (tools)
- translator.workflow: deterministic pipeline runner over the skills
- translator.config  : config.yaml + .env loading
"""

__version__ = "0.2.0"
