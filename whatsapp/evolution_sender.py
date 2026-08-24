import os
import requests


TIMEOUT_REQUEST = int(
    os.getenv("EVOLUTION_TIMEOUT", "30")
)

_interrupted = False
_interruption_reason = ""


def headers(api_key: str):
    return {
        "apikey": api_key,
        "Content-Type": "application/json",
    }


def interrupted():
    return _interrupted, _interruption_reason


def send_text(phone: str, message: str):
    """
    Envia uma mensagem de texto pela Evolution API.

    A configuração é lida no momento do envio para evitar
    que alterações nas variáveis de ambiente fiquem presas
    a valores antigos de um módulo já importado.
    """

    global _interrupted, _interruption_reason

    if _interrupted:
        raise RuntimeError(
            _interruption_reason or "Envio interrompido."
        )

    # Lê sempre a configuração atual do runtime.
    evolution_url = os.getenv(
        "EVOLUTION_URL", ""
    ).rstrip("/")

    evolution_key = os.getenv(
        "EVOLUTION_KEY", ""
    )

    evolution_instance = os.getenv(
        "EVOLUTION_INSTANCE",
        "imoveisberti"
    )

    if not evolution_url:
        raise RuntimeError(
            "EVOLUTION_URL não configurada."
        )

    if not evolution_key:
        raise RuntimeError(
            "EVOLUTION_KEY não configurada."
        )

    if not evolution_instance:
        raise RuntimeError(
            "EVOLUTION_INSTANCE não configurada."
        )

    phone = str(phone).strip()
    message = str(message).strip()

    if not phone:
        raise ValueError(
            "Telefone não informado."
        )

    if not message:
        raise ValueError(
            "Mensagem vazia."
        )

    url = (
        f"{evolution_url}/message/sendText/"
        f"{evolution_instance}"
    )

    payload = {
        "number": phone,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers(evolution_key),
            timeout=TIMEOUT_REQUEST,
        )

        body = response.text[:1000]
        body_lower = body.lower()

        if response.status_code in {
            401, 403, 429
        }:
            _interrupted = True
            _interruption_reason = (
                f"Evolution recusou o envio "
                f"(HTTP {response.status_code}). "
                "Novos envios foram interrompidos."
            )
            raise RuntimeError(
                _interruption_reason
            )

        restriction_signals = (
            "restricted",
            "restriction",
            "blocked",
            "spam",
            "terms",
            "massa",
            "mass",
            "automated",
            "automation",
        )

        if any(
            signal in body_lower
            for signal in restriction_signals
        ):
            _interrupted = True
            _interruption_reason = (
                "A Evolution API retornou sinal "
                "compatível com bloqueio, restrição "
                "ou automação. Novos envios foram "
                "interrompidos."
            )
            raise RuntimeError(
                _interruption_reason
            )

        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            return {}

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "Timeout na comunicação com a Evolution API."
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Não foi possível conectar à Evolution API."
        ) from exc

    except requests.exceptions.HTTPError as exc:
        status = (
            exc.response.status_code
            if exc.response is not None
            else "desconhecido"
        )

        raise RuntimeError(
            f"Evolution API retornou HTTP {status}."
        ) from exc