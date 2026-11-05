FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.lock .
RUN pip install -r requirements.lock
COPY . .
RUN pip install --no-deps .
EXPOSE 8000 8501
CMD ["uvicorn", "credit_risk_desk.api:app", "--host", "0.0.0.0", "--port", "8000"]
