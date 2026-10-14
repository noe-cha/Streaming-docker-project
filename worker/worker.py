import os
import time
import redis

print("Demarrage du worker FFmpeg (Connecte a Garage S3)...")

try:
    r = redis.Redis(host=os.getenv('REDIS_HOST', 'redis'), port=6379, decode_responses=True)
    r.ping()
    print("Connexion a Redis etablie.")
except Exception as e:
    print(f"Erreur de connexion a Redis: {e}")

while True:
    print("En attente de taches d'encodage...")
    time.sleep(10)