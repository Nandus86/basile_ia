"""
Backup & Restore API Endpoints
Provides endpoints for creating and restoring system backups
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.backup_service import create_full_backup, restore_full_backup

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/create")
async def create_backup(db: AsyncSession = Depends(get_db)):
    """
    Create a full system backup and return as JSON download.
    
    Exports:
    - All PostgreSQL tables
    - Weaviate vector collections
    - Local files (documents, VFS)
    
    Sensitive fields (API keys, tokens) are excluded for security.
    """
    try:
        from app.services.backup_service import TABLE_EXPORT_ORDER, WEAVIATE_COLLECTIONS, _export_weaviate_collection, _export_files_directory, _sanitize_row, _serialize_row
        from app.config import settings
        from datetime import timezone
        from sqlalchemy import text
        from app.weaviate_client import get_weaviate
        from app.services.document_processor import UPLOAD_DIR
        from app.services.vfs_rag_service import get_vfs_root
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"basile_backup_{timestamp}.json"
        
        async def stream_backup():
            yield '{\n'
            
            # Metadata
            metadata = {
                "version": "1.0.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "database_url": settings.DATABASE_URL,
                "weaviate_url": settings.WEAVIATE_URL,
            }
            yield '"metadata": ' + json.dumps(metadata) + ',\n'
            
            # Tables
            yield '"tables": {\n'
            first_table = True
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
                    
                    if not first_table:
                        yield ',\n'
                    yield f'  "{table_name}": ' + json.dumps(rows)
                    first_table = False
                except Exception as e:
                    logger.warning(f"[Backup] Failed to export table {table_name}: {e}")
                    
            yield '\n},\n'
            
            # Weaviate
            yield '"weaviate": {\n'
            first_coll = True
            weaviate_client = get_weaviate()
            for coll_name in WEAVIATE_COLLECTIONS:
                try:
                    objects = await _export_weaviate_collection(weaviate_client, coll_name)
                    if not first_coll:
                        yield ',\n'
                    yield f'  "{coll_name}": ' + json.dumps(objects)
                    first_coll = False
                except Exception as e:
                    logger.warning(f"[Backup] Failed to export Weaviate {coll_name}: {e}")
            
            yield '\n},\n'
            
            # Files
            yield '"files": {\n'
            try:
                docs = _export_files_directory(UPLOAD_DIR)
                yield '  "documents": ' + json.dumps(docs) + ',\n'
            except Exception as e:
                logger.warning(f"[Backup] Failed to export docs: {e}")
                yield '  "documents": {},\n'
                
            try:
                vfs_root = get_vfs_root()
                vfs_files = _export_files_directory(vfs_root, base_path=vfs_root)
                yield '  "vfs": ' + json.dumps(vfs_files) + '\n'
            except Exception as e:
                logger.warning(f"[Backup] Failed to export VFS: {e}")
                yield '  "vfs": {}\n'
            
            yield '}\n'
            yield '}\n'

        return StreamingResponse(
            stream_backup(),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    
    except Exception as e:
        logger.error(f"[Backup] Error creating backup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {str(e)}")


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    skip_files: bool = Form(False),
    dry_run: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    """
    Restore system from a backup file.
    
    Parameters:
    - file: JSON backup file to restore
    - skip_files: If true, only restore database and Weaviate (skip local files)
    - dry_run: If true, preview what would be restored without applying changes
    
    WARNING: This will DELETE all existing data before restoring!
    """
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Backup file must be a JSON file")
    
    try:
        content = await file.read()
        backup_data = json.loads(content)
    
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
    
    if "metadata" not in backup_data or "tables" not in backup_data:
        raise HTTPException(status_code=400, detail="Invalid backup file structure")
    
    try:
        stats = await restore_full_backup(db, backup_data, skip_files=skip_files, dry_run=dry_run)
        
        return JSONResponse(content={
            "status": "success",
            "dry_run": dry_run,
            "restored": stats,
        })
    
    except Exception as e:
        logger.error(f"[Restore] Error restoring backup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to restore backup: {str(e)}")


@router.post("/dry-run")
async def dry_run_restore(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview what would be restored from a backup file without applying changes.
    
    Returns statistics about tables, Weaviate collections, and files that would be restored.
    """
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Backup file must be a JSON file")
    
    try:
        content = await file.read()
        backup_data = json.loads(content)
    
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
    
    if "metadata" not in backup_data or "tables" not in backup_data:
        raise HTTPException(status_code=400, detail="Invalid backup file structure")
    
    try:
        stats = await restore_full_backup(db, backup_data, skip_files=False, dry_run=True)
        
        return JSONResponse(content={
            "status": "success",
            "dry_run": True,
            "would_restore": stats,
        })
    
    except Exception as e:
        logger.error(f"[Restore] Error during dry run: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze backup: {str(e)}")
