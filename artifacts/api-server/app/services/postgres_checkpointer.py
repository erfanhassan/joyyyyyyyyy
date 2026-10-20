import logging
import random
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Sequence, Tuple
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
    PendingWrite,
    WRITES_IDX_MAP,
    get_checkpoint_metadata,
)
from sqlalchemy import text
from app.db.session import sync_engine, async_engine

logger = logging.getLogger("joy.checkpointer.postgres")


class PostgreSQLSaver(BaseCheckpointSaver):
    """
    PostgreSQL LangGraph Checkpointer:
    Preserves complete multi-tenant LangGraph state in PostgreSQL tables:
    - checkpoints
    - checkpoint_blobs
    - checkpoint_writes
    Supports both sync and async execution paths.
    """

    def __init__(self, serde=None):
        super().__init__(serde=serde)
        # Checkpoint tables are provisioned by the existing Alembic migration.
        # Do not mutate the schema during import/startup on Replit.

    @classmethod
    def setup_tables(cls):
        """Ensures checkpoint tables exist in PostgreSQL."""
        try:
            with sync_engine.begin() as conn:
                conn.execute(
                    text("""
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        thread_id VARCHAR(255) NOT NULL,
                        checkpoint_ns VARCHAR(255) NOT NULL DEFAULT '',
                        checkpoint_id VARCHAR(255) NOT NULL,
                        parent_checkpoint_id VARCHAR(255),
                        type VARCHAR(50) NOT NULL,
                        checkpoint_blob BYTEA NOT NULL,
                        metadata_type VARCHAR(50) NOT NULL,
                        metadata_blob BYTEA NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                    );
                    CREATE TABLE IF NOT EXISTS checkpoint_blobs (
                        thread_id VARCHAR(255) NOT NULL,
                        checkpoint_ns VARCHAR(255) NOT NULL DEFAULT '',
                        channel VARCHAR(255) NOT NULL,
                        version VARCHAR(255) NOT NULL,
                        type VARCHAR(50) NOT NULL,
                        blob BYTEA,
                        PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
                    );
                    CREATE TABLE IF NOT EXISTS checkpoint_writes (
                        thread_id VARCHAR(255) NOT NULL,
                        checkpoint_ns VARCHAR(255) NOT NULL DEFAULT '',
                        checkpoint_id VARCHAR(255) NOT NULL,
                        task_id VARCHAR(255) NOT NULL,
                        idx INTEGER NOT NULL,
                        channel VARCHAR(255) NOT NULL,
                        type VARCHAR(50) NOT NULL,
                        blob BYTEA,
                        task_path VARCHAR(255) NOT NULL DEFAULT '',
                        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                    );
                    """)
                )
        except Exception as e:
            logger.debug(f"Checkpointer setup_tables notice: {e}")

    def setup(self):
        """LangGraph compatibility method to initialize checkpointer tables."""
        self.setup_tables()

    def get_next_version(self, current: Optional[str], channel: None) -> str:
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(str(current).split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"

    # ==========================================
    # Synchronous Methods
    # ==========================================
    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = config["configurable"].get("checkpoint_id")

        with sync_engine.connect() as conn:
            if checkpoint_id:
                row = conn.execute(
                    text(
                        "SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
                        "type, checkpoint_blob, metadata_type, metadata_blob "
                        "FROM checkpoints "
                        "WHERE thread_id = :tid AND checkpoint_ns = :ns AND checkpoint_id = :cid"
                    ),
                    {"tid": thread_id, "ns": checkpoint_ns, "cid": str(checkpoint_id)},
                ).mappings().first()
            else:
                row = conn.execute(
                    text(
                        "SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
                        "type, checkpoint_blob, metadata_type, metadata_blob "
                        "FROM checkpoints "
                        "WHERE thread_id = :tid AND checkpoint_ns = :ns "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"tid": thread_id, "ns": checkpoint_ns},
                ).mappings().first()

            if not row:
                return None

            c_blob_type = row["type"]
            c_blob = row["checkpoint_blob"]
            m_blob_type = row["metadata_type"]
            m_blob = row["metadata_blob"]
            curr_cid = row["checkpoint_id"]
            parent_cid = row["parent_checkpoint_id"]

            checkpoint_data: Dict[str, Any] = self.serde.loads_typed((c_blob_type, bytes(c_blob)))
            metadata: Dict[str, Any] = self.serde.loads_typed((m_blob_type, bytes(m_blob)))

            # Fetch channel blobs
            blobs_rows = conn.execute(
                text(
                    "SELECT channel, version, type, blob "
                    "FROM checkpoint_blobs "
                    "WHERE thread_id = :tid AND checkpoint_ns = :ns"
                ),
                {"tid": thread_id, "ns": checkpoint_ns},
            ).mappings().all()

            blobs_map = {
                (r["channel"], r["version"]): (r["type"], bytes(r["blob"]) if r["blob"] else b"")
                for r in blobs_rows
            }

            channel_values = {}
            for channel, version in checkpoint_data.get("channel_versions", {}).items():
                blob_tuple = blobs_map.get((channel, str(version)))
                if blob_tuple and blob_tuple[0] != "empty" and blob_tuple[1]:
                    try:
                        channel_values[channel] = self.serde.loads_typed(blob_tuple)
                    except Exception as e:
                        logger.warning(f"Failed to load blob for channel {channel}: {e}")

            checkpoint = {
                **checkpoint_data,
                "channel_values": channel_values,
            }

            # Fetch pending writes
            writes_rows = conn.execute(
                text(
                    "SELECT task_id, idx, channel, type, blob, task_path "
                    "FROM checkpoint_writes "
                    "WHERE thread_id = :tid AND checkpoint_ns = :ns AND checkpoint_id = :cid "
                    "ORDER BY task_id, idx"
                ),
                {"tid": thread_id, "ns": checkpoint_ns, "cid": curr_cid},
            ).mappings().all()

            pending_writes: List[PendingWrite] = [
                (
                    r["task_id"],
                    r["channel"],
                    self.serde.loads_typed((r["type"], bytes(r["blob"]))) if r["blob"] else None,
                )
                for r in writes_rows
            ]

            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": curr_cid,
                    }
                },
                checkpoint=checkpoint,  # type: ignore[arg-type]
                metadata=metadata,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_cid,
                        }
                    }
                    if parent_cid
                    else None
                ),
                pending_writes=pending_writes,
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])
        parent_id = config["configurable"].get("checkpoint_id")

        c = checkpoint.copy()
        values: Dict[str, Any] = c.pop("channel_values", {})

        with sync_engine.begin() as conn:
            # Store channel blobs
            for channel, version in new_versions.items():
                if channel in values:
                    blob_type, blob_bytes = self.serde.dumps_typed(values[channel])
                else:
                    blob_type, blob_bytes = ("empty", b"")

                conn.execute(
                    text(
                        "INSERT INTO checkpoint_blobs (thread_id, checkpoint_ns, channel, version, type, blob) "
                        "VALUES (:tid, :ns, :ch, :ver, :type, :blob) "
                        "ON CONFLICT (thread_id, checkpoint_ns, channel, version) "
                        "DO UPDATE SET type = EXCLUDED.type, blob = EXCLUDED.blob"
                    ),
                    {
                        "tid": thread_id,
                        "ns": checkpoint_ns,
                        "ch": channel,
                        "ver": str(version),
                        "type": blob_type,
                        "blob": blob_bytes,
                    },
                )

            # Store checkpoint & metadata
            c_type, c_blob = self.serde.dumps_typed(c)
            m_type, m_blob = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))

            conn.execute(
                text(
                    "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
                    "type, checkpoint_blob, metadata_type, metadata_blob) "
                    "VALUES (:tid, :ns, :cid, :pid, :ctype, :cblob, :mtype, :mblob) "
                    "ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id) "
                    "DO UPDATE SET parent_checkpoint_id = EXCLUDED.parent_checkpoint_id, "
                    "type = EXCLUDED.type, checkpoint_blob = EXCLUDED.checkpoint_blob, "
                    "metadata_type = EXCLUDED.metadata_type, metadata_blob = EXCLUDED.metadata_blob"
                ),
                {
                    "tid": thread_id,
                    "ns": checkpoint_ns,
                    "cid": checkpoint_id,
                    "pid": str(parent_id) if parent_id else None,
                    "ctype": c_type,
                    "cblob": c_blob,
                    "mtype": m_type,
                    "mblob": m_blob,
                },
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])

        with sync_engine.begin() as conn:
            for idx, (channel, val) in enumerate(writes):
                blob_type, blob_bytes = self.serde.dumps_typed(val)
                conn.execute(
                    text(
                        "INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob, task_path) "
                        "VALUES (:tid, :ns, :cid, :task_id, :idx, :channel, :type, :blob, :task_path) "
                        "ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) DO NOTHING"
                    ),
                    {
                        "tid": thread_id,
                        "ns": checkpoint_ns,
                        "cid": checkpoint_id,
                        "task_id": task_id,
                        "idx": idx,
                        "channel": channel,
                        "type": blob_type,
                        "blob": blob_bytes,
                        "task_path": task_path,
                    },
                )

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        if not config:
            return

        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))

        query = (
            "SELECT checkpoint_id FROM checkpoints "
            "WHERE thread_id = :tid AND checkpoint_ns = :ns ORDER BY created_at DESC"
        )
        if limit:
            query += f" LIMIT {limit}"

        with sync_engine.connect() as conn:
            rows = conn.execute(text(query), {"tid": thread_id, "ns": checkpoint_ns}).fetchall()

        for r in rows:
            tup = self.get_tuple(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": r[0],
                    }
                }
            )
            if tup:
                yield tup

    def delete_thread(self, thread_id: str) -> None:
        with sync_engine.begin() as conn:
            conn.execute(text("DELETE FROM checkpoint_writes WHERE thread_id = :tid"), {"tid": str(thread_id)})
            conn.execute(text("DELETE FROM checkpoint_blobs WHERE thread_id = :tid"), {"tid": str(thread_id)})
            conn.execute(text("DELETE FROM checkpoints WHERE thread_id = :tid"), {"tid": str(thread_id)})

    # ==========================================
    # Asynchronous Methods
    # ==========================================
    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        return self.get_tuple(config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def adelete_thread(self, thread_id: str) -> None:
        self.delete_thread(thread_id)
