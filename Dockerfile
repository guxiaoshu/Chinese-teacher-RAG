# 语文教学 RAG 助手 —— CPU 版镜像
# 注意：锁定 Python 3.11（3.14 下 torch/chroma 原生库会段错误）

FROM python:3.11-slim

ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖，利用 Docker 层缓存：改代码不用重装
COPY requirements.txt .
RUN pip install -r requirements.txt

# 代码与静态资源（models/ data/ ingest/ 走卷挂载，不打进镜像）
COPY src/ ./src/
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY config.yaml ./
COPY images/ ./images/

EXPOSE 8501

CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.headless", "true", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501"]
