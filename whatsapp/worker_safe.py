"""Worker da fila segura integrada ao CRM. DRY-RUN é o padrão."""
import os,random,time
try:
    from .safe_queue import claim_next,mark_sent,mark_failed,MIN_DELAY_SECONDS,MAX_DELAY_SECONDS
    from .evolution_sender import send_text
except ImportError:
    from safe_queue import claim_next,mark_sent,mark_failed,MIN_DELAY_SECONDS,MAX_DELAY_SECONDS
    from evolution_sender import send_text
DRY_RUN=os.getenv("SAFE_DRY_RUN","1")!="0"
def process_once():
    item=claim_next()
    if not item: return False
    phone,message,queue_id=item["phone"],item["message"],item["id"]
    try:
        if DRY_RUN: print(f"[DRY-RUN] {phone}: {message[:100]}")
        else: send_text(phone,message)
        mark_sent(queue_id); print(f"[SENT] {phone} | fila={queue_id}"); return True
    except Exception as exc:
        mark_failed(queue_id,str(exc)); print(f"[FAILED] {phone} | {exc}"); return False
def run():
    print("="*60); print("SAFE QUEUE WORKER"); print("="*60); print(f"DRY_RUN = {DRY_RUN}"); print(f"Intervalo = {MIN_DELAY_SECONDS}s até {MAX_DELAY_SECONDS}s"); print("="*60)
    while True:
        processed=process_once()
        if not processed: time.sleep(2); continue
        time.sleep(random.uniform(MIN_DELAY_SECONDS,MAX_DELAY_SECONDS))
if __name__=="__main__": run()
