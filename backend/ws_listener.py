"""
Bridges Celery task progress (published to Redis pub/sub by tasks.py) to SocketIO clients.
Runs as a background task inside the Flask/SocketIO process.
"""

import json
import os

import redis


def start_listener(socketio):
    def listen():
        redis_client = redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
        pubsub = redis_client.pubsub()
        pubsub.psubscribe('job:*:progress')

        for message in pubsub.listen():
            if message['type'] != 'pmessage':
                continue

            try:
                channel = message['channel'].decode('utf-8')
                job_id = channel.split(':')[1]
                data = json.loads(message['data'])
                socketio.emit('job_progress', data, room=f'job_{job_id}')
            except Exception as exc:
                print(f"[ws_listener] Failed to process message: {exc}")

    socketio.start_background_task(listen)
