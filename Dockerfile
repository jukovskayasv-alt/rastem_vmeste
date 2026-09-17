FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 skif
COPY . .
RUN mkdir -p runtime && chown -R skif:skif /app
USER skif
CMD ["python", "-m", "skif_agents", "run"]
