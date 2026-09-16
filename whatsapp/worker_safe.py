"""Worker da Safe Queue.

Produção:
- somente envio real
- texto via Evolution sendText
- imagem/vídeo via Evolution sendMedia
"""

import os
import time
import random

try:
    from .safe_queue import (
        claim_next,
        mark_pending,
        mark_failed,
        MIN_DELAY_SECONDS,
        MAX_DELAY_SECONDS,
    )

    from .evolution_sender import (
        send_text,
        send_media,
    )

except ImportError:

    from safe_queue import (
        claim_next,
        mark_pending,
        mark_failed,
        MIN_DELAY_SECONDS,
        MAX_DELAY_SECONDS,
    )

    from evolution_sender import (
        send_text,
        send_media,
    )


def process_once():

    item = claim_next()

    if not item:
        return False

    phone = item["phone"]
    message = item["message"]
    queue_id = item["id"]

    try:

        media_path = item.get(
            "media_path"
        )

        media_type = item.get(
            "media_type"
        )

        media_mimetype = item.get(
            "media_mimetype"
        )

        media_name = item.get(
            "media_name"
        )

        media_caption = item.get(
            "media_caption"
        )

        # -------------------------------------------------
        # MÍDIA
        # -------------------------------------------------

        if media_path:

            print(
                f"[MEDIA] {phone} | "
                f"{media_type} | "
                f"{media_name or media_path}"
            )

            response = send_media(
                phone=phone,
                media_path=media_path,
                media_type=media_type,
                media_mimetype=media_mimetype,
                media_name=media_name,
                caption=(
                    media_caption
                    if media_caption is not None
                    else message
                ),
            )

        # -------------------------------------------------
        # TEXTO
        # -------------------------------------------------

        else:

            print(
                f"[TEXT] {phone}: "
                f"{message[:100]}"
            )

            response = send_text(
                phone,
                message
            )

        # -------------------------------------------------
        # MESSAGE ID
        # -------------------------------------------------

        evolution_message_id = None

        if isinstance(response, dict):

            key = response.get(
                "key",
                {}
            )

            if isinstance(key, dict):

                evolution_message_id = (
                    key.get("id")
                )

        if not evolution_message_id:

            raise RuntimeError(
                "Evolution aceitou o envio, "
                "mas não retornou o messageId."
            )

        # -------------------------------------------------
        # PENDING
        # -------------------------------------------------

        mark_pending(
            queue_id,
            evolution_message_id
        )

        print(
            f"[PENDING] {phone} | "
            f"fila={queue_id} | "
            f"messageId={evolution_message_id}"
        )

        return True

    except Exception as exc:

        mark_failed(
            queue_id,
            str(exc)
        )

        print(
            f"[FAILED] {phone} | "
            f"fila={queue_id} | "
            f"{exc}"
        )

        return False


def run():

    print("=" * 60)
    print("SAFE QUEUE WORKER — PRODUÇÃO")
    print("=" * 60)

    print(
        f"Intervalo = "
        f"{MIN_DELAY_SECONDS}s até "
        f"{MAX_DELAY_SECONDS}s"
    )

    print(
        "DRY_RUN removido."
    )

    print("=" * 60)

    while True:

        processed = process_once()

        if not processed:

            time.sleep(2)

            continue

        time.sleep(
            random.uniform(
                MIN_DELAY_SECONDS,
                MAX_DELAY_SECONDS
            )
        )


if __name__ == "__main__":

    run()