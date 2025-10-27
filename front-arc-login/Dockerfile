FROM python:3.11-slim

WORKDIR /app
COPY app.py /app/
COPY static /app/static
COPY config /app/config

RUN pip install fastapi uvicorn requests python-multipart pyyaml

EXPOSE 6123
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "6123"]
