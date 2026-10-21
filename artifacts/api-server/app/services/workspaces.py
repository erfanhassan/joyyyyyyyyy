from uuid import uuid4
from sqlalchemy import select, text
from fastapi import HTTPException
from app.db.models import Tenant, User, OrganizationMember, WorkspaceIdentity
from app.core.config import settings
from app.core.deployment_guard import is_public_deployment


def actor(request):
    state = request.scope.get("state", {})
    subject, email = state.get("clerk_user_id"), state.get("clerk_email")
    if not subject and not is_public_deployment():
        subject, email = "local-preview-owner", "preview-owner@localhost.invalid"
    if not subject or not email:
        raise HTTPException(401, "A verified sign-in is required.")
    return subject, email, bool(state.get("is_joy_owner")) or not is_public_deployment()


async def bind(db, subject, email, tenant):
    db.info["tenant_id"] = str(tenant.id)
    await db.execute(text("SELECT set_config('app.current_tenant_id', :id, true)"), {"id": str(tenant.id)})
    user = (await db.execute(select(User).where(
        (User.clerk_user_id == subject) | (User.email == email) | (User.email == subject)))).scalar_one_or_none()
    if user and user.tenant_id != tenant.id:
        raise HTTPException(409, "This identity already belongs to another workspace.")
    if not user:
        user = User(id=uuid4(), tenant_id=tenant.id, email=email, clerk_user_id=subject, role="owner")
        db.add(user)
        await db.flush()
        db.add(OrganizationMember(tenant_id=tenant.id, user_id=user.id, role="owner"))
    else:
        user.clerk_user_id = subject
        user.email = email
    identity = WorkspaceIdentity(clerk_user_id=subject, tenant_id=tenant.id, role=user.role)
    db.add(identity)
    await db.commit()
    return identity


async def workspace_for(request, db):
    subject, email, platform_owner = actor(request)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:subject))"), {"subject": subject})
    identity = (await db.execute(select(WorkspaceIdentity).where(
        WorkspaceIdentity.clerk_user_id == subject))).scalar_one_or_none()
    if identity:
        tenant = (await db.execute(select(Tenant).where(Tenant.id == identity.tenant_id))).scalar_one_or_none()
        if tenant:
            return tenant, identity.role
    if platform_owner:
        # One-time migration: only the verified platform owner may adopt the
        # sole imported business. Never choose the first of multiple businesses.
        candidates = (await db.execute(select(Tenant).limit(2))).scalars().all()
        if len(candidates) == 1:
            identity = await bind(db, subject, email, candidates[0])
            return candidates[0], identity.role
    raise HTTPException(404, "No workspace is linked to this account. Create a business workspace.")
