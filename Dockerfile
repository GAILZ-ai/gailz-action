FROM python:3.12-slim

WORKDIR /action

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY entrypoint.py .

ENTRYPOINT ["python", "/action/entrypoint.py"]
