"""Configured persistence backends."""
from ..config import get_settings
from ..repository import ProjectRepository


def create_repository():
    settings = get_settings()
    if settings.database_backend == "sqlite":
        return ProjectRepository()
    from .postgres import PostgresRepository
    return PostgresRepository(settings.database_url)
