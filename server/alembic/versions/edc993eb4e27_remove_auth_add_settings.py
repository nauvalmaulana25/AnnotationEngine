"""remove auth, add settings

Revision ID: edc993eb4e27
Revises: d42a30045de9
Create Date: 2026-11-16 09:19:07.324353

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'edc993eb4e27'
down_revision: Union[str, None] = 'd42a30045de9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create settings table
    op.create_table(
        'settings',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('hf_api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('default_project_path', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # For SQLite, we need to recreate tables without user_id columns
    # since SQLite doesn't support dropping columns directly
    
    # Recreate projects table without user_id
    op.execute("""
        CREATE TABLE projects_new (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            base_path VARCHAR(500) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("INSERT INTO projects_new (id, name, description, base_path, created_at, updated_at) SELECT id, name, description, base_path, created_at, updated_at FROM projects")
    op.execute("DROP TABLE projects")
    op.execute("ALTER TABLE projects_new RENAME TO projects")
    
    # Recreate jobs table without user_id
    op.execute("""
        CREATE TABLE jobs_new (
            id INTEGER NOT NULL PRIMARY KEY,
            project_id INTEGER NOT NULL,
            job_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL,
            progress INTEGER NOT NULL,
            payload TEXT NOT NULL,
            result TEXT,
            error TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME,
            FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
        )
    """)
    op.execute("INSERT INTO jobs_new (id, project_id, job_type, status, progress, payload, result, error, created_at, started_at, completed_at) SELECT id, project_id, job_type, status, progress, payload, result, error, created_at, started_at, completed_at FROM jobs")
    op.execute("DROP TABLE jobs")
    op.execute("ALTER TABLE jobs_new RENAME TO jobs")
    
    # Recreate annotations table without created_by
    op.execute("""
        CREATE TABLE annotations_new (
            id INTEGER NOT NULL PRIMARY KEY,
            image_id INTEGER NOT NULL UNIQUE,
            data TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE
        )
    """)
    op.execute("INSERT INTO annotations_new (id, image_id, data, version, created_at, updated_at) SELECT id, image_id, data, version, created_at, updated_at FROM annotations")
    op.execute("DROP TABLE annotations")
    op.execute("ALTER TABLE annotations_new RENAME TO annotations")
    
    # Drop users table
    op.execute("DROP TABLE users")
    
    # Recreate indexes
    op.execute("CREATE INDEX ix_projects_id ON projects (id)")
    op.execute("CREATE INDEX ix_jobs_id ON jobs (id)")
    op.execute("CREATE INDEX ix_jobs_project_id_status ON jobs (project_id, status)")
    op.execute("CREATE INDEX ix_annotations_id ON annotations (id)")
    op.execute("CREATE INDEX ix_annotations_image_id ON annotations (image_id)")


def downgrade() -> None:
    # Recreate users table
    op.execute("""
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            hf_api_key_encrypted TEXT,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE UNIQUE INDEX ix_users_email ON users (email)")
    op.execute("CREATE INDEX ix_users_id ON users (id)")
    
    # Recreate projects with user_id
    op.execute("""
        CREATE TABLE projects_new (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            base_path VARCHAR(500) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    op.execute("INSERT INTO projects_new (id, user_id, name, description, base_path, created_at, updated_at) SELECT id, 1, name, description, base_path, created_at, updated_at FROM projects")
    op.execute("DROP TABLE projects")
    op.execute("ALTER TABLE projects_new RENAME TO projects")
    op.execute("CREATE INDEX ix_projects_user_id_name ON projects (user_id, name)")
    
    # Recreate jobs with user_id
    op.execute("""
        CREATE TABLE jobs_new (
            id INTEGER NOT NULL PRIMARY KEY,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            job_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL,
            progress INTEGER NOT NULL,
            payload TEXT NOT NULL,
            result TEXT,
            error TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME,
            FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    op.execute("INSERT INTO jobs_new (id, project_id, user_id, job_type, status, progress, payload, result, error, created_at, started_at, completed_at) SELECT id, project_id, 1, job_type, status, progress, payload, result, error, created_at, started_at, completed_at FROM jobs")
    op.execute("DROP TABLE jobs")
    op.execute("ALTER TABLE jobs_new RENAME TO jobs")
    op.execute("CREATE INDEX ix_jobs_user_id_created ON jobs (user_id, created_at)")
    
    # Recreate annotations with created_by
    op.execute("""
        CREATE TABLE annotations_new (
            id INTEGER NOT NULL PRIMARY KEY,
            image_id INTEGER NOT NULL UNIQUE,
            data TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_by INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
            FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE
        )
    """)
    op.execute("INSERT INTO annotations_new (id, image_id, data, version, created_by, created_at, updated_at) SELECT id, image_id, data, version, 1, created_at, updated_at FROM annotations")
    op.execute("DROP TABLE annotations")
    op.execute("ALTER TABLE annotations_new RENAME TO annotations")
    
    # Recreate users table
    op.execute("""
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            hf_api_key_encrypted TEXT,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE UNIQUE INDEX ix_users_email ON users (email)")
    op.execute("CREATE INDEX ix_users_id ON users (id)")
    
    # Drop settings table
    op.execute("DROP TABLE settings")