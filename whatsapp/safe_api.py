from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
try:
    from .safe_queue import dashboard,list_queue,enqueue,register_incoming,upsert_contact
except ImportError:
    from safe_queue import dashboard,list_queue,enqueue,register_incoming,upsert_contact
router=APIRouter(tags=["safe-mode"])
class ContactIn(BaseModel): phone:str; name:str=""; opt_in:bool=False
class IncomingIn(BaseModel): phone:str; name:str=""; text:str=""
class QueueIn(BaseModel): phone:str; message:str=Field(min_length=1); require_active:bool=True
@router.get("/dashboard")
def safe_dashboard(): return dashboard()
@router.get("/queue")
def safe_queue(limit:int=100): return list_queue(min(max(limit,1),500))
@router.post("/contacts")
def create_contact(data:ContactIn): upsert_contact(data.phone,data.name,data.opt_in); return {"ok":True,"phone":data.phone}
@router.post("/incoming")
def incoming(data:IncomingIn): register_incoming(data.phone,data.name,data.text); return {"ok":True,"phone":data.phone}
@router.post("/queue")
def add_queue(data:QueueIn):
    result=enqueue(data.phone,data.message,data.require_active)
    if not result["accepted"]: raise HTTPException(status_code=409,detail=result["reason"])
    return result
