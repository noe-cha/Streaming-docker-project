FROM python:3.11-alpine

RUN apk add --no-cache ffmpeg

RUN adduser -D worker
USER worker
WORKDIR /home/worker

COPY --chown=worker:worker requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=worker:worker worker.py .

CMD ["python", "-u", "worker.py"]