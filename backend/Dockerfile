FROM python:3.12-slim

WORKDIR /app

# git: repository.py klonlama ve commit okuma icin git komutunu calistiriyor.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# torch'un varsayilan PyPI paketi CUDA kutuphanelerini de getirir (birkac GB).
# Bu imaj CPU'da calisiyor, o yuzden once CPU-only torch kurulur; ardindan
# requirements icindeki sentence-transformers onu zaten kurulu bulur.
RUN pip install --no-cache-dir torch==2.14.0 \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Embedding ve reranker modelleri ilk istekte indirilir. HF_HOME bir volume'a
# baglanirsa konteyner yeniden basladiginda tekrar indirilmezler.
ENV HF_HOME=/models

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
