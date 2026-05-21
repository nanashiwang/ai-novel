from fastapi import APIRouter

from app.api import (
    auth,
    billing,
    chapters,
    character_revisions,
    characters,
    events,
    generation_jobs,
    novel_specs,
    organizations,
    plot_thread_revisions,
    plot_threads,
    project_extra,
    projects,
    quotas,
    revisions,
    scenes,
    world_item_revisions,
    world_items,
)
from app.api.admin import content_reviews, logs, metrics, plans, settings, users
from app.api.admin import jobs as admin_jobs
from app.api.admin import organizations as admin_orgs

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(billing.router)
api_router.include_router(quotas.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(project_extra.router)
api_router.include_router(revisions.router)
api_router.include_router(novel_specs.router)
api_router.include_router(characters.router)
api_router.include_router(character_revisions.router)
api_router.include_router(character_revisions.project_router)
api_router.include_router(chapters.router)
api_router.include_router(scenes.router)
# Sprint 12-C: 注册 revision 子路由必须在 world_items/plot_threads 主路由之前，
# 否则 GET /projects/{pid}/world-items/pending-count 会被 /{item_id} 吞掉。
api_router.include_router(world_item_revisions.router)
api_router.include_router(plot_thread_revisions.router)
api_router.include_router(world_items.router)
api_router.include_router(plot_threads.router)
api_router.include_router(generation_jobs.router)
api_router.include_router(events.router)

# Admin
api_router.include_router(users.router)
api_router.include_router(admin_orgs.router)
api_router.include_router(plans.router)
api_router.include_router(admin_jobs.router)
api_router.include_router(logs.router)
api_router.include_router(content_reviews.router)
api_router.include_router(settings.router)
api_router.include_router(metrics.router)
