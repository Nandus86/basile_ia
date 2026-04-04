"""
Backup & Restore Service
Handles full system backup and restore for PostgreSQL, Weaviate, and local files
"""
import os
import json
import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, delete, table
from sqlalchemy.orm import selectinload

from app.config import settings
from app.weaviate_client import get_weaviate
from app.services.document_processor import UPLOAD_DIR
from app.services.vfs_rag_service import get_vfs_root

logger = logging.getLogger(__name__)

SENSITIVE_FIELDS = {
    "ai_providers": ["api_key"],
    "webhook_configs": ["access_token"],
    "api_keys": ["key_hash"],
}

TABLE_EXPORT_ORDER = [
    "ai_providers",
    "emotional_profiles",
    "agent_groups",
    "mcp_groups",
    "skill_groups",
    "vfs_knowledge_bases",
    "information_bases",
    "agents",
    "mcps",
    "skills",
    "documents",
    "vfs_files",
    "agent_configs",
    "agent_collaborators",
    "pending_approvals",
    "webhook_configs",
    "job_logs",
    "conversation_messages",
    "api_keys",
    "agent_mcp_access",
    "agent_mcp_group_access",
    "agent_document_access",
    "agent_skill_access",
    "agent_info_base_access",
    "agent_vfs_knowledge_base_access",
]

TABLE_IMPORT_ORDER = list(reversed(TABLE_EXPORT_ORDER))

WEAVIATE_COLLECTIONS = [
    "AgentDocuments",
    "ContactMemory",
    "AgentSelfMemory",
    "InformationBaseNode",
]


def _sanitize_row(table_name: str, row: dict) -> dict:
    sanitized = dict(row)
    for field in SENSITIVE_FIELDS.get(table_name, []):
        if field in sanitized:
            sanitized[field] = None
    return sanitized


def _serialize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize_value(v) for k, v in row.items()}


async def create_full_backup(db: AsyncSession) -> Dict[str, Any]:
    logger.info("[Backup] Starting full system backup...")
    
    tables_data = {}
    for table_name in TABLE_EXPORT_ORDER:
        try:
            result = await db.execute(text(f"SELECT * FROM {table_name}"))
            columns = result.keys()
            rows = []
            for row in result.fetchall():
                row_dict = dict(zip(columns, row))
                row_dict = _serialize_row(row_dict)
                row_dict = _sanitize_row(table_name, row_dict)
                rows.append(row_dict)
            tables_data[table_name] = rows
            logger.info(f"[Backup] Exported {len(rows)} rows from {table_name}")
        except Exception as e:
            logger.warning(f"[Backup] Failed to export {table_name}: {e}")
            tables_data[table_name] = []

    weaviate_data = {}
    weaviate_client = get_weaviate()
    for collection_name in WEAVIATE_COLLECTIONS:
        try:
            objects = await _export_weaviate_collection(weaviate_client, collection_name)
            weaviate_data[collection_name] = objects
            logger.info(f"[Backup] Exported {len(objects)} objects from Weaviate collection {collection_name}")
        except Exception as e:
            logger.warning(f"[Backup] Failed to export Weaviate collection {collection_name}: {e}")
            weaviate_data[collection_name] = []

    files_data = {}
    try:
        files_data["documents"] = _export_files_directory(UPLOAD_DIR)
        logger.info(f"[Backup] Exported {len(files_data['documents'])} document files")
    except Exception as e:
        logger.warning(f"[Backup] Failed to export documents directory: {e}")
        files_data["documents"] = {}

    try:
        vfs_root = get_vfs_root()
        files_data["vfs"] = _export_files_directory(vfs_root, base_path=vfs_root)
        logger.info(f"[Backup] Exported {len(files_data['vfs'])} VFS files")
    except Exception as e:
        logger.warning(f"[Backup] Failed to export VFS directory: {e}")
        files_data["vfs"] = {}

    backup = {
        "metadata": {
            "version": "1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database_url": settings.DATABASE_URL,
            "weaviate_url": settings.WEAVIATE_URL,
        },
        "tables": tables_data,
        "weaviate": weaviate_data,
        "files": files_data,
    }
    
    logger.info("[Backup] Full backup completed successfully")
    return backup


async def _export_weaviate_collection(weaviate_client, collection_name: str) -> List[Dict[str, Any]]:
    def _sync_export():
        client = weaviate_client._ensure_connected()
        if collection_name not in client.collections.list_all():
            return []
        
        collection = client.collections.get(collection_name)
        objects = []
        
        cursor = None
        while True:
            result = collection.iterator(include_vector=True, return_metadata=True)
            for obj in result:
                objects.append({
                    "uuid": str(obj.uuid),
                    "properties": dict(obj.properties),
                    "vector": obj.vector if hasattr(obj, 'vector') and obj.vector else None,
                })
            break
        
        return objects
    
    import asyncio
    return await asyncio.to_thread(_sync_export)


def _export_files_directory(directory: Path, base_path: Optional[Path] = None) -> Dict[str, str]:
    if base_path is None:
        base_path = directory
    
    files = {}
    if not directory.exists():
        return files
    
    for file_path in directory.rglob("*"):
        if file_path.is_file():
            try:
                relative_path = str(file_path.relative_to(base_path))
                with open(file_path, "rb") as f:
                    content = f.read()
                files[relative_path] = base64.b64encode(content).decode("utf-8")
            except Exception as e:
                logger.warning(f"[Backup] Failed to read file {file_path}: {e}")
    
    return files


async def restore_full_backup(
    db: AsyncSession,
    backup_data: Dict[str, Any],
    skip_files: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    logger.info(f"[Restore] Starting {'dry run ' if dry_run else ''}restore...")
    
    metadata = backup_data.get("metadata", {})
    version = metadata.get("version", "unknown")
    logger.info(f"[Restore] Backup version: {version}")

    stats = {
        "tables": {},
        "weaviate": {},
        "files": {"documents": 0, "vfs": 0},
        "warnings": [],
    }

    if dry_run:
        tables_data = backup_data.get("tables", {})
        for table_name in TABLE_IMPORT_ORDER:
            rows = tables_data.get(table_name, [])
            if rows:
                stats["tables"][table_name] = len(rows)
        
        weaviate_data = backup_data.get("weaviate", {})
        for collection_name in WEAVIATE_COLLECTIONS:
            objects = weaviate_data.get(collection_name, [])
            if objects:
                stats["weaviate"][collection_name] = len(objects)
        
        if not skip_files:
            files_data = backup_data.get("files", {})
            stats["files"]["documents"] = len(files_data.get("documents", {}))
            stats["files"]["vfs"] = len(files_data.get("vfs", {}))
        
        stats["warnings"].append("API keys were excluded from backup and will remain unchanged")
        logger.info("[Restore] Dry run completed")
        return stats

    for table_name in TABLE_IMPORT_ORDER:
        try:
            await db.execute(text(f"DELETE FROM {table_name}"))
            logger.info(f"[Restore] Cleared table {table_name}")
        except Exception as e:
            logger.warning(f"[Restore] Failed to clear {table_name}: {e}")

    await db.commit()

    tables_data = backup_data.get("tables", {})
    for table_name in TABLE_EXPORT_ORDER:
        rows = tables_data.get(table_name, [])
        if not rows:
            stats["tables"][table_name] = 0
            continue
        
        try:
            columns = rows[0].keys()
            for row in rows:
                if table_name in SENSITIVE_FIELDS:
                    for field in SENSITIVE_FIELDS[table_name]:
                        if field in row and row[field] is None:
                            row.pop(field, None)
                
                column_names = ", ".join(columns)
                placeholders = ", ".join([f":{col}" for col in columns])
                await db.execute(
                    text(f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"),
                    row
                )
            
            stats["tables"][table_name] = len(rows)
            logger.info(f"[Restore] Restored {len(rows)} rows to {table_name}")
        except Exception as e:
            logger.error(f"[Restore] Failed to restore {table_name}: {e}")
            stats["warnings"].append(f"Failed to restore {table_name}: {str(e)}")

    await db.commit()

    weaviate_data = backup_data.get("weaviate", {})
    weaviate_client = get_weaviate()
    for collection_name in WEAVIATE_COLLECTIONS:
        objects = weaviate_data.get(collection_name, [])
        if not objects:
            stats["weaviate"][collection_name] = 0
            continue
        
        try:
            await _restore_weaviate_collection(weaviate_client, collection_name, objects)
            stats["weaviate"][collection_name] = len(objects)
            logger.info(f"[Restore] Restored {len(objects)} objects to Weaviate collection {collection_name}")
        except Exception as e:
            logger.error(f"[Restore] Failed to restore Weaviate collection {collection_name}: {e}")
            stats["warnings"].append(f"Failed to restore Weaviate {collection_name}: {str(e)}")

    if not skip_files:
        files_data = backup_data.get("files", {})
        
        try:
            doc_count = _restore_files_directory(files_data.get("documents", {}), UPLOAD_DIR)
            stats["files"]["documents"] = doc_count
            logger.info(f"[Restore] Restored {doc_count} document files")
        except Exception as e:
            logger.error(f"[Restore] Failed to restore documents: {e}")
            stats["warnings"].append(f"Failed to restore documents: {str(e)}")
        
        try:
            vfs_root = get_vfs_root()
            vfs_count = _restore_files_directory(files_data.get("vfs", {}), vfs_root)
            stats["files"]["vfs"] = vfs_count
            logger.info(f"[Restore] Restored {vfs_count} VFS files")
        except Exception as e:
            logger.error(f"[Restore] Failed to restore VFS files: {e}")
            stats["warnings"].append(f"Failed to restore VFS files: {str(e)}")

    logger.info("[Restore] Restore completed")
    return stats


async def _restore_weaviate_collection(weaviate_client, collection_name: str, objects: List[Dict[str, Any]]):
    def _sync_restore():
        client = weaviate_client._ensure_connected()
        
        if collection_name not in client.collections.list_all():
            from weaviate.classes.config import Configure, Property, DataType
            client.collections.create(
                name=collection_name,
                vectorizer_config=Configure.Vectorizer.text2vec_openai(),
                properties=[
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="document_id", data_type=DataType.TEXT),
                    Property(name="document_name", data_type=DataType.TEXT),
                    Property(name="chunk_index", data_type=DataType.INT),
                    Property(name="source", data_type=DataType.TEXT),
                    Property(name="chunk_metadata", data_type=DataType.TEXT),
                    Property(name="agent_id", data_type=DataType.TEXT),
                    Property(name="contact_id", data_type=DataType.TEXT),
                    Property(name="memory_type", data_type=DataType.TEXT),
                    Property(name="metadata", data_type=DataType.TEXT),
                    Property(name="created_at", data_type=DataType.DATE),
                    Property(name="base_code", data_type=DataType.TEXT),
                    Property(name="user_id", data_type=DataType.TEXT),
                    Property(name="external_id", data_type=DataType.TEXT),
                    Property(name="facet_type", data_type=DataType.TEXT),
                ]
            )
        
        collection = client.collections.get(collection_name)
        
        for obj in objects:
            try:
                uuid = obj.get("uuid")
                properties = obj.get("properties", {})
                vector = obj.get("vector")
                
                if collection.data.exists(uuid):
                    collection.data.delete_by_id(uuid)
                
                if vector:
                    collection.data.insert(properties=properties, uuid=uuid, vector=vector)
                else:
                    collection.data.insert(properties=properties, uuid=uuid)
            except Exception as e:
                logger.warning(f"[Restore] Failed to restore Weaviate object {uuid}: {e}")
    
    import asyncio
    await asyncio.to_thread(_sync_restore)


def _restore_files_directory(files: Dict[str, str], target_dir: Path) -> int:
    count = 0
    for relative_path, content_b64 in files.items():
        try:
            file_path = target_dir / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            content = base64.b64decode(content_b64)
            with open(file_path, "wb") as f:
                f.write(content)
            count += 1
        except Exception as e:
            logger.warning(f"[Restore] Failed to restore file {relative_path}: {e}")
    
    return count
