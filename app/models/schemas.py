from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

# 1. ORGANIZATIONS
class OrganizationBase(BaseModel):
    name: str
    domain: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None

class OrganizationCreate(OrganizationBase):
    pass

class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None

class OrganizationResponse(OrganizationBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 2. PROFILES
class ProfileBase(BaseModel):
    org_id: Optional[UUID] = None
    role: Optional[str] = "member"
    name: Optional[str] = None
    avatar_url: Optional[str] = None

class ProfileCreate(ProfileBase):
    id: UUID

class ProfileUpdate(BaseModel):
    org_id: Optional[UUID] = None
    role: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None

class ProfileResponse(ProfileBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 3. SPACES
class SpaceBase(BaseModel):
    org_id: UUID
    name: str

class SpaceCreate(SpaceBase):
    pass

class SpaceUpdate(BaseModel):
    name: Optional[str] = None

class SpaceResponse(SpaceBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 4. AGENTS
class AgentBase(BaseModel):
    space_id: Optional[UUID] = None
    org_id: UUID
    name: str
    system_prompt: Optional[str] = None
    voice_id: Optional[str] = None
    voice_provider: Optional[str] = None
    language: Optional[str] = "en"
    config: Optional[Dict[str, Any]] = {}
    published: Optional[bool] = False
    enable_memory: Optional[bool] = False
    enable_emotion: Optional[bool] = False

class AgentCreate(AgentBase):
    pass

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    space_id: Optional[UUID] = None
    system_prompt: Optional[str] = None
    voice_id: Optional[str] = None
    voice_provider: Optional[str] = None
    language: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    published: Optional[bool] = None
    enable_memory: Optional[bool] = None
    enable_emotion: Optional[bool] = None

class AgentResponse(AgentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 5. API KEYS
class APIKeyCreate(BaseModel):
    org_id: UUID
    provider: str
    encrypted_key: str

class APIKeyResponse(BaseModel):
    id: UUID
    org_id: UUID
    provider: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 6. PHONE NUMBERS
class PhoneNumberCreate(BaseModel):
    org_id: UUID
    agent_id: Optional[UUID] = None
    number: str
    provider: Optional[str] = None

class PhoneNumberResponse(BaseModel):
    id: UUID
    org_id: UUID
    agent_id: Optional[UUID] = None
    number: str
    provider: Optional[str] = None
    kyc_status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 7. CONTACTS
class ContactBase(BaseModel):
    org_id: UUID
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    tags: Optional[List[str]] = []

class ContactCreate(ContactBase):
    pass

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    tags: Optional[List[str]] = None

class ContactResponse(ContactBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 8. CONNECTORS
class ConnectorBase(BaseModel):
    agent_id: Optional[UUID] = None
    org_id: UUID
    type: str
    trigger_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = {}
    enabled: Optional[bool] = True

class ConnectorCreate(ConnectorBase):
    pass

class ConnectorUpdate(BaseModel):
    type: Optional[str] = None
    trigger_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None

class ConnectorResponse(ConnectorBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 9. CALLS
class CallBase(BaseModel):
    agent_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    org_id: UUID
    direction: Optional[str] = None
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    status: Optional[str] = "initiated"
    duration_seconds: Optional[int] = 0
    transcript: Optional[str] = None
    is_test: Optional[bool] = False
    emotion_score: Optional[float] = None
    analysis: Optional[Dict[str, Any]] = {}
    post_processed_at: Optional[datetime] = None
    post_steps: Optional[Dict[str, Any]] = {}

class CallCreate(CallBase):
    pass

class CallUpdate(BaseModel):
    status: Optional[str] = None
    duration_seconds: Optional[int] = None
    transcript: Optional[str] = None
    emotion_score: Optional[float] = None
    analysis: Optional[Dict[str, Any]] = None
    post_processed_at: Optional[datetime] = None
    post_steps: Optional[Dict[str, Any]] = None

class CallResponse(CallBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class LiveKitTokenRequest(BaseModel):
    room_name: str
    participant_name: str
    agent_id: Optional[UUID] = None

class LiveKitTokenResponse(BaseModel):
    token: str
    room_name: str
    livekit_url: str

# 10. MEMORY LONG TERM
class MemoryLongTermCreate(BaseModel):
    contact_id: Optional[UUID] = None
    org_id: UUID
    agent_id: Optional[UUID] = None
    call_id: Optional[UUID] = None
    content: str
    embedding: Optional[List[float]] = None
    emotion_state: Optional[Dict[str, Any]] = {}

class MemoryLongTermResponse(MemoryLongTermCreate):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 11. MEMORY EPISODIC
class MemoryEpisodicCreate(BaseModel):
    contact_id: Optional[UUID] = None
    call_id: Optional[UUID] = None
    org_id: UUID
    summary: Optional[str] = None
    key_facts: Optional[Dict[str, Any]] = {}
    emotion_arc: Optional[Dict[str, Any]] = {}
    entities: Optional[Dict[str, Any]] = {}
    topics: Optional[Dict[str, Any]] = {}

class MemoryEpisodicResponse(MemoryEpisodicCreate):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# 12. EMOTION EVENTS
class EmotionEventCreate(BaseModel):
    call_id: UUID
    timestamp_ms: Optional[int] = None
    valence: Optional[float] = None
    arousal: Optional[float] = None
    dominant: Optional[str] = None
    confidence: Optional[float] = None
    signal_source: Optional[str] = None

class EmotionEventResponse(EmotionEventCreate):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
