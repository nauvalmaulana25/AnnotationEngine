"""
AnnotationEngine Desktop - Database Module
"""
import sqlite3
import json
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Generator
from datetime import datetime
from annotation_engine.config import DATABASE_PATH

logger = logging.getLogger(__name__)

SCHEMA = """
-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    base_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Images
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    file_size INTEGER,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    split TEXT DEFAULT 'train',
    has_annotation BOOLEAN DEFAULT 0,
    UNIQUE(project_id, relative_path)
);

-- Annotations (LabelMe JSON)
CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    data TEXT NOT NULL,  -- LabelMe JSON as text
    version INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(image_id)
);

-- Jobs (Background processing)
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,  -- 'grounding_dino', 'mobile_sam', 'dinov2_keypoint', 'export'
    status TEXT DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed'
    progress INTEGER DEFAULT 0,
    payload TEXT,  -- JSON
    result TEXT,   -- JSON
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Project label metadata (colors, visibility)
CREATE TABLE IF NOT EXISTS project_labels (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    visible INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (project_id, name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_images_project ON images(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

class Database:
    """SQLite database manager with connection pooling."""
    
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database with schema."""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()
        logger.info(f"Database initialized at {self.db_path}")
    
    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a write query."""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor
    
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch single row."""
        with self.get_connection() as conn:
            return conn.execute(query, params).fetchone()
    
    def fetch_all(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Fetch all rows."""
        with self.get_connection() as conn:
            return conn.execute(query, params).fetchall()

# Global database instance
_db_instance: Optional[Database] = None

def get_database() -> Database:
    """Get global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

# Project CRUD
def create_project(name: str, base_path: str, description: str = "") -> int:
    """Create a new project with folder structure."""
    import shutil
    from pathlib import Path
    
    db = get_database()
    now = datetime.now().isoformat()
    
    # Create project folder structure
    project_path = Path(base_path) / name
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "images").mkdir(exist_ok=True)
    (project_path / "labels").mkdir(exist_ok=True)
    (project_path / "exports").mkdir(exist_ok=True)
    
    cursor = db.execute(
        "INSERT INTO projects (name, description, base_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (name, description, str(project_path), now, now)
    )
    return cursor.lastrowid

def get_project(project_id: int) -> Optional[Dict]:
    """Get project by ID."""
    db = get_database()
    row = db.fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    return dict(row) if row else None

def get_all_projects() -> List[Dict]:
    """Get all projects ordered by updated_at desc."""
    db = get_database()
    rows = db.fetch_all("SELECT * FROM projects ORDER BY updated_at DESC")
    return [dict(row) for row in rows]

def update_project(project_id: int, **kwargs) -> bool:
    """Update project fields."""
    if not kwargs:
        return False
    db = get_database()
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    kwargs['updated_at'] = datetime.now().isoformat()
    kwargs['id'] = project_id
    cursor = db.execute(
        f"UPDATE projects SET {fields}, updated_at = ? WHERE id = ?",
        tuple(kwargs.values())
    )
    return cursor.rowcount > 0

def delete_project(project_id: int) -> bool:
    """Delete project and all related data (cascades), including folder on disk."""
    db = get_database()
    
    # Get project path before deleting from DB
    project = get_project(project_id)
    if project:
        project_path = Path(project['base_path'])
        if project_path.exists():
            import shutil
            shutil.rmtree(project_path)
    
    cursor = db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return cursor.rowcount > 0

def clean_database() -> bool:
    """
    Clean the entire database - delete all projects and reset AUTOINCREMENT counters.
    WARNING: This is destructive and irreversible.
    """
    db = get_database()
    
    # Get all project paths before deleting
    projects = get_all_projects()
    for project in projects:
        project_path = Path(project['base_path'])
        if project_path.exists():
            import shutil
            shutil.rmtree(project_path)
    
    with db.get_connection() as conn:
        # Delete all data from tables
        conn.execute("DELETE FROM annotations")
        conn.execute("DELETE FROM project_labels")
        conn.execute("DELETE FROM images")
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM projects")
        
        # Reset AUTOINCREMENT counters
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('projects', 'images', 'annotations', 'jobs')")
        
        conn.commit()
    
    # Clear recent projects
    set_setting('recent_projects', [])
    
    logger.warning("Database cleaned - all projects deleted, AUTOINCREMENT reset")
    return True

# Settings CRUD
def add_image(project_id: int, filename: str, relative_path: str, 
              width: int = None, height: int = None, file_size: int = None,
              split: str = "train") -> int:
    """Add image to project."""
    db = get_database()
    now = datetime.now().isoformat()
    cursor = db.execute(
        """INSERT INTO images (project_id, filename, relative_path, width, height, file_size, split, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (project_id, filename, relative_path, width, height, file_size, split, now)
    )
    return cursor.lastrowid

def get_image(image_id: int) -> Optional[Dict]:
    """Get image by ID."""
    db = get_database()
    row = db.fetch_one("SELECT * FROM images WHERE id = ?", (image_id,))
    return dict(row) if row else None

def get_project_images(project_id: int, split: str = None) -> List[Dict]:
    """Get all images for a project."""
    db = get_database()
    if split:
        rows = db.fetch_all("SELECT * FROM images WHERE project_id = ? AND split = ? ORDER BY imported_at", (project_id, split))
    else:
        rows = db.fetch_all("SELECT * FROM images WHERE project_id = ? ORDER BY imported_at", (project_id,))
    return [dict(row) for row in rows]

def update_image(image_id: int, **kwargs) -> bool:
    """Update image fields."""
    if not kwargs:
        return False
    db = get_database()
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    kwargs['id'] = image_id
    cursor = db.execute(
        f"UPDATE images SET {fields} WHERE id = ?",
        tuple(kwargs.values())
    )
    return cursor.rowcount > 0

def delete_image(image_id: int) -> bool:
    """Delete image and its annotation."""
    db = get_database()
    cursor = db.execute("DELETE FROM images WHERE id = ?", (image_id,))
    return cursor.rowcount > 0

# Annotation CRUD
def save_annotation(image_id: int, data: Dict, version: int = 1) -> int:
    """Save or update annotation for image."""
    db = get_database()
    now = datetime.now().isoformat()
    data_json = json.dumps(data)
    
    # Check if exists
    existing = db.fetch_one("SELECT id FROM annotations WHERE image_id = ?", (image_id,))
    
    if existing:
        db.execute(
            "UPDATE annotations SET data = ?, version = ?, updated_at = ? WHERE image_id = ?",
            (data_json, version, now, image_id)
        )
        return existing['id']
    else:
        cursor = db.execute(
            "INSERT INTO annotations (image_id, data, version, updated_at) VALUES (?, ?, ?, ?)",
            (image_id, data_json, version, now)
        )
        return cursor.lastrowid

def get_annotation(image_id: int) -> Optional[Dict]:
    """Get annotation for image."""
    db = get_database()
    row = db.fetch_one("SELECT * FROM annotations WHERE image_id = ?", (image_id,))
    if row:
        data = dict(row)
        data['data'] = json.loads(data['data'])
        return data
    return None

def delete_annotation(image_id: int) -> bool:
    """Delete annotation for image."""
    db = get_database()
    cursor = db.execute("DELETE FROM annotations WHERE image_id = ?", (image_id,))
    return cursor.rowcount > 0


def get_project_annotations(project_id: int) -> Dict[int, List[Dict]]:
    """Return every saved shape, keyed by image id, for a project.

    Loads all annotations in one query (rather than one per image) so the image
    grid can render overlays without an N+1 fetch on the UI thread.
    """
    db = get_database()
    rows = db.fetch_all(
        """SELECT a.image_id, a.data FROM annotations a
           JOIN images i ON i.id = a.image_id
           WHERE i.project_id = ?""",
        (project_id,)
    )

    result: Dict[int, List[Dict]] = {}
    for row in rows:
        try:
            data = json.loads(row['data'])
        except (TypeError, json.JSONDecodeError):
            continue
        result[int(row['image_id'])] = list(data.get('shapes') or [])
    return result

# Project label metadata
def get_project_labels(project_id: int) -> List[Dict]:
    """Return persisted label metadata for a project."""
    db = get_database()
    rows = db.fetch_all(
        "SELECT name, color, visible FROM project_labels "
        "WHERE project_id = ? ORDER BY rowid",
        (project_id,)
    )
    return [
        {
            'name': row['name'],
            'color': row['color'],
            'visible': bool(row['visible']),
        }
        for row in rows
    ]

def save_project_labels(project_id: int, labels: List[Dict]) -> None:
    """Replace the persisted label metadata for a project."""
    db = get_database()
    with db.get_connection() as conn:
        conn.execute(
            "DELETE FROM project_labels WHERE project_id = ?", (project_id,)
        )
        conn.executemany(
            "INSERT INTO project_labels (project_id, name, color, visible) "
            "VALUES (?, ?, ?, ?)",
            [
                (
                    project_id,
                    label['name'],
                    label.get('color') or '',
                    1 if label.get('visible', True) else 0,
                )
                for label in labels
                if label.get('name')
            ]
        )
        conn.commit()

def label_in_use(
    project_id: int, label: str, exclude_image_id: Optional[int] = None
) -> bool:
    """Return whether any saved annotation of the project uses the label.

    ``exclude_image_id`` skips one image, used for the canvas that is currently
    open: while it has unsaved edits its saved row is stale and must not keep a
    label alive.
    """
    if not label:
        return False

    db = get_database()
    base_sql = """
        SELECT a.data
        FROM annotations a
        JOIN images i ON i.id = a.image_id
        WHERE i.project_id = ?
    """
    base_params: List[Any] = [project_id]
    if exclude_image_id is not None:
        base_sql += " AND a.image_id != ?"
        base_params.append(exclude_image_id)

    try:
        row = db.fetch_one(
            base_sql
            + """
              AND EXISTS (
                  SELECT 1 FROM json_each(a.data, '$.shapes') AS shape
                  WHERE json_extract(shape.value, '$.label') = ?
              )
            """,
            tuple(base_params) + (label,)
        )
        return bool(row)
    except sqlite3.OperationalError:
        # SQLite without the JSON1 extension: inspect the rows in Python.
        for row in db.fetch_all(base_sql, tuple(base_params)):
            try:
                data = json.loads(row['data'])
            except (TypeError, json.JSONDecodeError):
                continue
            if any(
                (shape or {}).get('label') == label
                for shape in data.get('shapes') or []
            ):
                return True
        return False


def rename_label_in_project(project_id: int, old: str, new: str) -> int:
    """Rename a label inside every saved annotation of a project."""
    if not old or not new or old == new:
        return 0

    db = get_database()
    rows = db.fetch_all(
        """SELECT a.id, a.image_id, a.data FROM annotations a
           JOIN images i ON i.id = a.image_id
           WHERE i.project_id = ?""",
        (project_id,)
    )

    updated = 0
    with db.get_connection() as conn:
        for row in rows:
            try:
                data = json.loads(row['data'])
            except (TypeError, json.JSONDecodeError):
                continue

            shapes = data.get('shapes') or []
            changed = False
            for shape in shapes:
                if shape.get('label') == old:
                    shape['label'] = new
                    changed = True
            if not changed:
                continue

            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE annotations SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(data), now, row['id'])
            )
            updated += 1
        conn.commit()

    return updated

# Job CRUD
def create_job(project_id: int, job_type: str, payload: Dict) -> str:
    """Create a new job."""
    import uuid
    db = get_database()
    job_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    payload_json = json.dumps(payload)
    db.execute(
        """INSERT INTO jobs (id, project_id, job_type, status, payload, created_at)
           VALUES (?, ?, ?, 'pending', ?, ?)""",
        (job_id, project_id, job_type, payload_json, now)
    )
    return job_id

def get_job(job_id: str) -> Optional[Dict]:
    """Get job by ID."""
    db = get_database()
    row = db.fetch_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if row:
        data = dict(row)
        data['payload'] = json.loads(data['payload'])
        if data['result']:
            data['result'] = json.loads(data['result'])
        return data
    return None

def get_project_jobs(project_id: int, status: str = None) -> List[Dict]:
    """Get jobs for project."""
    db = get_database()
    if status:
        rows = db.fetch_all("SELECT * FROM jobs WHERE project_id = ? AND status = ? ORDER BY created_at DESC", (project_id, status))
    else:
        rows = db.fetch_all("SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    result = []
    for row in rows:
        data = dict(row)
        data['payload'] = json.loads(data['payload'])
        if data['result']:
            data['result'] = json.loads(data['result'])
        result.append(data)
    return result

def update_job_status(job_id: str, status: str, progress: int = None, 
                      result: Dict = None, error: str = None) -> bool:
    """Update job status."""
    db = get_database()
    now = datetime.now().isoformat()
    
    if status == 'running':
        db.execute(
            "UPDATE jobs SET status = ?, progress = ?, started_at = ? WHERE id = ?",
            (status, progress or 0, now, job_id)
        )
    elif status == 'completed':
        result_json = json.dumps(result) if result else None
        db.execute(
            "UPDATE jobs SET status = ?, progress = 100, result = ?, completed_at = ? WHERE id = ?",
            (status, result_json, now, job_id)
        )
    elif status == 'failed':
        db.execute(
            "UPDATE jobs SET status = ?, error = ?, completed_at = ? WHERE id = ?",
            (status, error, now, job_id)
        )
    else:
        db.execute(
            "UPDATE jobs SET status = ?, progress = ? WHERE id = ?",
            (status, progress or 0, job_id)
        )
    return True

# Settings CRUD
def get_setting(key: str, default: Any = None) -> Any:
    """Get setting value."""
    db = get_database()
    row = db.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
    if row:
        try:
            return json.loads(row['value'])
        except json.JSONDecodeError:
            return row['value']
    return default

def set_setting(key: str, value: Any) -> bool:
    """Set setting value."""
    db = get_database()
    value_json = json.dumps(value)
    cursor = db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value_json)
    )
    return cursor.rowcount > 0

# Recent projects
def add_recent_project(project_id: int) -> None:
    """Add project to recent list."""
    from annotation_engine.config import DEFAULT_SETTINGS
    recent = get_setting('recent_projects', [])
    if project_id in recent:
        recent.remove(project_id)
    recent.insert(0, project_id)
    recent = recent[:DEFAULT_SETTINGS['max_recent_projects']]
    set_setting('recent_projects', recent)

def get_recent_projects() -> List[int]:
    """Get recent project IDs."""
    return get_setting('recent_projects', [])