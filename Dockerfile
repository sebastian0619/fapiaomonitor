FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libzbar0 \
    curl \
    build-essential \
    libclang-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Rust 和 Cargo
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# 通过 Cargo 安装 qrscan
RUN cargo install --locked --force qrscan

# 创建必要的目录
RUN mkdir -p /watch /app/uploads /app/tmp /app/static /app/templates

# 复制项目文件
COPY requirements.txt .
COPY *.py .
COPY static/* static/
COPY templates/* templates/

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量
ENV WATCH_DIR=/watch
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8080

# 运行 Web 服务器
CMD ["python", "web_app.py"] 