from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class NFSAuth(BaseModel):
    login_url: Optional[str] = None
    session_check: Optional[Dict[str, Any]] = None
    login_fields: Dict[str, str] = Field(default_factory=dict)


class NFSExecution(BaseModel):
    type: Literal["navigate", "api_call", "fill_form", "click"]
    url_template: Optional[str] = None
    method: Optional[str] = None
    endpoint: Optional[str] = None
    body_template: Optional[Dict[str, Any]] = None
    field_registry: Optional[Dict[str, Any]] = None
    submit_selector: Optional[str] = None
    success_redirect: Optional[str] = None
    selector: Optional[str] = None


class NFSAction(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    requires_auth: bool = False
    trigger_intents: List[str] = Field(default_factory=list)
    params: List[str] = Field(default_factory=list)
    execution: Optional[NFSExecution] = None
    fallback: Optional[NFSExecution] = None


class NFSProduct(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    price: Optional[float] = None
    image: Optional[str] = None
    detail_url: Optional[str] = None


class NFSPage(BaseModel):
    url_pattern: Optional[str] = None
    label: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    content_type: Optional[str] = None
    products: List[NFSProduct] = Field(default_factory=list)
    actions: List[NFSAction] = Field(default_factory=list)


class NFSTree(BaseModel):
    domain: Optional[str] = None
    base_url: Optional[str] = None
    auth: Optional[NFSAuth] = None
    pages: Dict[str, NFSPage] = Field(default_factory=dict)
    created_at: Optional[str] = None
    version: int = 1


