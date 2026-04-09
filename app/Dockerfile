FROM python:3.11-slim
WORKDIR /app
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY vendor/sentinelops-sdk-src ./vendor/sentinelops-sdk-src
RUN pip install --no-cache-dir ./vendor/sentinelops-sdk-src
COPY app ./
CMD ["python", "main.py"]