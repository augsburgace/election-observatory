"""Local schema migrations use the same configured database as the application."""
from alembic import context
from observatory.db import Base
from observatory.settings import get_settings
from sqlalchemy import create_engine

config = context.config
target_metadata = Base.metadata
url = config.get_main_option('sqlalchemy.url') or f'sqlite:///{get_settings().database_path}'
if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url, connect_args={"timeout": 60} if url.startswith("sqlite:") else {}).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
