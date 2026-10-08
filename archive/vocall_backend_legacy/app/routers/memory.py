from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/memory", tags=["Memory (VoCall Original)"])

@router.get("/long-term")
async def get_long_term_memory():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Long-term memory retrieval will be implemented in Module P2-M5."
    )

@router.post("/long-term")
async def store_long_term_memory():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Long-term memory embedding storage will be implemented in Module P2-M5."
    )

@router.get("/episodic")
async def get_episodic_memory():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Episodic memory summarization will be implemented in Module P2-M5."
    )
