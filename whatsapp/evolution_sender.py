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


def _media_root() -> Path:
    configured = os.getenv("CRM_MEDIA_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(os.getenv("DATABASE_ROOT", "/content/drive/MyDrive/BERTI_BOT/database")).expanduser().resolve() / "campanhas" / "midias")


def _resolve_media_path(media_path: str | os.PathLike) -> Path:
    if not media_path:
        raise ValueError("media_path não informado.")
    raw = Path(str(media_path)).expanduser()
    if raw.is_absolute():
        resolved = raw.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Mídia não encontrada: {resolved}")
        return resolved
    root = _media_root().resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"media_path relativo inválido: {media_path}") from exc
    if candidate.is_file():
        return candidate
    fallback = (root / raw.name).resolve()
    try:
        fallback.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"media_path relativo inválido: {media_path}") from exc
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"Mídia não encontrada. media_path={media_path!r}; MEDIA_ROOT={root}")


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
    body = response.text[:4000]
    if response.status_code in (401, 403, 429):
        _interrupted = True
        _interruption_reason = f"Evolution recusou o envio (HTTP {response.status_code})."
        raise RuntimeError(_interruption_reason)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Evolution API retornou HTTP {response.status_code}: {body[:1000]}") from exc
    try:
        data = response.json()
    except ValueError:
        data = {}
    if isinstance(data, dict):
        text = str(data).lower()
        signals = ("restricted", "restriction", "blocked", "spam", "terms", "massa", "mass", "automated", "automation")
        if any(s in text for s in signals):
            _interrupted = True
            _interruption_reason = "A Evolution API retornou sinal compatível com bloqueio, restrição ou automação. Novos envios foram interrompidos."
            raise RuntimeError(_interruption_reason)
    return data


def _post(endpoint: str, payload: dict):
    try:
        return _check_response(requests.post(endpoint, json=payload, headers=headers(os.getenv("EVOLUTION_KEY", "")), timeout=_timeout()))
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("Timeout na comunicação com a Evolution API.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError("Não foi possível conectar à Evolution API.") from exc


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
    return _post(f"{url}/message/sendText/{instance}", {"number": phone, "text": message})


def send_media(phone: str, media_path: str, media_type: str = "", mimetype: str = "", caption: str = "", file_name: str = ""):
    if _interrupted:
        raise RuntimeError(_interruption_reason or "Envio interrompido.")
    url, key, instance = _config()
    phone = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(phone) < 10:
        raise ValueError("Telefone inválido.")
    path = _resolve_media_path(media_path)
    if not media_type:
        detected = mimetypes.guess_type(path.name)[0] or ""
        media_type = "image" if detected.startswith("image/") else "video"
    if media_type not in {"image", "video"}:
        raise ValueError(f"media_type inválido: {media_type!r}")
    if not mimetype:
        mimetype = mimetypes.guess_type(path.name)[0] or ("image/jpeg" if media_type == "image" else "video/mp4")
    if not file_name:
        file_name = path.name
    data64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {"number": phone, "mediatype": media_type, "mimetype": mimetype, "caption": caption or "", "media": data64, "fileName": file_name}
    return _post(f"{url}/message/sendMedia/{instance}", payload)
