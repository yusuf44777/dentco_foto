FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

WORKDIR /app

# OpenCV, pillow-heif ve insightface native build bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libheif-dev \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install "numpy==1.26.4" "Cython==0.29.37" \
    && python -m pip install -r requirements.txt

COPY . .

CMD ["sh", "start.sh"]
