import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text, event, func
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Field, SQLModel, Session, col, delete, or_, select, update


INITIAL_ALEMBIC_REVISION = "0001_current_schema"
DATETIME_FIELDS = {
    "created_at",
    "updated_at",
    "last_seen",
    "first_interaction",
    "last_interaction",
    "timestamp",
    "last_activity",
    "deleted_at",
}


class UserRole(Enum):
    """User roles with hierarchy levels."""

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
        """Check if this role can manage another role."""
        return self.level > other_role.level


@dataclass
class User:
    """User data model matching Telegram user structure with bot-specific fields."""

    user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_bot: bool = False
    is_premium: bool | None = None
    added_to_attachment_menu: bool | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_seen: datetime | None = None
    is_active: bool = False
    user_state: str | None = None
    user_role: str = "user"
    settings: dict[str, Any] | None = field(default_factory=dict)

    current_session_id: str | None = None

    total_messages: int = 0
    total_commands: int = 0
    first_interaction: datetime | None = None
    last_interaction: datetime | None = None


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
    """User activity tracking model."""

    id: int | None = None
    user_id: int = 0
    activity_type: str = ""
    activity_data: str | None = None
    timestamp: datetime | None = None
    session_id: str | None = None


class DatabaseError(Exception):
    """Custom exception for database operations."""


class UserRecord(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_username", "username"),
        Index("idx_user_role", "user_role"),
        Index("idx_is_active", "is_active"),
        Index("idx_created_at", "created_at"),
        Index("idx_last_seen", "last_seen"),
    )

    user_id: int = Field(primary_key=True)
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_bot: bool = Field(default=False)
    is_premium: bool | None = None
    added_to_attachment_menu: bool | None = None
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    updated_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    last_seen: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    is_active: bool = Field(default=False)
    user_state: str | None = None
    user_role: str = Field(default=UserRole.USER.role_name)
    settings: str | None = Field(default="{}", sa_column=Column(Text, nullable=True))
    total_messages: int = Field(default=0)
    total_commands: int = Field(default=0)
    first_interaction: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    last_interaction: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    current_session_id: str | None = None


class UserActivityRecord(SQLModel, table=True):
    __tablename__ = "user_activities"
    __table_args__ = (
        Index("idx_activity_user_id", "user_id"),
        Index("idx_activity_type", "activity_type"),
        Index("idx_activity_timestamp", "timestamp"),
        Index("idx_activity_session", "session_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
        )
    )
    activity_type: str = Field(nullable=False)
    activity_data: str | None = Field(default=None, sa_column=Column(Text))
    timestamp: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    session_id: str | None = None


class ChatSessionRecord(SQLModel, table=True):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_sessions_user_id", "user_id"),
        Index("idx_chat_sessions_created_at", "created_at"),
        Index("idx_chat_sessions_last_activity", "last_activity"),
        Index("idx_chat_sessions_deleted_at", "deleted_at"),
    )

    session_id: str = Field(primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
        )
    )
    name: str = Field(nullable=False)
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    last_activity: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, nullable=True)
    )
    message_count: int = Field(default=0)


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _sqlite_url(db_path: str | Path) -> str:
    path = Path(db_path)
    if str(path) == ":memory:":
        return "sqlite:///:memory:"
    return f"sqlite:///{path.resolve()}"


def _alembic_config(db_path: str | Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", _sqlite_url(db_path))
    return config


def _enable_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=memory")
        cursor.execute("PRAGMA mmap_size=268435456")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class MigrationManager:
    """Alembic-backed database migration compatibility wrapper."""

    CURRENT_VERSION = 2
    REQUIRED_LEGACY_TABLES = {
        "schema_migrations",
        "users",
        "user_activities",
        "chat_sessions",
    }
    REQUIRED_LEGACY_COLUMNS = {
        "users": {
            "user_id",
            "username",
            "first_name",
            "last_name",
            "language_code",
            "is_bot",
            "is_premium",
            "added_to_attachment_menu",
            "created_at",
            "updated_at",
            "last_seen",
            "is_active",
            "user_state",
            "user_role",
            "settings",
            "total_messages",
            "total_commands",
            "first_interaction",
            "last_interaction",
            "current_session_id",
        },
        "user_activities": {
            "id",
            "user_id",
            "activity_type",
            "activity_data",
            "timestamp",
            "session_id",
        },
        "chat_sessions": {
            "session_id",
            "user_id",
            "name",
            "created_at",
            "last_activity",
            "deleted_at",
            "message_count",
        },
    }

    @staticmethod
    async def get_db_version(db_path: str) -> int:
        """Return the legacy schema version, or CURRENT_VERSION for Alembic DBs."""
        engine = create_engine(_sqlite_url(db_path))
        try:
            with engine.connect() as conn:
                tables = set(sqlalchemy_inspect(conn).get_table_names())
                if "alembic_version" in tables:
                    result = conn.exec_driver_sql(
                        "SELECT version_num FROM alembic_version"
                    )
                    revision = result.scalar_one_or_none()
                    return MigrationManager.CURRENT_VERSION if revision else 0
                if "schema_migrations" not in tables:
                    return 0
                result = conn.exec_driver_sql(
                    "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
                )
                version = result.scalar_one_or_none()
                return int(version) if version is not None else 0
        except Exception:
            return 0
        finally:
            engine.dispose()

    @classmethod
    async def initialize_database(cls, db_path: str | Path) -> None:
        """Run Alembic on fresh DBs and stamp valid legacy v2 DBs."""
        engine = create_engine(_sqlite_url(db_path))
        try:
            with engine.connect() as conn:
                tables = set(sqlalchemy_inspect(conn).get_table_names())

            if "alembic_version" in tables:
                command.upgrade(_alembic_config(db_path), "head")
                return

            app_tables = tables & {"users", "user_activities", "chat_sessions"}
            if not app_tables:
                command.upgrade(_alembic_config(db_path), "head")
                return

            version = await cls.get_db_version(str(db_path))
            if version == cls.CURRENT_VERSION:
                cls._validate_legacy_schema(engine)
                command.stamp(_alembic_config(db_path), "head")
                return

            raise DatabaseError(
                "Database has a partial or unsupported pre-Alembic schema. "
                "Expected legacy schema_migrations version 2 before stamping Alembic."
            )
        finally:
            engine.dispose()

    @classmethod
    def _validate_legacy_schema(cls, engine: Engine) -> None:
        with engine.connect() as conn:
            inspector = sqlalchemy_inspect(conn)
            tables = set(inspector.get_table_names())
            missing_tables = cls.REQUIRED_LEGACY_TABLES - tables
            if missing_tables:
                raise DatabaseError(
                    f"Legacy database is missing required tables: {sorted(missing_tables)}"
                )

            for table_name, required_columns in cls.REQUIRED_LEGACY_COLUMNS.items():
                columns = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
                missing_columns = required_columns - columns
                if missing_columns:
                    raise DatabaseError(
                        f"Legacy table {table_name} is missing columns: "
                        f"{sorted(missing_columns)}"
                    )


class AsyncUserDatabase:
    """Async SQLModel database manager for aiogram bot users with analytics."""

    def __init__(self, db_path: str = "bot_users.db"):
        self.db_path = Path(db_path)
        self.logger = logging.getLogger(__name__)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            _sqlite_url(self.db_path),
            connect_args={"timeout": 10.0},
        )
        _enable_sqlite_pragmas(self.engine)
        self.session_factory = Session

    async def initialize(self) -> None:
        """Initialize database with Alembic migrations."""
        try:
            await MigrationManager.initialize_database(self.db_path)
            self.logger.info("Database initialized successfully")
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise DatabaseError(f"Database initialization failed: {e}")

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[Session]:
        with self.session_factory(self.engine, expire_on_commit=False) as session:
            try:
                yield session
            except SQLAlchemyError as e:
                session.rollback()
                self.logger.error(f"Database error: {e}")
                raise DatabaseError(f"Database operation failed: {e}")

    @staticmethod
    def _user_record_to_dataclass(record: UserRecord) -> User:
        settings: dict[str, Any] = {}
        if record.settings:
            try:
                parsed = json.loads(record.settings)
                settings = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                settings = {}

        return User(
            user_id=record.user_id,
            username=record.username,
            first_name=record.first_name,
            last_name=record.last_name,
            language_code=record.language_code,
            is_bot=bool(record.is_bot),
            is_premium=record.is_premium,
            added_to_attachment_menu=record.added_to_attachment_menu,
            created_at=_coerce_datetime(record.created_at),
            updated_at=_coerce_datetime(record.updated_at),
            last_seen=_coerce_datetime(record.last_seen),
            is_active=bool(record.is_active),
            user_state=record.user_state,
            user_role=record.user_role,
            settings=settings,
            current_session_id=record.current_session_id,
            total_messages=record.total_messages or 0,
            total_commands=record.total_commands or 0,
            first_interaction=_coerce_datetime(record.first_interaction),
            last_interaction=_coerce_datetime(record.last_interaction),
        )

    @staticmethod
    def _chat_session_record_to_dataclass(record: ChatSessionRecord) -> ChatSession:
        return ChatSession(
            session_id=record.session_id,
            user_id=record.user_id,
            name=record.name,
            created_at=_coerce_datetime(record.created_at) or datetime.now(),
            last_activity=_coerce_datetime(record.last_activity),
            ended_at=None,
            deleted_at=_coerce_datetime(record.deleted_at),
            message_count=record.message_count or 0,
        )

    @staticmethod
    def _row_to_user(row_dict: dict[str, Any]) -> User:
        for field_name in [
            "created_at",
            "updated_at",
            "last_seen",
            "first_interaction",
            "last_interaction",
        ]:
            row_dict[field_name] = _coerce_datetime(row_dict.get(field_name))

        if row_dict.get("settings"):
            try:
                row_dict["settings"] = json.loads(row_dict["settings"])
            except json.JSONDecodeError:
                row_dict["settings"] = {}

        return User(**row_dict)

    @staticmethod
    def _row_to_chat_session(row_dict: dict[str, Any]) -> ChatSession:
        for field_name in ("created_at", "last_activity", "ended_at", "deleted_at"):
            row_dict[field_name] = _coerce_datetime(row_dict.get(field_name))
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

    @staticmethod
    def _user_to_record_kwargs(user: User) -> dict[str, Any]:
        now = datetime.now()
        user.created_at = now
        user.updated_at = now
        user.first_interaction = now
        user.last_interaction = now

        return {
            "user_id": user.user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "language_code": user.language_code,
            "is_bot": user.is_bot,
            "is_premium": user.is_premium,
            "added_to_attachment_menu": user.added_to_attachment_menu,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_seen": user.last_seen,
            "is_active": user.is_active,
            "user_state": user.user_state,
            "user_role": user.user_role,
            "settings": json.dumps(user.settings or {}),
            "current_session_id": user.current_session_id,
            "total_messages": user.total_messages,
            "total_commands": user.total_commands,
            "first_interaction": user.first_interaction,
            "last_interaction": user.last_interaction,
        }

    @staticmethod
    def _normalize_update_values(values: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(values)
        if isinstance(normalized.get("settings"), dict):
            normalized["settings"] = json.dumps(normalized["settings"])
        for field_name in DATETIME_FIELDS:
            if field_name in normalized:
                normalized[field_name] = _coerce_datetime(normalized[field_name])
        return normalized

    async def add_user(self, user: User) -> bool:
        """Add a new user to the database."""
        try:
            async with self.get_session() as session:
                existing = session.get(UserRecord, user.user_id)
                if existing:
                    return False

                session.add(UserRecord(**self._user_to_record_kwargs(user)))
                session.commit()
                self.logger.info(f"Added new user: {user.user_id}")
                return True
        except Exception as e:
            self.logger.error(f"Error adding user {user.user_id}: {e}")
            raise DatabaseError(f"Failed to add user: {e}")

    async def get_user(self, user_id: int) -> User | None:
        """Retrieve a user by user_id."""
        try:
            async with self.get_session() as session:
                record = session.get(UserRecord, user_id)
                return self._user_record_to_dataclass(record) if record else None
        except Exception as e:
            self.logger.error(f"Error retrieving user {user_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user: {e}")

    async def update_user(self, user_id: int, **kwargs: Any) -> bool:
        """Update user information."""
        if not kwargs:
            return False

        try:
            async with self.get_session() as session:
                values = self._normalize_update_values(kwargs)
                values["updated_at"] = datetime.now()
                result = session.exec(
                    update(UserRecord)
                    .where(UserRecord.user_id == user_id)
                    .values(**values)
                )
                session.commit()
                if result.rowcount > 0:
                    self.logger.info(f"Updated user: {user_id}")
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error updating user {user_id}: {e}")
            raise DatabaseError(f"Failed to update user: {e}")

    async def set_user_role(self, user_id: int, role: str | UserRole) -> bool:
        """Set user role with validation."""
        try:
            role_name = role if isinstance(role, str) else role.role_name
            return await self.update_user(user_id, user_role=role_name)
        except ValueError as e:
            raise DatabaseError(f"Invalid role: {e}")

    async def is_superadmin(self, user_id: int) -> bool:
        """Check if user is a superadmin."""
        user = await self.get_user(user_id)
        return user.user_role == UserRole.SUPERADMIN.role_name if user else False

    async def is_admin_or_higher(self, user_id: int) -> bool:
        """Check if user is admin or superadmin."""
        user = await self.get_user(user_id)
        if not user:
            return False
        try:
            role = UserRole.from_string(user.user_role)
            return role.level > UserRole.USER.level
        except ValueError:
            return False

    async def can_manage_user(self, manager_id: int, target_id: int) -> bool:
        """Check if manager can manage target user."""
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
        """Get all users, optionally filtering by active status."""
        try:
            async with self.get_session() as session:
                statement = select(UserRecord)
                if active_only:
                    statement = statement.where(UserRecord.is_active.is_(True))
                statement = statement.order_by(col(UserRecord.created_at).desc())
                result = session.exec(statement)
                return [
                    self._user_record_to_dataclass(record) for record in result.all()
                ]
        except Exception as e:
            self.logger.error(f"Error retrieving all users: {e}")
            raise DatabaseError(f"Failed to retrieve users: {e}")

    async def get_users_by_role(self, role: str | UserRole) -> list[User]:
        """Get active users by their role."""
        role_name = role.role_name if isinstance(role, UserRole) else role
        try:
            async with self.get_session() as session:
                result = session.exec(
                    select(UserRecord)
                    .where(
                        UserRecord.user_role == role_name,
                        UserRecord.is_active.is_(True),
                    )
                    .order_by(col(UserRecord.created_at).desc())
                )
                return [
                    self._user_record_to_dataclass(record) for record in result.all()
                ]
        except Exception as e:
            self.logger.error(f"Error retrieving users by role {role_name}: {e}")
            raise DatabaseError(f"Failed to retrieve users by role: {e}")

    async def log_activity(
        self,
        user_id: int,
        activity_type: str,
        activity_data: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> bool:
        """Log user activity for analytics."""
        try:
            async with self.get_session() as session:
                now = datetime.now()
                data_json = json.dumps(activity_data) if activity_data else None
                session.add(
                    UserActivityRecord(
                        user_id=user_id,
                        activity_type=activity_type,
                        activity_data=data_json,
                        session_id=session_id,
                        timestamp=now,
                    )
                )

                values: dict[str, Any] = {
                    "last_interaction": now,
                    "last_seen": now,
                    "updated_at": now,
                }
                if activity_type == "message":
                    values["total_messages"] = UserRecord.total_messages + 1
                elif activity_type == "command":
                    values["total_commands"] = UserRecord.total_commands + 1

                session.exec(
                    update(UserRecord)
                    .where(UserRecord.user_id == user_id)
                    .values(**values)
                )
                session.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error logging activity for user {user_id}: {e}")
            return False

    async def get_user_activity_stats(
        self, user_id: int, days: int = 30
    ) -> dict[str, Any]:
        """Get user activity statistics."""
        try:
            async with self.get_session() as session:
                since_date = datetime.now() - timedelta(days=days)

                activity_result = session.exec(
                    select(UserActivityRecord.activity_type, func.count())
                    .where(
                        UserActivityRecord.user_id == user_id,
                        UserActivityRecord.timestamp >= since_date,
                    )
                    .group_by(UserActivityRecord.activity_type)
                )
                activity_breakdown = {row[0]: row[1] for row in activity_result.all()}

                date_expr = func.date(UserActivityRecord.timestamp)
                daily_result = session.exec(
                    select(date_expr, func.count())
                    .where(
                        UserActivityRecord.user_id == user_id,
                        UserActivityRecord.timestamp >= since_date,
                    )
                    .group_by(date_expr)
                    .order_by(date_expr.desc())
                )
                daily_activity = {row[0]: row[1] for row in daily_result.all()}

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

    async def get_message_activity_user_stats(
        self, user_id: int, days: int = 30
    ) -> list[dict[str, Any]]:
        """Get user message activity statistics grouped by day."""
        try:
            async with self.get_session() as session:
                since_date = datetime.now() - timedelta(days=days)
                date_expr = func.date(UserActivityRecord.timestamp)
                result = session.exec(
                    select(date_expr, func.count(), UserActivityRecord.activity_data)
                    .where(
                        UserActivityRecord.user_id == user_id,
                        UserActivityRecord.activity_type == "message",
                        UserActivityRecord.timestamp >= since_date,
                    )
                    .group_by(date_expr)
                    .order_by(date_expr.desc())
                )

                message_stats: list[dict[str, Any]] = []
                for row in result.all():
                    try:
                        data = json.loads(row[2]) if row[2] else {}
                    except json.JSONDecodeError:
                        data = {}
                    message_stats.append(
                        {"date": row[0], "count": row[1], "activity_data": data}
                    )
                return message_stats
        except Exception as e:
            self.logger.error(f"Error getting message stats for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get message stats: {e}")

    async def get_bot_analytics(self, days: int = 30) -> dict[str, Any]:
        """Get comprehensive bot analytics."""
        try:
            async with self.get_session() as session:
                since_date = datetime.now() - timedelta(days=days)

                total_active_users = (
                    session.exec(
                        select(func.count())
                        .select_from(UserRecord)
                        .where(UserRecord.is_active.is_(True))
                    )
                ).one()

                new_users = (
                    session.exec(
                        select(func.count())
                        .select_from(UserRecord)
                        .where(UserRecord.created_at >= since_date)
                    )
                ).one()

                active_users_period = (
                    session.exec(
                        select(
                            func.count(func.distinct(UserActivityRecord.user_id))
                        ).where(UserActivityRecord.timestamp >= since_date)
                    )
                ).one()

                top_result = session.exec(
                    select(
                        UserRecord.user_id,
                        UserRecord.username,
                        UserRecord.first_name,
                        func.count(UserActivityRecord.id),
                    )
                    .outerjoin(
                        UserActivityRecord,
                        UserRecord.user_id == UserActivityRecord.user_id,
                    )
                    .where(
                        or_(
                            UserActivityRecord.timestamp >= since_date,
                            UserActivityRecord.timestamp.is_(None),
                        )
                    )
                    .group_by(UserRecord.user_id)
                    .order_by(func.count(UserActivityRecord.id).desc())
                    .limit(10)
                )
                top_users = [
                    {
                        "user_id": row[0],
                        "username": row[1],
                        "name": row[2],
                        "activity_count": row[3],
                    }
                    for row in top_result.all()
                ]

                activity_result = session.exec(
                    select(UserActivityRecord.activity_type, func.count())
                    .where(UserActivityRecord.timestamp >= since_date)
                    .group_by(UserActivityRecord.activity_type)
                    .order_by(func.count().desc())
                )
                activity_breakdown = {row[0]: row[1] for row in activity_result.all()}

                role_result = session.exec(
                    select(UserRecord.user_role, func.count())
                    .where(UserRecord.is_active.is_(True))
                    .group_by(UserRecord.user_role)
                )
                role_distribution = {row[0]: row[1] for row in role_result.all()}

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

    async def get_command_usage_stats(self, days: int = 30) -> dict[str, int]:
        """Get command usage statistics."""
        try:
            async with self.get_session() as session:
                since_date = datetime.now() - timedelta(days=days)
                result = session.exec(
                    select(UserActivityRecord.activity_data, func.count())
                    .where(
                        UserActivityRecord.activity_type == "command",
                        UserActivityRecord.timestamp >= since_date,
                        UserActivityRecord.activity_data.is_not(None),
                    )
                    .group_by(UserActivityRecord.activity_data)
                    .order_by(func.count().desc())
                )

                command_stats: dict[str, int] = {}
                for row in result.all():
                    try:
                        data = json.loads(row[0])
                        command_name = data.get("command", "unknown")
                        command_stats[command_name] = row[1]
                    except json.JSONDecodeError:
                        continue
                return command_stats
        except Exception as e:
            self.logger.error(f"Error getting command stats: {e}")
            return {}

    async def get_user_count(self, active_only: bool = True) -> int:
        """Get total number of users."""
        try:
            async with self.get_session() as session:
                statement = select(func.count()).select_from(UserRecord)
                if active_only:
                    statement = statement.where(UserRecord.is_active.is_(True))
                return (session.exec(statement)).one()
        except Exception as e:
            self.logger.error(f"Error counting users: {e}")
            raise DatabaseError(f"Failed to count users: {e}")

    async def cleanup_old_activities(self, days: int = 90) -> int:
        """Clean up old activity records."""
        try:
            async with self.get_session() as session:
                cutoff_date = datetime.now() - timedelta(days=days)
                result = session.exec(
                    delete(UserActivityRecord).where(
                        UserActivityRecord.timestamp < cutoff_date
                    )
                )
                session.commit()
                deleted_count = result.rowcount
                self.logger.info(f"Cleaned up {deleted_count} old activity records")
                return deleted_count
        except Exception as e:
            self.logger.error(f"Error cleaning up activities: {e}")
            return 0

    async def activate_user(self, target_user_id: int) -> bool:
        """Activate a user by setting is_active to True."""
        try:
            async with self.get_session() as session:
                result = session.exec(
                    update(UserRecord)
                    .where(
                        UserRecord.user_id == target_user_id,
                        UserRecord.is_active.is_(False),
                    )
                    .values(is_active=True, updated_at=datetime.now())
                )
                session.commit()
                if result.rowcount > 0:
                    self.logger.info(f"Activated user: {target_user_id}")
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error activating user {target_user_id}: {e}")
            raise DatabaseError(f"Failed to activate user: {e}")

    async def deactivate_user(self, target_user_id: int) -> bool:
        """Deactivate a user by setting is_active to False."""
        try:
            async with self.get_session() as session:
                result = session.exec(
                    update(UserRecord)
                    .where(
                        UserRecord.user_id == target_user_id,
                        UserRecord.is_active.is_(True),
                    )
                    .values(is_active=False, updated_at=datetime.now())
                )
                session.commit()
                if result.rowcount > 0:
                    self.logger.info(f"Deactivated user: {target_user_id}")
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error deactivating user {target_user_id}: {e}")
            raise DatabaseError(f"Failed to deactivate user: {e}")

    async def create_chat_session(
        self, user_id: int, session_id: str, name: str | None = None
    ) -> str:
        """Create a new chat session and set it as current for the user."""
        name = name or datetime.now().strftime("%d.%m.%Y %H:%M")
        now = datetime.now()
        try:
            async with self.get_session() as session:
                session.add(
                    ChatSessionRecord(
                        session_id=session_id,
                        user_id=user_id,
                        name=name,
                        created_at=now,
                    )
                )
                session.exec(
                    update(UserRecord)
                    .where(UserRecord.user_id == user_id)
                    .values(current_session_id=session_id, updated_at=now)
                )
                session.commit()
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
            async with self.get_session() as session:
                statement = select(ChatSessionRecord).where(
                    ChatSessionRecord.user_id == user_id
                )
                if not include_deleted:
                    statement = statement.where(ChatSessionRecord.deleted_at.is_(None))
                statement = statement.order_by(col(ChatSessionRecord.created_at).desc())
                result = session.exec(statement)
                return [
                    self._chat_session_record_to_dataclass(record)
                    for record in result.all()
                ]
        except Exception as e:
            self.logger.error(f"Error listing chat sessions for user {user_id}: {e}")
            raise DatabaseError(f"Failed to list chat sessions: {e}")

    async def soft_delete_chat_session(self, user_id: int, session_id: str) -> bool:
        """Soft-delete a chat session and clear it if it is current."""
        try:
            async with self.get_session() as session:
                now = datetime.now()
                result = session.exec(
                    update(ChatSessionRecord)
                    .where(
                        ChatSessionRecord.session_id == session_id,
                        ChatSessionRecord.user_id == user_id,
                        ChatSessionRecord.deleted_at.is_(None),
                    )
                    .values(deleted_at=now)
                )
                user = session.get(UserRecord, user_id)
                if user and user.current_session_id == session_id:
                    user.current_session_id = None
                    user.updated_at = now
                    session.add(user)
                session.commit()
                if result.rowcount > 0:
                    self.logger.info(
                        f"Soft-deleted chat session {session_id} for user {user_id}"
                    )
                    return True
                return False
        except Exception as e:
            self.logger.error(
                f"Error soft-deleting chat session {session_id} for user {user_id}: {e}"
            )
            return False

    async def restore_chat_session(self, user_id: int, session_id: str) -> bool:
        """Restore a previously soft-deleted chat session."""
        try:
            async with self.get_session() as session:
                result = session.exec(
                    update(ChatSessionRecord)
                    .where(
                        ChatSessionRecord.session_id == session_id,
                        ChatSessionRecord.user_id == user_id,
                        ChatSessionRecord.deleted_at.is_not(None),
                    )
                    .values(deleted_at=None)
                )
                session.commit()
                return result.rowcount > 0
        except Exception as e:
            self.logger.error(
                f"Error restoring chat session {session_id} for user {user_id}: {e}"
            )
            return False

    async def get_current_chat_session(self, user_id: int) -> ChatSession | None:
        """Return the current chat session if it is not soft-deleted."""
        try:
            async with self.get_session() as session:
                result = session.exec(
                    select(ChatSessionRecord)
                    .join(
                        UserRecord,
                        UserRecord.current_session_id == ChatSessionRecord.session_id,
                    )
                    .where(
                        UserRecord.user_id == user_id,
                        ChatSessionRecord.deleted_at.is_(None),
                    )
                    .limit(1)
                )
                record = result.first()
                return (
                    self._chat_session_record_to_dataclass(record) if record else None
                )
        except Exception as e:
            self.logger.error(f"Error fetching current session for user {user_id}: {e}")
            return None

    async def update_chat_session_activity(
        self, session_id: str, message_count: int | None = None
    ) -> None:
        """Update chat session last activity and optionally message count."""
        try:
            async with self.get_session() as session:
                values: dict[str, Any] = {"last_activity": datetime.now()}
                if message_count is not None:
                    values["message_count"] = message_count
                session.exec(
                    update(ChatSessionRecord)
                    .where(ChatSessionRecord.session_id == session_id)
                    .values(**values)
                )
                session.commit()
        except Exception as e:
            self.logger.error(f"Error updating chat session activity: {e}")

    async def deactivate_old_current_sessions(self, minutes: int) -> list[int]:
        """Clear current_session_id for users with inactive current sessions."""
        try:
            async with self.get_session() as session:
                cutoff_time = datetime.now() - timedelta(minutes=minutes)
                result = session.exec(
                    select(UserRecord.user_id)
                    .join(
                        ChatSessionRecord,
                        UserRecord.current_session_id == ChatSessionRecord.session_id,
                    )
                    .where(
                        ChatSessionRecord.last_activity < cutoff_time,
                        UserRecord.current_session_id.is_not(None),
                    )
                )
                user_ids = list(result.all())
                if not user_ids:
                    return []

                session.exec(
                    update(UserRecord)
                    .where(UserRecord.user_id.in_(user_ids))
                    .values(current_session_id=None, updated_at=datetime.now())
                )
                session.commit()
                self.logger.info(
                    f"Cleared current_session_id for users: {user_ids} due to inactivity"
                )
                return user_ids
        except Exception as e:
            self.logger.error(f"Error clearing old current user sessions: {e}")
            return []

    async def delete_empty_chat_sessions(self, days: int = 7) -> list[str]:
        """Permanently delete empty chat sessions older than the cutoff."""
        try:
            async with self.get_session() as session:
                cutoff_time = datetime.now() - timedelta(days=days)
                result = session.exec(
                    select(ChatSessionRecord.session_id).where(
                        ChatSessionRecord.message_count == 0,
                        ChatSessionRecord.created_at < cutoff_time,
                    )
                )
                session_ids = list(result.all())
                if not session_ids:
                    return []

                session.exec(
                    delete(ChatSessionRecord).where(
                        ChatSessionRecord.session_id.in_(session_ids)
                    )
                )
                session.commit()
                self.logger.info(f"Permanently deleted empty sessions: {session_ids}")
                return session_ids
        except Exception as e:
            self.logger.error(f"Error deleting empty chat sessions: {e}")
            return []


def create_user_from_telegram(telegram_user: Any) -> User:
    """Create User object from aiogram's Telegram User object."""
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


async def example_usage() -> None:
    """Example of how to use the async database with analytics."""
    db = AsyncUserDatabase("example_bot.db")
    await db.initialize()

    superadmin = User(
        user_id=123456789,
        username="superadmin",
        first_name="Super",
        last_name="Admin",
        user_role="superadmin",
    )

    await db.add_user(superadmin)
    is_super = await db.is_superadmin(123456789)
    print(f"Is superadmin: {is_super}")

    await asyncio.sleep(0.1)
    await db.log_activity(123456789, "command", {"command": "/start"})
    await asyncio.sleep(0.1)

    deactivated = await db.deactivate_user(123456789)
    print(f"User deactivated: {deactivated}")

    deactivated_again = await db.deactivate_user(123456789)
    print(f"User deactivated again: {deactivated_again}")

    activated = await db.activate_user(123456789)
    print(f"User activated: {activated}")

    await db.log_activity(123456789, "message", {"text": "Hello bot, I'm back!"})
    await asyncio.sleep(0.1)

    user_stats = await db.get_user_activity_stats(123456789)
    bot_analytics = await db.get_bot_analytics()

    print(f"User stats: {user_stats}")
    print(f"Bot analytics: {bot_analytics}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage())
