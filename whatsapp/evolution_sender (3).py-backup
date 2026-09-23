import os
import base64
import mimetypes
from pathlib import Path

import requests


TIMEOUT_REQUEST = int(
    os.getenv("EVOLUTION_TIMEOUT", "30")
)

_interrupted = False
_interruption_reason = ""


# ============================================================
# CONFIGURAÇÃO / HEADERS
# ============================================================

def headers(api_key: str):
    return {
        "apikey": api_key,
        "Content-Type": "application/json",
    }


# ============================================================
# CONTROLE DE INTERRUPÇÃO
# ============================================================

def interrupted():
    return _interrupted, _interruption_reason


def reset_interruption():
    """
    Libera novamente os envios depois de uma interrupção manual.
    """
    global _interrupted, _interruption_reason

    _interrupted = False
    _interruption_reason = ""


def _check_interrupted():
    if _interrupted:
        raise RuntimeError(
            _interruption_reason or "Envio interrompido."
        )


# ============================================================
# CONFIGURAÇÃO DA EVOLUTION
# ============================================================

def _config():
    """
    Lê a configuração no momento do envio.

    Isso evita que alterações nas variáveis de ambiente
    fiquem presas a valores antigos de um módulo já importado.
    """

    evolution_url = os.getenv(
        "EVOLUTION_URL",
        ""
    ).rstrip("/")

    evolution_key = os.getenv(
        "EVOLUTION_KEY",
        ""
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

    return (
        evolution_url,
        evolution_key,
        evolution_instance,
    )


# ============================================================
# TRATAMENTO DE RESPOSTA
# ============================================================

def _extract_message_id(data):
    """
    Tenta extrair o ID da mensagem retornado pela Evolution.

    Estrutura esperada normalmente:

    {
        "key": {
            "id": "..."
        },
        ...
    }

    Mantemos algumas alternativas para aumentar a
    compatibilidade entre versões.
    """

    if not isinstance(data, dict):
        return None

    # Estrutura principal
    key = data.get("key")

    if isinstance(key, dict):
        message_id = key.get("id")

        if message_id:
            return str(message_id)

    # Algumas respostas podem vir encapsuladas
    for container_name in (
        "data",
        "message",
        "response",
        "result",
    ):

        container = data.get(
            container_name
        )

        if isinstance(container, dict):

            key = container.get("key")

            if isinstance(key, dict):

                message_id = key.get("id")

                if message_id:
                    return str(message_id)

            # Algumas APIs retornam messageId diretamente
            message_id = container.get(
                "messageId"
            )

            if message_id:
                return str(message_id)

    # Última tentativa no nível principal
    message_id = data.get(
        "messageId"
    )

    if message_id:
        return str(message_id)

    return None


def _response_json(response):
    """
    Converte a resposta para dict quando possível.
    """

    try:
        data = response.json()

        if isinstance(data, dict):
            return data

        return {}

    except ValueError:
        return {}


# ============================================================
# DETECÇÃO DE RESTRIÇÃO / BLOQUEIO
# ============================================================

def _check_response_for_restriction(response):
    """
    Analisa HTTP e corpo da resposta procurando sinais
    de bloqueio, restrição ou automação.

    Se encontrar um sinal grave, interrompe novos envios.
    """

    global _interrupted
    global _interruption_reason

    body = response.text[:2000]
    body_lower = body.lower()

    # Bloqueios HTTP graves
    if response.status_code in {
        401,
        403,
        429,
    }:

        _interrupted = True

        _interruption_reason = (
            "Evolution recusou o envio "
            f"(HTTP {response.status_code}). "
            "Novos envios foram interrompidos."
        )

        raise RuntimeError(
            _interruption_reason
        )

    # Sinais textuais de restrição
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


# ============================================================
# POST GENÉRICO
# ============================================================

def _post_json(
    url: str,
    api_key: str,
    payload: dict,
):
    """
    Executa POST JSON na Evolution API.
    """

    _check_interrupted()

    try:

        response = requests.post(
            url,
            json=payload,
            headers=headers(api_key),
            timeout=TIMEOUT_REQUEST,
        )

        _check_response_for_restriction(
            response
        )

        response.raise_for_status()

        return _response_json(
            response
        )

    except requests.exceptions.Timeout as exc:

        raise RuntimeError(
            "Timeout na comunicação "
            "com a Evolution API."
        ) from exc

    except requests.exceptions.ConnectionError as exc:

        raise RuntimeError(
            "Não foi possível conectar "
            "à Evolution API."
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


# ============================================================
# ENVIO DE TEXTO
# ============================================================

def send_text(
    phone: str,
    message: str,
):
    """
    Envia uma mensagem de texto pela Evolution API.

    Retorna o JSON bruto da Evolution.
    """

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

    (
        evolution_url,
        evolution_key,
        evolution_instance,
    ) = _config()

    url = (
        f"{evolution_url}"
        f"/message/sendText/"
        f"{evolution_instance}"
    )

    payload = {
        "number": phone,
        "text": message,
    }

    return _post_json(
        url,
        evolution_key,
        payload,
    )


# ============================================================
# INFERÊNCIA DE MIME TYPE
# ============================================================

def _guess_mimetype(
    media_path: str,
    provided_mimetype: str = "",
):
    """
    Determina o MIME type.

    Prioridade:
    1. mimetype informado pelo CRM
    2. extensão do arquivo
    3. application/octet-stream
    """

    provided_mimetype = str(
        provided_mimetype or ""
    ).strip()

    if provided_mimetype:
        return provided_mimetype

    guessed, _ = mimetypes.guess_type(
        media_path
    )

    if guessed:
        return guessed

    return "application/octet-stream"


# ============================================================
# INFERÊNCIA DO TIPO DE MÍDIA
# ============================================================

def _guess_media_type(
    media_path: str,
    media_type: str = "",
    mimetype: str = "",
):
    """
    Converte o tipo interno do CRM para os tipos
    aceitos pela Evolution:

        image
        video
        audio
        document
    """

    media_type = str(
        media_type or ""
    ).strip().lower()

    if media_type in {
        "image",
        "video",
        "audio",
        "document",
    }:
        return media_type

    mimetype = str(
        mimetype or ""
    ).lower()

    if mimetype.startswith(
        "image/"
    ):
        return "image"

    if mimetype.startswith(
        "video/"
    ):
        return "video"

    if mimetype.startswith(
        "audio/"
    ):
        return "audio"

    return "document"


# ============================================================
# BASE64
# ============================================================

def _file_to_base64(
    media_path: str,
):
    """
    Lê o arquivo local e transforma em Base64.

    A Evolution aceita a mídia no campo 'media' como
    URL ou Base64 no endpoint sendMedia.
    """

    path = Path(
        media_path
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Mídia não encontrada: {media_path}"
        )

    if not path.is_file():

        raise ValueError(
            f"O caminho informado não é um arquivo: "
            f"{media_path}"
        )

    try:

        with path.open(
            "rb"
        ) as file:

            content = file.read()

    except OSError as exc:

        raise RuntimeError(
            f"Não foi possível ler a mídia: "
            f"{media_path}"
        ) from exc

    if not content:

        raise ValueError(
            f"O arquivo de mídia está vazio: "
            f"{media_path}"
        )

    return base64.b64encode(
        content
    ).decode("utf-8")


# ============================================================
# ENVIO DE MÍDIA
# ============================================================

def send_media(
    phone: str,
    media_path: str,
    media_type: str = "",
    mimetype: str = "",
    caption: str = "",
    file_name: str = "",
):
    """
    Envia imagem, vídeo, áudio ou documento pela
    Evolution API.

    O arquivo é lido localmente e convertido para
    Base64 antes de ser enviado.

    Parâmetros:

        phone
            Número do destinatário.

        media_path
            Caminho local do arquivo.

        media_type
            image | video | audio | document

        mimetype
            Ex.: image/jpeg, video/mp4, application/pdf

        caption
            Legenda da mídia.

        file_name
            Nome exibido para o arquivo.
    """

    phone = str(
        phone or ""
    ).strip()

    media_path = str(
        media_path or ""
    ).strip()

    media_type = str(
        media_type or ""
    ).strip().lower()

    mimetype = str(
        mimetype or ""
    ).strip()

    caption = str(
        caption or ""
    )

    file_name = str(
        file_name or ""
    ).strip()

    if not phone:

        raise ValueError(
            "Telefone não informado."
        )

    if not media_path:

        raise ValueError(
            "Caminho da mídia não informado."
        )

    # Confere existência antes de montar o payload.
    path = Path(
        media_path
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Mídia não encontrada: {media_path}"
        )

    if not path.is_file():

        raise ValueError(
            f"O caminho informado não é um arquivo: "
            f"{media_path}"
        )

    # MIME
    mimetype = _guess_mimetype(
        media_path,
        mimetype,
    )

    # Tipo da mídia
    media_type = _guess_media_type(
        media_path,
        media_type,
        mimetype,
    )

    # Nome do arquivo
    if not file_name:
        file_name = path.name

    # Base64
    media_base64 = _file_to_base64(
        media_path
    )

    (
        evolution_url,
        evolution_key,
        evolution_instance,
    ) = _config()

    url = (
        f"{evolution_url}"
        f"/message/sendMedia/"
        f"{evolution_instance}"
    )

    payload = {
        "number": phone,
        "mediatype": media_type,
        "mimetype": mimetype,
        "caption": caption,
        "media": media_base64,
        "fileName": file_name,
    }

    return _post_json(
        url,
        evolution_key,
        payload,
    )


# ============================================================
# ENVIO UNIFICADO
# ============================================================

def send(
    phone: str,
    message: str = "",
    media_path: str = "",
    media_type: str = "",
    media_mimetype: str = "",
    media_caption: str = "",
    media_name: str = "",
):
    """
    Função unificada.

    Sem mídia:
        send_text()

    Com mídia:
        send_media()

    Isso permite que o worker simplesmente entregue
    os dados da fila para esta função.
    """

    media_path = str(
        media_path or ""
    ).strip()

    if media_path:

        return send_media(
            phone=phone,
            media_path=media_path,
            media_type=media_type,
            mimetype=media_mimetype,
            caption=media_caption,
            file_name=media_name,
        )

    return send_text(
        phone=phone,
        message=message,
    )


# ============================================================
# EXTRAÇÃO DO MESSAGE ID
# ============================================================

def extract_message_id(
    response_data,
):
    """
    Extrai o Evolution message ID da resposta.

    Estrutura esperada:

        {
            "key": {
                "id": "..."
            }
        }
    """

    if not isinstance(
        response_data,
        dict,
    ):
        return None

    key = response_data.get(
        "key"
    )

    if isinstance(
        key,
        dict,
    ):

        message_id = key.get(
            "id"
        )

        if message_id:
            return str(
                message_id
            )

    # Compatibilidade com respostas encapsuladas.
    for container_name in (
        "data",
        "response",
        "result",
    ):

        container = response_data.get(
            container_name
        )

        if isinstance(
            container,
            dict,
        ):

            key = container.get(
                "key"
            )

            if isinstance(
                key,
                dict,
            ):

                message_id = key.get(
                    "id"
                )

                if message_id:
                    return str(
                        message_id
                    )

            message_id = container.get(
                "messageId"
            )

            if message_id:
                return str(
                    message_id
                )

    message_id = response_data.get(
        "messageId"
    )

    if message_id:
        return str(
            message_id
        )

    return None
```
