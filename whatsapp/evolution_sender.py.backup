from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

import requests

_interrupted = False
_interruption_reason = ""


def _timeout():
    return int(os.getenv("EVOLUTION_TIMEOUT", "30"))


def headers(api_key: str):
    return {"apikey": api_key, "Content-Type": "application/json"}


def interrupted():
    return _interrupted, _interruption_reason


def reset_interruption():
    global _interrupted, _interruption_reason
    _interrupted = False
    _interruption_reason = ""


def _config():
    url = os.getenv("EVOLUTION_URL", "").rstrip("/")
    key = os.getenv("EVOLUTION_KEY", "")
    instance = os.getenv("EVOLUTION_INSTANCE", "imoveisberti")
    if not url or not key or not instance:
        raise RuntimeError("EVOLUTION_URL, EVOLUTION_KEY e EVOLUTION_INSTANCE são obrigatórios.")
    return url, key, instance


def _check_response(response):
    global _interrupted, _interruption_reason
    body = response.text[:2000]
    low = body.lower()
    if response.status_code in (401, 403, 429):
        _interrupted = True
        _interruption_reason = f"Evolution recusou o envio (HTTP {response.status_code})."
        raise RuntimeError(_interruption_reason)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError:
        data = {}
    if isinstance(data, dict):
        text = str(data).lower()
        if any(x in text for x in ("restricted", "restriction", "blocked", "spam", "terms")):
            _interrupted = True
            _interruption_reason = "Evolution retornou sinal de bloqueio/restrição."
            raise RuntimeError(_interruption_reason)
    return data


def send_text(phone: str, message: str):
    if _interrupted:
        raise RuntimeError(_interruption_reason or "Envio interrompido.")
    url, key, instance = _config()
    phone = "".join(ch for ch in str(phone) if ch.isdigit())
    message = str(message or "").strip()
    if len(phone) < 10:
        raise ValueError("Telefone inválido.")
    if not message:
        raise ValueError("Mensagem vazia.")
    endpoint = f"{url}/message/sendText/{instance}"
    r = requests.post(endpoint, json={"number": phone, "text": message}, headers=headers(key), timeout=_timeout())
    return _check_response(r)


def send_media(phone: str, media_path: str, media_type: str = "", mimetype: str = "", caption: str = "", file_name: str = ""):
    if _interrupted:
        raise RuntimeError(_interruption_reason or "Envio interrompido.")
    url, key, instance = _config()
    phone = "".join(ch for ch in str(phone) if ch.isdigit())
    path = Path(media_path)
    if not path.is_file():
        raise FileNotFoundError(f"Mídia não encontrada: {path}")
    if not media_type:
        media_type = "image" if (mimetypes.guess_type(path.name)[0] or "").startswith("image/") else "video"
    if not mimetype:
        mimetype = mimetypes.guess_type(path.name)[0] or ("image/jpeg" if media_type == "image" else "video/mp4")
    if not file_name:
        file_name = path.name
    data64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "number": phone,
        "mediatype": media_type,
        "mimetype": mimetype,
        "caption": caption or "",
        "media": data64,
        "fileName": file_name,
    }
    endpoint = f"{url}/message/sendMedia/{instance}"
    r = requests.post(endpoint, json=payload, headers=headers(key), timeout=_timeout())
    return _check_response(r)
