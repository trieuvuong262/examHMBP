# syntax=docker/dockerfile:1
# Tag 3.13-slim (ổn định trên Hub). VPS: chỉ pull khi thiếu image local (deploy.sh).
ARG PYTHON_BASE_IMAGE=python:3.13-slim
FROM ${PYTHON_BASE_IMAGE}

# Ngăn Python tạo file .pyc và không buffer log
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Apt/LibreOffice nặng — cache mount + layer Docker giữ lại giữa các lần deploy
# (chỉ rebuild khi đổi dòng lệnh này hoặc base image).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        postgresql-client \
        gcc \
        pkg-config \
        libcairo2-dev \
        rclone \
        fonts-dejavu-core \
        fonts-noto-core \
        libreoffice-writer-nogui \
        libreoffice-calc-nogui \
    && rm -rf /var/lib/apt/lists/*

# Pip chỉ chạy lại khi đổi requirements.txt
COPY requirements.txt /app/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install -r requirements.txt

# Code app — layer này đổi mỗi deploy; apt/pip phía trên vẫn dùng cache
COPY . /app/
