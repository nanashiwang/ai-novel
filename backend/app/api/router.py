from fastapi import APIRouter
from app.api import auth, billing, generation_jobs, projects, quotas
from app.api.admin import content_reviews, jobs as admin_jobs, logs, organizations, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(billing.router)
api_router.include_router(quotas.router)
api_router.include_router(projects.router)
api_router.include_router(generation_jobs.router)
api_router.include_router(users.router)
api_router.include_router(organizations.router)
api_router.include_router(admin_jobs.router)
api_router.include_router(logs.router)
api_router.include_router(content_reviews.router)
