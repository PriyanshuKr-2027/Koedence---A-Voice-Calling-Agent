from datetime import datetime
from typing import Any, Dict, Literal, Optional, Union
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

# Literal enum for all 9 supported connector types
ConnectorType = Literal[
    "google_calendar",
    "hubspot",
    "salesforce",
    "supabase",
    "postgres",
    "slack",
    "whatsapp",
    "zapier",
    "custom_webhook",
]


class ConnectorConfigBase(BaseModel):
    connector_type: ConnectorType
    is_enabled: bool = False


# 1. Google Calendar Config
class GoogleCalendarConfig(BaseModel):
    credentials_json: str
    calendar_id: str
    timezone: str = "Asia/Kolkata"


# 2. HubSpot Config
class HubSpotConfig(BaseModel):
    access_token: str
    pipeline_id: str
    deal_stage_id: str


# 3. Salesforce Config
class SalesforceConfig(BaseModel):
    client_id: str
    client_secret: str
    instance_url: str
    refresh_token: str


# 4. Supabase Config
class SupabaseConnectorConfig(BaseModel):
    url: str
    anon_key: str
    table_name: str
    query_column: str


# 5. Postgres Config
class PostgresConfig(BaseModel):
    connection_string: str
    query_template: str  # query_template uses {contact_phone} as a placeholder


# 6. Slack Config
class SlackConfig(BaseModel):
    bot_token: str
    channel_id: str
    notify_on: Literal["frustration", "call_end", "both"] = "frustration"


# 7. WhatsApp Config
class WhatsAppConfig(BaseModel):
    provider: Literal["twilio", "plivo"] = "twilio"
    from_number: str
    message_template: str


# 8. Zapier Config
class ZapierConfig(BaseModel):
    webhook_url: str
    include_transcript: bool = True
    include_emotion: bool = True


# 9. Custom Webhook Config
class CustomWebhookConfig(BaseModel):
    url: str
    method: Literal["POST", "GET"] = "POST"
    headers: Dict[str, str] = Field(default_factory=dict)
    payload_template: str


# Type alias for any connector specific config
SpecificConnectorConfig = Union[
    GoogleCalendarConfig,
    HubSpotConfig,
    SalesforceConfig,
    SupabaseConnectorConfig,
    PostgresConfig,
    SlackConfig,
    WhatsAppConfig,
    ZapierConfig,
    CustomWebhookConfig,
]

CONNECTOR_CONFIG_MODELS: Dict[str, Any] = {
    "google_calendar": GoogleCalendarConfig,
    "hubspot": HubSpotConfig,
    "salesforce": SalesforceConfig,
    "supabase": SupabaseConnectorConfig,
    "postgres": PostgresConfig,
    "slack": SlackConfig,
    "whatsapp": WhatsAppConfig,
    "zapier": ZapierConfig,
    "custom_webhook": CustomWebhookConfig,
}


# Create Model
class ConnectorConfigCreate(ConnectorConfigBase):
    org_id: UUID
    agent_id: Optional[UUID] = None
    config: Dict[str, Any] = Field(default_factory=dict)


# Update Model (makes all fields Optional)
class ConnectorConfigUpdate(BaseModel):
    connector_type: Optional[ConnectorType] = None
    is_enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


# Response Model
class ConnectorConfigResponse(ConnectorConfigBase):
    id: UUID
    org_id: UUID
    agent_id: Optional[UUID] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
