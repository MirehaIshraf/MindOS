from pydantic import BaseModel


class ModelProvider(BaseModel):
    id: str
    name: str
    type: str
    configured: bool
    enabled: bool
    requires_api_key: bool
    has_api_key: bool = False
    available: bool | None = None
    privacy_note: str


class ModelConfig(BaseModel):
    id: str
    provider: str
    display_name: str
    model_id: str
    type: str
    enabled: bool
    configured: bool
    available: bool = False
    status: str = "unavailable"
    supports_tools: bool = False
    supports_vision: bool = False
    default_context_profile: str = "fast_chat"
    privacy_level: str
    description: str


class ModelSettingsResponse(BaseModel):
    providers: list[ModelProvider]
    models: list[ModelConfig]
    selected_chat_model: str


class ChatModelsResponse(BaseModel):
    models: list[ModelConfig]
    selected_chat_model: str
    warning: str | None = None


class UpdateSelectedModelRequest(BaseModel):
    model_id: str


class UpdateProviderConfigRequest(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    enabled: bool = True


class UpdateModelEnabledRequest(BaseModel):
    model_id: str | None = None
    enabled: bool
