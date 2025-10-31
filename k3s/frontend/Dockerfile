FROM python:3.11-slim

WORKDIR /app

# Copy frontend files
COPY static /app/static
COPY app.py /app/

# Install Flask and requests
RUN pip install --no-cache-dir flask requests

ENV FLASK_APP=app.py

EXPOSE 5000

CMD ["python", "-m", "flask", "run", "--host", "0.0.0.0", "--port", "5000"]
