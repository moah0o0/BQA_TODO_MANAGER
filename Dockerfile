FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 데이터 디렉토리 생성 (SQLite DB 저장용)
RUN mkdir -p /app/data

# 환경 변수 설정
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV DATABASE_PATH=/app/data/database.db

# 포트 노출
EXPOSE 8000

# gunicorn으로 실행
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app:app"]
