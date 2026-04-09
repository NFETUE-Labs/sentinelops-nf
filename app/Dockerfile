FROM python:3.11-slim
WORKDIR /app
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "sentinelops @ git+https://github.com/NFETUE-Labs/sentinelops-python-sdk.git"
COPY app ./
CMD ["python", "main.py"]