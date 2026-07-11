# Use flattened local base to avoid layer depth accumulation
FROM llmwiki-streamlit-base:flat AS base

WORKDIR /app

# Overlay updated Python source — no pip needed
COPY streamlit/app.py .
COPY streamlit/pages/ pages/
COPY streamlit/demo_variants.py demo_variants.py
COPY streamlit/skill_specs/ skill_specs/
COPY wiki_seed/ wiki_seed/

# Neuro SAN coded tools — LLMWiki domain tools (SK-01 to SK-05)
COPY neuro_san/coded_tools/ coded_tools/

# Shared common library — same source used by Lambda Layer and Neuro SAN coded tools
COPY lambda/common/ lambda_common/
ENV PYTHONPATH=/app/lambda_common

# Neuro SAN agent network definitions (HOCON) and shared config
COPY registries/ registries/
COPY config/llm_config.hocon config/llm_config.hocon

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]
