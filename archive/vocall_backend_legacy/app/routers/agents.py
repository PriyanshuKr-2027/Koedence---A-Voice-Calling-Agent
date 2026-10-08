from fastapi import APIRouter, HTTPException, status
from typing import List, Optional, Dict, Any
from uuid import UUID
import httpx
from pydantic import BaseModel
from app.models.schemas import AgentCreate, AgentUpdate, AgentResponse
from app.services.supabase_client import supabase
from app.core.config import settings

router = APIRouter(prefix="/agents", tags=["Agents"])

class EnhancePromptRequest(BaseModel):
    system_prompt: str

class EnhancePromptResponse(BaseModel):
    enhanced_prompt: str

class RunAnalysisResponse(BaseModel):
    summary: str = "stub"
    success_eval: str = "stub"
    structured_data: Dict[str, Any] = {}

@router.get("", response_model=List[AgentResponse])
async def list_agents(org_id: UUID):
    if not supabase:
        return []
    res = supabase.table("agents").select("*").eq("org_id", str(org_id)).execute()
    return res.data or []

@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(agent: AgentCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("agents").insert(agent.model_dump(mode="json")).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to create agent")
    return res.data[0]

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("agents").select("*").eq("id", str(agent_id)).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Agent not found")
    return res.data

@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: UUID, agent_update: AgentUpdate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    update_data = {k: v for k, v in agent_update.model_dump(mode="json").items() if v is not None}
    res = supabase.table("agents").update(update_data).eq("id", str(agent_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Agent not found or update failed")
    return res.data[0]

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    supabase.table("agents").delete().eq("id", str(agent_id)).execute()
    return None

@router.post("/{agent_id}/publish")
async def publish_agent(agent_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("agents").update({"published": True}).eq("id", str(agent_id)).execute()
    return {"message": "Agent published successfully", "agent": res.data[0] if res.data else None}

@router.post("/{agent_id}/enhance-prompt", response_model=EnhancePromptResponse)
async def enhance_agent_prompt(agent_id: UUID, payload: EnhancePromptRequest):
    """
    Enhances system prompt using Groq's llama-3.3-70b-versatile model.
    """
    prompt_to_enhance = payload.system_prompt.strip()
    if not prompt_to_enhance:
        raise HTTPException(status_code=400, detail="System prompt cannot be empty")

    groq_api_key = settings.GROQ_API_KEY

    if groq_api_key:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are an expert voice AI prompt engineer. "
                                    "Improve this voice agent system prompt for clarity, structure, role clarity, "
                                    "and low-latency conversational effectiveness, preserving original intent. "
                                    "Output ONLY the refined system prompt without conversational intro/outro."
                                ),
                            },
                            {"role": "user", "content": prompt_to_enhance},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1500,
                    },
                )

                if res.status_code == 200:
                    data = res.json()
                    enhanced_text = data["choices"][0]["message"]["content"].strip()
                    return EnhancePromptResponse(enhanced_prompt=enhanced_text)
        except Exception as e:
            print(f"Groq API call failed: {e}")

    fallback_enhanced = (
        f"# ROLE & PERSONA\n{prompt_to_enhance}\n\n"
        f"## CONVERSATIONAL STYLE\n"
        f"- Maintain a helpful, empathetic, and professional tone.\n"
        f"- Keep responses concise (1-2 sentences) optimized for real-time speech synthesis.\n\n"
        f"## INSTRUCTIONS\n"
        f"- Listen actively and confirm caller requests before executing actions.\n"
        f"- Ask clarifying questions when user instructions are ambiguous."
    )
    return EnhancePromptResponse(enhanced_prompt=fallback_enhanced)

@router.post("/{agent_id}/run-analysis", response_model=RunAnalysisResponse)
async def run_agent_analysis(agent_id: UUID):
    """
    Post-call analysis execution endpoint stub.
    Real implementation will be wired in Module P2-M10 (post-call pipeline).
    """
    return RunAnalysisResponse(
        summary="stub",
        success_eval="stub",
        structured_data={}
    )
