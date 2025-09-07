import aiosqlite
import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum


class UserRole(Enum):
    """User roles with hierarchy levels"""

    USER = ("user", 1)
    SUPERADMIN = ("superadmin", 10)

    def __init__(self, role_name: str, level: int):
        self.role_name = role_name
        self.level = level

    @classmethod
    def from_string(cls, role_str: str) -> "UserRole":
        for role in cls:
            if role.role_name == role_str:
                return role
        raise ValueError(f"Invalid role: {role_str}")

    def can_manage(self, other_role: "UserRole") -> bool:
        """Check if this role can manage another role"""
        return self.level > other_role.level


@dataclass
class User:
    """User data model matching Telegram user structure with bot-specific fields"""

    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    is_bot: bool = False
    is_premium: Optional[bool] = None
    added_to_attachment_menu: Optional[bool] = None

    # Bot-specific fields
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    is_active: bool = False
    user_state: Optional[str] = None
    user_role: str = "user"
    settings: Optional[Dict[str, Any]] = field(default_factory=dict)

    # Chat session
    current_session_id: str | None = None

    # Analytics fields
    total_messages: int = 0
    total_commands: int = 0
    first_interaction: Optional[datetime] = None
    last_interaction: Optional[datetime] = None


@dataclass
class ChatSession:
    session_id: str
    user_id: int
    name: str
    created_at: datetime
    last_activity: datetime | None = None
    ended_at: datetime | None = None
    deleted_at: datetime | None = None
    message_count: int = 0


@dataclass
class UserActivity:
    """User activity tracking model"""

    id: Optional[int] = None
    user_id: int = 0
    activity_type: str = ""  # 'message', 'command', 'callback', 'inline'
    activity_data: Optional[str] = None  # JSON data
    timestamp: Optional[datetime] = None
    session_id: Optional[str] = None


class DatabaseError(Exception):
    """Custom exception for database operations"""

    pass


class MigrationManager:
    """Database migration management system"""

    CURRENT_VERSION = 2

    @staticmethod
    async def get_db_version(db_path: str) -> int:
        """Get current database version"""
        try:
            async with aiosqlite.connect(db_path) as conn:
                async with conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                ) as cursor:
                    if not await cursor.fetchone():
                        return 0

                async with conn.execute(
                    "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
        except Exception:
            return 0

    @staticmethod
    async def create_migrations_table(conn: aiosqlite.Connection):
        """Create migrations tracking table"""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)

    @staticmethod
    async def apply_migration_v1(conn: aiosqlite.Connection):
        """Apply version 1 migration - initial schema"""
        # Users table with analytics fields
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT,
                is_bot BOOLEAN DEFAULT FALSE,
                is_premium BOOLEAN,
                added_to_attachment_menu BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                user_state TEXT,
                user_role TEXT DEFAULT 'user',
                settings TEXT DEFAULT '{}',
                total_messages INTEGER DEFAULT 0,
                total_commands INTEGER DEFAULT 0,
                first_interaction TIMESTAMP,
                last_interaction TIMESTAMP,
                UNIQUE(user_id)
            )
        """)

        # User activities table for detailed analytics
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                activity_data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        """)

        # Create indexes for performance
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_username ON users(username)")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_role ON users(user_role)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_is_active ON users(is_active)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_created_at ON users(created_at)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_last_seen ON users(last_seen)"
        )

        # Activity indexes
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_user_id ON user_activities(user_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_type ON user_activities(activity_type)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON user_activities(timestamp)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_session ON user_activities(session_id)"
        )

        # Record migration
        await conn.execute(
            "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
            (1, "Initial schema with users and analytics"),
        )

    @staticmethod
    async def apply_migration_v2(conn: aiosqlite.Connection):
        """Apply version 2 migration - add session table"""
        _chat_sessions_table_sql = """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP,
                    deleted_at TIMESTAMP,                 -- soft-delete marker (NULL = active)
                    message_count INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                );
                """

        _chat_sessions_indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_created_at ON chat_sessions(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_activity ON chat_sessions(last_activity);",
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_deleted_at ON chat_sessions(deleted_at);",
        ]

        # Add current_session_id to users table safely (run inside a migration - catch/ignore error if column exists)
        _add_current_session_column_sql = (
            "ALTER TABLE users ADD COLUMN current_session_id TEXT;"
        )

        await conn.execute(_chat_sessions_table_sql)
        for idx_sql in _chat_sessions_indexes_sql:
            await conn.execute(idx_sql)
        try:
            await conn.execute(_add_current_session_column_sql)
        except aiosqlite.Error:
            # Column already exists on a previously migrated DB — ignore
            pass

        # Then record migration as normal:
        await conn.execute(
            "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
            (2, "Add chat_sessions"),
        )


class AsyncUserDatabase:
    """Async SQLite database manager for aiogram bot users with analytics"""

    def __init__(self, db_path: str = "bot_users.db"):
        """Initialize async database manager"""
        self.db_path = Path(db_path)
        self.logger = logging.getLogger(__name__)

        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """Initialize database with migrations"""
        try:
            current_version = await MigrationManager.get_db_version(str(self.db_path))
            target_version = MigrationManager.CURRENT_VERSION

            if current_version < target_version:
                self.logger.info(
                    f"Migrating database from v{current_version} to v{target_version}"
                )
                await self._run_migrations(current_version, target_version)

            self.logger.info("Database initialized successfully")
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise DatabaseError(f"Database initialization failed: {e}")

    async def _run_migrations(self, current_version: int, target_version: int):
        """Run database migrations"""
        async with aiosqlite.connect(self.db_path) as conn:
            await MigrationManager.create_migrations_table(conn)

            if current_version < 1 <= target_version:
                await MigrationManager.apply_migration_v1(conn)
            if current_version < 2 <= target_version:
                await MigrationManager.apply_migration_v2(conn)

            await conn.commit()

    @asynccontextmanager
    async def get_connection(self):
        """Async context manager for database connections with proper locking"""
        conn = None
        try:
            conn = await aiosqlite.connect(self.db_path, timeout=10.0)
            conn.row_factory = aiosqlite.Row
            # Enable WAL mode for better concurrency
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA temp_store=memory")
            await conn.execute("PRAGMA mmap_size=268435456")  # 256MB
            yield conn
        except aiosqlite.Error as e:
            if conn:
                try:
                    await conn.rollback()
                except Exception:
                    pass
            self.logger.error(f"Database error: {e}")
            raise DatabaseError(f"Database operation failed: {e}")
        finally:
            if conn:
                try:
                    await conn.close()
                except Exception:
                    pass

    # User Management Methods

    async def add_user(self, user: User) -> bool:
        """Add a new user to the database"""
        try:
            async with self.get_connection() as conn:
                now = datetime.now()
                user.created_at = now
                user.updated_at = now
                user.first_interaction = now
                user.last_interaction = now

                user_dict = asdict(user)
                # Convert datetime objects and handle JSON fields
                for key, value in user_dict.items():
                    if isinstance(value, datetime):
                        user_dict[key] = value.isoformat()
                    elif key == "settings" and isinstance(value, dict):
                        user_dict[key] = json.dumps(value)

                placeholders = ", ".join(["?" for _ in user_dict])
                columns = ", ".join(user_dict.keys())

                await conn.execute(
                    f"INSERT OR IGNORE INTO users ({columns}) VALUES ({placeholders})",
                    list(user_dict.values()),
                )

                rows_affected = conn.total_changes
                await conn.commit()

                if rows_affected > 0:
                    self.logger.info(f"Added new user: {user.user_id}")
                    return True
                return False

        except Exception as e:
            self.logger.error(f"Error adding user {user.user_id}: {e}")
            raise DatabaseError(f"Failed to add user: {e}")

    async def get_user(self, user_id: int) -> Optional[User]:
        """Retrieve a user by user_id"""
        try:
            async with self.get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()

                    if row:
                        user_dict = dict(row)
                        return self._row_to_user(user_dict)
                    return None

        except Exception as e:
            self.logger.error(f"Error retrieving user {user_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user: {e}")

    async def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user information"""
        if not kwargs:
            return False

        try:
            async with self.get_connection() as conn:
                # Start transaction
                await conn.execute("BEGIN IMMEDIATE")

                try:
                    # Handle special fields
                    if "settings" in kwargs and isinstance(kwargs["settings"], dict):
                        kwargs["settings"] = json.dumps(kwargs["settings"])

                    # Add updated_at timestamp
                    kwargs["updated_at"] = datetime.now().isoformat()

                    set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
                    values = list(kwargs.values()) + [user_id]

                    cursor = await conn.execute(
                        f"UPDATE users SET {set_clause} WHERE user_id = ?", values
                    )

                    rows_affected = cursor.rowcount
                    await conn.commit()

                    if rows_affected > 0:
                        self.logger.info(f"Updated user: {user_id}")
                        return True
                    return False

                except Exception as e:
                    await conn.rollback()
                    raise e

        except Exception as e:
            self.logger.error(f"Error updating user {user_id}: {e}")
            raise DatabaseError(f"Failed to update user: {e}")

    # Role Management with Superadmin Support

    async def set_user_role(self, user_id: int, role: Union[str, UserRole]) -> bool:
        """Set user role with validation"""
        try:
            if isinstance(role, str):
                role_name = role
            else:
                role_name = role.role_name

            return await self.update_user(user_id, user_role=role_name)
        except ValueError as e:
            raise DatabaseError(f"Invalid role: {e}")

    async def is_superadmin(self, user_id: int) -> bool:
        """Check if user is a superadmin"""
        user = await self.get_user(user_id)
        return user.user_role == "superadmin" if user else False

    async def is_admin_or_higher(self, user_id: int) -> bool:
        """Check if user is admin or superadmin"""
        user = await self.get_user(user_id)
        if not user:
            return False
        try:
            role = UserRole.from_string(user.user_role)
            return role.level > UserRole.USER.level
        except ValueError:
            return False

    async def can_manage_user(self, manager_id: int, target_id: int) -> bool:
        """Check if manager can manage target user"""
        manager = await self.get_user(manager_id)
        target = await self.get_user(target_id)

        if not manager or not target:
            return False

        try:
            manager_role = UserRole.from_string(manager.user_role)
            target_role = UserRole.from_string(target.user_role)
            return manager_role.can_manage(target_role)
        except ValueError:
            return False

    async def get_all_users(self, active_only: bool = False) -> list[User]:
        """Get all users, optionally filtering by active status, sorted by creation date, newest first"""
        try:
            async with self.get_connection() as conn:
                query = "SELECT * FROM users"
                params = []

                if active_only:
                    query += " WHERE is_active = ?"
                    params.append(True)

                query += " ORDER BY created_at DESC"

                async with conn.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [self._row_to_user(dict(row)) for row in rows]

        except Exception as e:
            self.logger.error(f"Error retrieving all users: {e}")
            raise DatabaseError(f"Failed to retrieve users: {e}")

    async def get_users_by_role(self, role: Union[str, UserRole]) -> List[User]:
        """Get users by their role"""
        role_name = role.role_name if isinstance(role, UserRole) else role

        try:
            async with self.get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM users WHERE user_role = ? AND is_active = ? ORDER BY created_at DESC",
                    (role_name, True),
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [self._row_to_user(dict(row)) for row in rows]

        except Exception as e:
            self.logger.error(f"Error retrieving users by role {role_name}: {e}")
            raise DatabaseError(f"Failed to retrieve users by role: {e}")

    # Analytics Methods

    async def log_activity(
        self,
        user_id: int,
        activity_type: str,
        activity_data: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Log user activity for analytics"""
        try:
            async with self.get_connection() as conn:
                # Start transaction
                await conn.execute("BEGIN IMMEDIATE")

                try:
                    data_json = json.dumps(activity_data) if activity_data else None

                    await conn.execute(
                        """
                        INSERT INTO user_activities
                        (user_id, activity_type, activity_data, session_id)
                        VALUES (?, ?, ?, ?)
                    """,
                        (user_id, activity_type, data_json, session_id),
                    )

                    # Update user interaction timestamp and counters in single query
                    now = datetime.now().isoformat()

                    if activity_type == "message":
                        await conn.execute(
                            """
                            UPDATE users SET
                                last_interaction = ?,
                                last_seen = ?,
                                total_messages = total_messages + 1,
                                updated_at = ?
                            WHERE user_id = ?
                        """,
                            (now, now, now, user_id),
                        )
                    elif activity_type == "command":
                        await conn.execute(
                            """
                            UPDATE users SET
                                last_interaction = ?,
                                last_seen = ?,
                                total_commands = total_commands + 1,
                                updated_at = ?
                            WHERE user_id = ?
                        """,
                            (now, now, now, user_id),
                        )
                    else:
                        await conn.execute(
                            """
                            UPDATE users SET
                                last_interaction = ?,
                                last_seen = ?,
                                updated_at = ?
                            WHERE user_id = ?
                        """,
                            (now, now, now, user_id),
                        )

                    await conn.commit()
                    return True

                except Exception as e:
                    await conn.rollback()
                    raise e

        except Exception as e:
            self.logger.error(f"Error logging activity for user {user_id}: {e}")
            return False

    async def get_user_activity_stats(
        self, user_id: int, days: int = 30
    ) -> Dict[str, Any]:
        """Get user activity statistics"""
        try:
            async with self.get_connection() as conn:
                since_date = datetime.now() - timedelta(days=days)

                # Activity breakdown
                async with conn.execute(
                    """
                    SELECT activity_type, COUNT(*) as count
                    FROM user_activities
                    WHERE user_id = ? AND timestamp >= ?
                    GROUP BY activity_type
                """,
                    (user_id, since_date.isoformat()),
                ) as cursor:
                    activity_breakdown = {
                        row[0]: row[1] for row in await cursor.fetchall()
                    }

                # Daily activity
                async with conn.execute(
                    """
                    SELECT DATE(timestamp) as date, COUNT(*) as count
                    FROM user_activities
                    WHERE user_id = ? AND timestamp >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date DESC
                """,
                    (user_id, since_date.isoformat()),
                ) as cursor:
                    daily_activity = {row[0]: row[1] for row in await cursor.fetchall()}

                # Get user totals
                user = await self.get_user(user_id)

                return {
                    "user_id": user_id,
                    "period_days": days,
                    "activity_breakdown": activity_breakdown,
                    "daily_activity": daily_activity,
                    "total_messages": user.total_messages if user else 0,
                    "total_commands": user.total_commands if user else 0,
                    "first_interaction": user.first_interaction.isoformat()
                    if user and user.first_interaction
                    else None,
                    "last_interaction": user.last_interaction.isoformat()
                    if user and user.last_interaction
                    else None,
                }

        except Exception as e:
            self.logger.error(f"Error getting activity stats for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get activity stats: {e}")

    async def get_bot_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive bot analytics"""
        try:
            async with self.get_connection() as conn:
                since_date = datetime.now() - timedelta(days=days)

                # Total users
                async with conn.execute(
                    "SELECT COUNT(*) FROM users WHERE is_active = 1"
                ) as cursor:
                    total_active_users = (await cursor.fetchone())[0]

                # New users in period
                async with conn.execute(
                    "SELECT COUNT(*) FROM users WHERE created_at >= ?",
                    (since_date.isoformat(),),
                ) as cursor:
                    new_users = (await cursor.fetchone())[0]

                # Active users in period
                async with conn.execute(
                    """
                    SELECT COUNT(DISTINCT user_id) FROM user_activities
                    WHERE timestamp >= ?
                """,
                    (since_date.isoformat(),),
                ) as cursor:
                    active_users_period = (await cursor.fetchone())[0]

                # Most active users
                async with conn.execute(
                    """
                    SELECT u.user_id, u.username, u.first_name, COUNT(a.id) as activity_count
                    FROM users u
                    LEFT JOIN user_activities a ON u.user_id = a.user_id
                    WHERE a.timestamp >= ? OR a.timestamp IS NULL
                    GROUP BY u.user_id
                    ORDER BY activity_count DESC
                    LIMIT 10
                """,
                    (since_date.isoformat(),),
                ) as cursor:
                    top_users = []
                    for row in await cursor.fetchall():
                        top_users.append(
                            {
                                "user_id": row[0],
                                "username": row[1],
                                "name": row[2],
                                "activity_count": row[3],
                            }
                        )

                # Activity by type
                async with conn.execute(
                    """
                    SELECT activity_type, COUNT(*) as count
                    FROM user_activities
                    WHERE timestamp >= ?
                    GROUP BY activity_type
                    ORDER BY count DESC
                """,
                    (since_date.isoformat(),),
                ) as cursor:
                    activity_breakdown = {
                        row[0]: row[1] for row in await cursor.fetchall()
                    }

                # Role distribution
                async with conn.execute("""
                    SELECT user_role, COUNT(*) as count
                    FROM users
                    WHERE is_active = 1
                    GROUP BY user_role
                """) as cursor:
                    role_distribution = {
                        row[0]: row[1] for row in await cursor.fetchall()
                    }

                return {
                    "period_days": days,
                    "total_active_users": total_active_users,
                    "new_users_period": new_users,
                    "active_users_period": active_users_period,
                    "top_users": top_users,
                    "activity_breakdown": activity_breakdown,
                    "role_distribution": role_distribution,
                    "generated_at": datetime.now().isoformat(),
                }

        except Exception as e:
            self.logger.error(f"Error getting bot analytics: {e}")
            raise DatabaseError(f"Failed to get bot analytics: {e}")

    async def get_command_usage_stats(self, days: int = 30) -> Dict[str, int]:
        """Get command usage statistics"""
        try:
            async with self.get_connection() as conn:
                since_date = datetime.now() - timedelta(days=days)

                async with conn.execute(
                    """
                    SELECT activity_data, COUNT(*) as count
                    FROM user_activities
                    WHERE activity_type = 'command'
                    AND timestamp >= ?
                    AND activity_data IS NOT NULL
                    GROUP BY activity_data
                    ORDER BY count DESC
                """,
                    (since_date.isoformat(),),
                ) as cursor:
                    command_stats = {}
                    for row in await cursor.fetchall():
                        try:
                            data = json.loads(row[0])
                            command = data.get("command", "unknown")
                            command_stats[command] = row[1]
                        except json.JSONDecodeError:
                            continue

                    return command_stats

        except Exception as e:
            self.logger.error(f"Error getting command stats: {e}")
            return {}

    # Utility Methods

    @staticmethod
    def _row_to_user(row_dict: Dict[str, Any]) -> User:
        """Convert database row to User object"""
        # Handle datetime fields
        for field_name in [
            "created_at",
            "updated_at",
            "last_seen",
            "first_interaction",
            "last_interaction",
        ]:
            if row_dict.get(field_name):
                try:
                    row_dict[field_name] = datetime.fromisoformat(row_dict[field_name])
                except (ValueError, TypeError):
                    row_dict[field_name] = None

        # Handle JSON fields
        if row_dict.get("settings"):
            try:
                row_dict["settings"] = json.loads(row_dict["settings"])
            except json.JSONDecodeError:
                row_dict["settings"] = {}

        return User(**row_dict)

    @staticmethod
    def _row_to_chat_session(row_dict: dict[str, Any]) -> ChatSession:
        """
        Convert DB row dict to ChatSession dataclass. Safe-parse timestamps and JSON.
        """
        # Parse datetimes
        for f in ("created_at", "last_activity", "ended_at", "deleted_at"):
            if row_dict.get(f):
                try:
                    row_dict[f] = datetime.fromisoformat(row_dict[f])
                except (ValueError, TypeError):
                    row_dict[f] = None
            else:
                row_dict[f] = None

        return ChatSession(
            session_id=row_dict["session_id"],
            user_id=int(row_dict["user_id"]),
            name=row_dict.get("name") or "",
            created_at=row_dict["created_at"] or datetime.now(),
            last_activity=row_dict.get("last_activity"),
            ended_at=row_dict.get("ended_at"),
            deleted_at=row_dict.get("deleted_at"),
            message_count=int(row_dict.get("message_count") or 0),
        )

    async def get_user_count(self, active_only: bool = True) -> int:
        """Get total number of users"""
        try:
            async with self.get_connection() as conn:
                query = "SELECT COUNT(*) FROM users"
                params = []

                if active_only:
                    query += " WHERE is_active = ?"
                    params.append(True)

                async with conn.execute(query, params) as cursor:
                    result = await cursor.fetchone()
                    return result[0]

        except Exception as e:
            self.logger.error(f"Error counting users: {e}")
            raise DatabaseError(f"Failed to count users: {e}")

    async def cleanup_old_activities(self, days: int = 90) -> int:
        """Clean up old activity records"""
        try:
            async with self.get_connection() as conn:
                cutoff_date = datetime.now() - timedelta(days=days)

                cursor = await conn.execute(
                    """
                    DELETE FROM user_activities
                    WHERE timestamp < ?
                """,
                    (cutoff_date.isoformat(),),
                )

                deleted_count = cursor.rowcount
                await conn.commit()

                self.logger.info(f"Cleaned up {deleted_count} old activity records")
                return deleted_count

        except Exception as e:
            self.logger.error(f"Error cleaning up activities: {e}")
            return 0

    async def activate_user(self, target_user_id: int) -> bool:
        """
        Activate a user by setting is_active to True

        Args:
            target_user_id: The ID of the user to activate

        Returns:
            bool: True if the user was activated, False if the user was already active
                 or didn't exist

        Raises:
            DatabaseError: If there's an error during the database operation
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")

                try:
                    cursor = await conn.execute(
                        """
                        UPDATE users
                        SET is_active = 1,
                            updated_at = ?
                        WHERE user_id = ? AND is_active = 0
                        """,
                        (datetime.now().isoformat(), target_user_id),
                    )

                    rows_affected = cursor.rowcount
                    await conn.commit()

                    if rows_affected > 0:
                        self.logger.info(f"Activated user: {target_user_id}")
                        return True
                    return False

                except Exception as e:
                    await conn.rollback()
                    raise e

        except Exception as e:
            self.logger.error(f"Error activating user {target_user_id}: {e}")
            raise DatabaseError(f"Failed to activate user: {e}")

    async def deactivate_user(self, target_user_id: int) -> bool:
        """
        Deactivate a user by setting is_active to False

        Args:
            target_user_id: The ID of the user to deactivate

        Returns:
            bool: True if the user was deactivated, False if the user was already inactive
                 or didn't exist

        Raises:
            DatabaseError: If there's an error during the database operation
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")

                try:
                    cursor = await conn.execute(
                        """
                        UPDATE users
                        SET is_active = 0,
                            updated_at = ?
                        WHERE user_id = ? AND is_active = 1
                        """,
                        (datetime.now().isoformat(), target_user_id),
                    )

                    rows_affected = cursor.rowcount
                    await conn.commit()

                    if rows_affected > 0:
                        self.logger.info(f"Deactivated user: {target_user_id}")
                        return True
                    return False

                except Exception as e:
                    await conn.rollback()
                    raise e

        except Exception as e:
            self.logger.error(f"Error deactivating user {target_user_id}: {e}")
            raise DatabaseError(f"Failed to deactivate user: {e}")

    # Session methods
    async def create_chat_session(
        self, user_id: int, session_id: str, name: str | None = None
    ) -> str:
        """
        Create a new chat session owned by user_id and set it as user's current_session_id.
        name defaults to human-readable EU date/time: "DD.MM.YYYY HH:MM"
        Returns the new session_id.
        """
        if not name:
            name = datetime.now().strftime("%d.%m.%Y %H:%M")
        now_iso = datetime.now().isoformat()

        try:
            async with self.get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO chat_sessions
                    (session_id, user_id, name, created_at, last_activity)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, user_id, name, now_iso, now_iso),
                )

                # Set session as current for the user
                await conn.execute(
                    "UPDATE users SET current_session_id = ?, updated_at = ? WHERE user_id = ?",
                    (session_id, now_iso, user_id),
                )

                await conn.commit()
                self.logger.info(
                    f"Created chat session {session_id} for user {user_id}"
                )
                return session_id

        except Exception as e:
            self.logger.error(f"Error creating chat session for user {user_id}: {e}")
            raise DatabaseError(f"Failed to create chat session: {e}")

    async def list_chat_sessions(
        self, user_id: int, include_deleted: bool = False
    ) -> list[ChatSession]:
        """List sessions owned by a user."""
        try:
            async with self.get_connection() as conn:
                if include_deleted:
                    query = "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY created_at DESC"
                    params = (user_id,)
                else:
                    query = "SELECT * FROM chat_sessions WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC"
                    params = (user_id,)

                async with conn.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [self._row_to_chat_session(dict(row)) for row in rows]

        except Exception as e:
            self.logger.error(f"Error listing chat sessions for user {user_id}: {e}")
            raise DatabaseError(f"Failed to list chat sessions: {e}")

    async def soft_delete_chat_session(self, user_id: int, session_id: str) -> bool:
        """
        Soft-delete a chat session by setting deleted_at = now().
        Only the owner (user_id) can soft-delete their session.
        If the deleted session was the user's current_session_id it will be cleared.
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                try:
                    now_iso = datetime.now().isoformat()
                    cursor = await conn.execute(
                        "UPDATE chat_sessions SET deleted_at = ? WHERE session_id = ? AND user_id = ? AND deleted_at IS NULL",
                        (now_iso, session_id, user_id),
                    )
                    rows_affected = cursor.rowcount

                    # Clear current_session_id if needed
                    async with conn.execute(
                        "SELECT current_session_id FROM users WHERE user_id = ?",
                        (user_id,),
                    ) as cur:
                        row = await cur.fetchone()
                        if row and row[0] == session_id:
                            await conn.execute(
                                "UPDATE users SET current_session_id = NULL, updated_at = ? WHERE user_id = ?",
                                (now_iso, user_id),
                            )

                    await conn.commit()
                    if rows_affected > 0:
                        self.logger.info(
                            f"Soft-deleted chat session {session_id} for user {user_id}"
                        )
                        return True
                    return False

                except Exception:
                    await conn.rollback()
                    raise

        except Exception as e:
            self.logger.error(
                f"Error soft-deleting chat session {session_id} for user {user_id}: {e}"
            )
            return False

    async def restore_chat_session(self, user_id: int, session_id: str) -> bool:
        """
        Restore a previously soft-deleted chat session (set deleted_at = NULL).
        Only owner may restore.
        """
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute(
                    "UPDATE chat_sessions SET deleted_at = NULL WHERE session_id = ? AND user_id = ? AND deleted_at IS NOT NULL",
                    (session_id, user_id),
                )
                await conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(
                f"Error restoring chat session {session_id} for user {user_id}: {e}"
            )
            return False

    async def get_current_chat_session(self, user_id: int) -> ChatSession | None:
        """
        Return the current chat session for a user in a single query, only if it's not soft-deleted.
        """
        try:
            async with self.get_connection() as conn:
                async with conn.execute(
                    """
                        SELECT cs.*
                        FROM users u
                        JOIN chat_sessions cs ON u.current_session_id = cs.session_id
                        WHERE u.user_id = ? AND cs.deleted_at IS NULL
                        LIMIT 1
                        """,
                    (user_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    return self._row_to_chat_session(dict(row))

        except Exception as e:
            self.logger.error(f"Error fetching current session for user {user_id}: {e}")
            return None

    async def update_chat_session_activity(self, session_id: str, message_count: int):
        """Update chat session last activity and message count"""
        try:
            async with self.get_connection() as conn:
                await conn.execute(
                    "UPDATE chat_sessions SET last_activity = ?, message_count = ? WHERE session_id = ?",
                    (datetime.now().isoformat(), message_count, session_id),
                )
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Error updating chat session activity: {e}")


# Helper functions for aiogram integration
def create_user_from_telegram(telegram_user) -> User:
    """Create User object from aiogram's Telegram User object"""
    return User(
        user_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
        language_code=telegram_user.language_code,
        is_bot=telegram_user.is_bot,
        is_premium=getattr(telegram_user, "is_premium", None),
        added_to_attachment_menu=getattr(
            telegram_user, "added_to_attachment_menu", None
        ),
    )


# Example usage with analytics
async def example_usage():
    """Example of how to use the async database with analytics"""
    # Initialize database
    db = AsyncUserDatabase("example_bot.db")
    await db.initialize()

    # Create a superadmin user
    superadmin = User(
        user_id=123456789,
        username="superadmin",
        first_name="Super",
        last_name="Admin",
        user_role="superadmin",
    )

    await db.add_user(superadmin)

    # Check if user is superadmin
    is_super = await db.is_superadmin(123456789)
    print(f"Is superadmin: {is_super}")

    # Add small delays to prevent rapid concurrent access
    await asyncio.sleep(0.1)

    # Log some activities
    await db.log_activity(123456789, "command", {"command": "/start"})
    await asyncio.sleep(0.1)

    # Example: Deactivate the user
    deactivated = await db.deactivate_user(123456789)
    print(f"User deactivated: {deactivated}")

    # Try to deactivate again (should return False as user is already inactive)
    deactivated_again = await db.deactivate_user(123456789)
    print(f"User deactivated again: {deactivated_again}")

    # Example: Activate the user
    activated = await db.activate_user(123456789)
    print(f"User activated: {activated}")

    # Log another activity after reactivation
    await db.log_activity(123456789, "message", {"text": "Hello bot, I'm back!"})
    await asyncio.sleep(0.1)

    # Get analytics
    user_stats = await db.get_user_activity_stats(123456789)
    bot_analytics = await db.get_bot_analytics()

    print(f"User stats: {user_stats}")
    print(f"Bot analytics: {bot_analytics}")

    # Clean up test database
    import os

    try:
        os.remove("example_bot.db")
        os.remove("example_bot.db-wal")
        os.remove("example_bot.db-shm")
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage())
