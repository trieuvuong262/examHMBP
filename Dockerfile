# Sử dụng Python 3.13.12 bản slim để tối ưu dung lượng
FROM python:3.13.12-slim

# Ngăn Python tạo file .pyc và không buffer log
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Cài đặt thư viện hệ thống cần thiết cho PostgreSQL + rclone (đồng bộ NAS)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    pkg-config \
    libcairo2-dev \
    rclone \
    fonts-dejavu-core \
    fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt requirements
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy toàn bộ code vào container
COPY . /app/