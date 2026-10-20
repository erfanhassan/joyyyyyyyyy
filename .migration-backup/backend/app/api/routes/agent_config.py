import logging
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import AgentConfig, Tenant

logger = logging.getLogger("joy.routes.agent_config")
router = APIRouter(prefix="/tenant", tags=["Digital Employee Roster Management"])


class AgentUpdatePayload(BaseModel):
    name: Optional[str] = None
    tone_settings: Optional[Dict[str, Any]] = None
    max_discount_pct: Optional[int] = Field(None, ge=0, le=50)
    operational_hours: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None


class AgentCreatePayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    agent_type: str = Field(..., description="'social_sales', 'voice_confirmation', 'returns', 'support'")
    system_prompt: str = Field(..., min_length=10)
    tone_settings: Dict[str, Any] = Field(default_factory=lambda: {"formality": 0.5, "enthusiasm": 0.8})
    max_discount_pct: int = Field(10, ge=0, le=50)
    operational_hours: Dict[str, Any] = Field(
        default_factory=lambda: {"start": "08:00", "end": "21:00", "timezone": "Asia/Dhaka"}
    )
    is_active: bool = True


@router.get("/{tenant_id}/agents")
async def list_tenant_agents(tenant_id: UUID, db: AsyncSession = Depends(get_db)):
    """Fetches all active and configured digital employees from PostgreSQL for the merchant."""
    stmt = (
        select(AgentConfig)
        .where(AgentConfig.tenant_id == tenant_id)
        .order_by(AgentConfig.created_at.asc())
    )
    res = await db.execute(stmt)
    agents = res.scalars().all()

    # If no agents exist yet, seed standard Employee #1 and Employee #2 defaults
    if not agents:
        emp1 = AgentConfig(
            id=uuid4(),
            tenant_id=tenant_id,
            agent_type="social_sales",
            name="Social Sales Specialist (Employee #1)",
            system_prompt=(
                "You are Employee #1, an elite Social Sales Specialist for the merchant store. "
                "Monitor public comments, DMs, and live chat. Look up items in the store catalog, "
                "verify stock, and generate personalized direct checkout links."
            ),
            tone_settings={"tone_slider": 75, "formality": 0.3, "enthusiasm": 0.8},
            max_discount_pct=10,
            operational_hours={"start": "00:00", "end": "23:59", "timezone": "Asia/Dhaka"},
            is_active=True,
        )
        emp2 = AgentConfig(
            id=uuid4(),
            tenant_id=tenant_id,
            agent_type="voice_confirmation",
            name="Phone Confirmation Specialist (Employee #2)",
            system_prompt=(
                "You are Employee #2, a Voice Confirmation Specialist for e-commerce orders. "
                "Autonomously call customers to verify order items, delivery addresses, and payment methods. "
                "Adhere strictly to local daytime calling hours (8 AM to 9 PM)."
            ),
            tone_settings={"tone_slider": 50, "formality": 0.7, "enthusiasm": 0.5},
            max_discount_pct=0,
            operational_hours={"start": "08:00", "end": "21:00", "timezone": "Asia/Dhaka"},
            is_active=True,
        )
        db.add_all([emp1, emp2])
        await db.commit()
        await db.refresh(emp1)
        await db.refresh(emp2)
        agents = [emp1, emp2]

    return {
        "tenant_id": str(tenant_id),
        "agents": [
            {
                "id": str(a.id),
                "name": a.name,
                "agent_type": a.agent_type,
                "system_prompt": a.system_prompt,
                "tone_settings": a.tone_settings or {},
                "max_discount_pct": a.max_discount_pct,
                "operational_hours": a.operational_hours or {},
                "is_active": a.is_active,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in agents
        ],
    }


@router.put("/{tenant_id}/agents/{agent_id}")
async def update_agent_config(
    tenant_id: UUID,
    agent_id: UUID,
    payload: AgentUpdatePayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Updates digital employee guardrails in PostgreSQL: tone sliders, discount caps,
    system prompts, and operational hours.
    """
    stmt = select(AgentConfig).where(
        AgentConfig.id == agent_id,
        AgentConfig.tenant_id == tenant_id,
    )
    res = await db.execute(stmt)
    agent = res.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found for tenant '{tenant_id}'.",
        )

    if payload.name is not None:
        agent.name = payload.name.strip()
    if payload.tone_settings is not None:
        agent.tone_settings = payload.tone_settings
    if payload.max_discount_pct is not None:
        agent.max_discount_pct = payload.max_discount_pct
    if payload.operational_hours is not None:
        agent.operational_hours = payload.operational_hours
    if payload.system_prompt is not None:
        agent.system_prompt = payload.system_prompt
    if payload.is_active is not None:
        agent.is_active = payload.is_active

    await db.commit()
    await db.refresh(agent)

    logger.info(f"Updated agent {agent_id} for tenant {tenant_id}: max_discount={agent.max_discount_pct}%")
    return {
        "status": "success",
        "agent_id": str(agent.id),
        "name": agent.name,
        "max_discount_pct": agent.max_discount_pct,
        "tone_settings": agent.tone_settings,
        "is_active": agent.is_active,
        "message": f"Guardrails for '{agent.name}' saved to database successfully.",
    }


@router.post("/{tenant_id}/agents")
async def create_new_digital_employee(
    tenant_id: UUID,
    payload: AgentCreatePayload,
    db: AsyncSession = Depends(get_db),
):
    """Hires a new specialized digital employee and registers their record in PostgreSQL."""
    new_agent = AgentConfig(
        id=uuid4(),
        tenant_id=tenant_id,
        agent_type=payload.agent_type,
        name=payload.name.strip(),
        system_prompt=payload.system_prompt,
        tone_settings=payload.tone_settings,
        max_discount_pct=payload.max_discount_pct,
        operational_hours=payload.operational_hours,
        is_active=payload.is_active,
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

    logger.info(f"Hired new digital employee '{new_agent.name}' ({new_agent.agent_type}) for tenant {tenant_id}")
    return {
        "status": "success",
        "agent": {
            "id": str(new_agent.id),
            "name": new_agent.name,
            "agent_type": new_agent.agent_type,
            "max_discount_pct": new_agent.max_discount_pct,
            "is_active": new_agent.is_active,
        },
        "message": f"Successfully onboarded {new_agent.name} to your digital workforce.",
    }
