"""Worker da fila segura integrada ao CRM.

DRY-RUN é o padrão.
No envio real, a Evolution retorna inicialmente PENDING.
O status posterior é atualizado pelo webhook MESSAGES_UPDATE.
"""

import os
import random
import time

try:
    from .safe_queue import (
        claim_next,
        mark_pending,
        mark_failed,
        MIN_DELAY_SECONDS,
        MAX_DELAY_SECONDS,
    )
    from .evolution_sender import send_text

except ImportError:
    from safe_queue import (
        claim_next,
        mark_pending,
        mark_failed,
        MIN_DELAY_SECONDS,
        MAX_DELAY_SECONDS,
    )
    from evolution_sender import send_text


DRY_RUN = os.getenv("SAFE_DRY_RUN", "1") != "0"


def process_once():
    item = claim_next()

    if not item:
        return False

    phone = item["phone"]
    message = item["message"]
    queue_id = item["id"]

    try:

        if DRY_RUN:

            print(
                f"[DRY-RUN] {phone}: "
                f"{message[:100]}"
            )

            # DRY-RUN continua sem chamar a Evolution.
            # Para manter o comportamento de teste,
            # marcamos como processado localmente.
            #
            # Não existe messageId da Evolution neste modo.
            mark_pending(
                queue_id,
                None
            )

            print(
                f"[DRY-RUN SENT] {phone} | "
                f"fila={queue_id}"
            )

            return True

        # -------------------------------------------------
        # ENVIO REAL
        # -------------------------------------------------

        response = send_text(
            phone,
            message
        )

        evolution_message_id = None

        if isinstance(response, dict):

            evolution_message_id = (
                response
                .get("key", {})
                .get("id")
            )

        if not evolution_message_id:
            raise RuntimeError(
                "Evolution aceitou o envio, "
                "mas não retornou o messageId."
            )

        # A Evolution respondeu PENDING.
        # O status real será atualizado por
        # MESSAGES_UPDATE.
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
            f"{exc}"
        )

        return False


def run():

    print("=" * 60)
    print("SAFE QUEUE WORKER")
    print("=" * 60)

    print(
        f"DRY_RUN = {DRY_RUN}"
    )

    print(
        f"Intervalo = "
        f"{MIN_DELAY_SECONDS}s até "
        f"{MAX_DELAY_SECONDS}s"
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