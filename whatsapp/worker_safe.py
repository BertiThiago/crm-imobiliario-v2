"""Worker da fila segura BERTI.

Processa itens pendentes continuamente, com atraso aleatório configurável.
Suporta texto e mídia e respeita opt-in/opt-out através do safe_queue.
"""
from __future__ import annotations

import os
import random
import time

from .safe_queue import (
    claim_next,
    mark_failed,
    mark_pending,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
)
from .evolution_sender import send_media, send_text

DRY_RUN = os.getenv("SAFE_DRY_RUN", "1") != "0"


def _message_id(response):
    if not isinstance(response, dict):
        return None
    key = response.get("key") or {}
    if isinstance(key, dict):
        return key.get("id") or key.get("messageId")
    return response.get("messageId")


def process_once():
    item = claim_next()
    if not item:
        return False

    qid = item["id"]
    phone = item["phone"]
    message = item.get("message") or ""
    media_path = item.get("media_path")
    media_type = item.get("media_type") or ""
    media_mimetype = item.get("media_mimetype") or ""
    media_name = item.get("media_name") or ""
    media_caption = item.get("media_caption")

    try:
        if DRY_RUN:
            print(f"[DRY-RUN] {phone} | mode={item.get('send_mode')} | {message[:100]}")
            mark_pending(qid, f"DRY-RUN-{qid}")
            return True

        if media_path:
            response = send_media(
                phone=phone,
                media_path=media_path,
                media_type=media_type,
                mimetype=media_mimetype,
                caption=media_caption if media_caption is not None else message,
                file_name=media_name,
            )
        else:
            response = send_text(phone, message)

        message_id = _message_id(response)
        if not message_id:
            raise RuntimeError("Evolution aceitou o envio, mas não retornou messageId.")

        mark_pending(qid, message_id)
        print(f"[PENDING] {phone} | queue={qid} | messageId={message_id}")
        return True

    except Exception as exc:
        mark_failed(qid, str(exc))
        print(f"[FAILED] {phone} | queue={qid} | {exc}")
        return False


def run():
    print("=" * 70)
    print("BERTI SAFE QUEUE WORKER")
    print(f"DRY_RUN={DRY_RUN}")
    print(f"DELAY={MIN_DELAY_SECONDS}-{MAX_DELAY_SECONDS}s")
    print("=" * 70)

    while True:
        processed = process_once()
        if processed:
            delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
            print(f"[WAIT] {delay:.1f}s")
            time.sleep(delay)
        else:
            time.sleep(2)


if __name__ == "__main__":
    run()
