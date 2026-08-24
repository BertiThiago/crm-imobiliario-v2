import os
import requests

EVOLUTION_URL=os.getenv("EVOLUTION_URL","").rstrip("/")
EVOLUTION_KEY=os.getenv("EVOLUTION_KEY","")
EVOLUTION_INSTANCE=os.getenv("EVOLUTION_INSTANCE","imoveisberti")
TIMEOUT_REQUEST=int(os.getenv("EVOLUTION_TIMEOUT","30"))
_interrupted=False
_interruption_reason=""

def headers(): return {"apikey":EVOLUTION_KEY,"Content-Type":"application/json"}
def interrupted(): return _interrupted,_interruption_reason

def send_text(phone:str,message:str):
    global _interrupted,_interruption_reason
    if _interrupted: raise RuntimeError(_interruption_reason or "Envio interrompido.")
    if not EVOLUTION_URL: raise RuntimeError("EVOLUTION_URL não configurada.")
    if not EVOLUTION_KEY: raise RuntimeError("EVOLUTION_KEY não configurada.")
    if not EVOLUTION_INSTANCE: raise RuntimeError("EVOLUTION_INSTANCE não configurada.")
    phone,message=str(phone).strip(),str(message).strip()
    if not phone: raise ValueError("Telefone não informado.")
    if not message: raise ValueError("Mensagem vazia.")
    url=f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    try:
        response=requests.post(url,json={"number":phone,"text":message},headers=headers(),timeout=TIMEOUT_REQUEST)
        body_lower=response.text[:1000].lower()
        if response.status_code in {401,403,429}:
            _interrupted=True; _interruption_reason=f"Evolution recusou o envio (HTTP {response.status_code}). Novos envios foram interrompidos."
            raise RuntimeError(_interruption_reason)
        restriction_signals=("restricted","restriction","blocked","spam","terms","massa","mass","automated","automation")
        if any(s in body_lower for s in restriction_signals):
            _interrupted=True; _interruption_reason="A Evolution API retornou sinal compatível com bloqueio, restrição ou automação. Novos envios foram interrompidos."
            raise RuntimeError(_interruption_reason)
        response.raise_for_status()
        try: return response.json()
        except ValueError: return {}
    except requests.exceptions.Timeout as exc: raise RuntimeError("Timeout na comunicação com a Evolution API.") from exc
    except requests.exceptions.ConnectionError as exc: raise RuntimeError("Não foi possível conectar à Evolution API.") from exc
    except requests.exceptions.HTTPError as exc:
        status=exc.response.status_code if exc.response is not None else "desconhecido"
        raise RuntimeError(f"Evolution API retornou HTTP {status}.") from exc
