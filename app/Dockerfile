FROM python:3.11-slim
WORKDIR /app
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY sentinelops-sdk ./sentinelops-sdk
RUN pip install --no-cache-dir ./sentinelops-sdk
COPY app ./
CMD ["python", "main.py"]