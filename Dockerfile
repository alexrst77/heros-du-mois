# Site « Mon Héros du Mois » en ligne (Railway, Render…). Un seul processus : les fabrications tournent en arrière-plan.
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
RUN mkdir -p /data
CMD gunicorn -w 1 --threads 16 --timeout 180 -b 0.0.0.0:${PORT} app:app
