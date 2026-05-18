from fastapi import APIRouter

from app.api import (
    auth,
    billing,
    chapters,
    characters,
    generation_jobs,
    organizations,
    project_extra,
    projects,
    quotas,
    scenes,
    world_items,
)
from app.api.admin import content_reviews, logs, organizations as admin_orgs, settings, users
from app.api.admin import jobs as admin_jobs

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(billing.router)
api_router.include_router(quotas.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(project_extra.router)
api_router.include_router(characters.router)
api_router.include_router(chapters.router)
api_router.include_router(scenes.router)
api_router.include_router(world_items.router)
api_router.include_router(generation_jobs.router)

# Admin
api_router.include_router(users.router)
api_router.include_router(admin_orgs.router)
api_router.include_router(admin_jobs.router)
api_router.include_router(logs.router)
api_router.include_router(content_reviews.router)
api_router.include_router(settings.router)
