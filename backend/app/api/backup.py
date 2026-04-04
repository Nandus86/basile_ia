"""
Backup & Restore API Endpoints
Provides endpoints for creating and restoring system backups
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException
from fastapi.responses import Response, StreamingResponse, JSONResponse
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
        backup_data = await create_full_backup(db)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"basile_backup_{timestamp}.json"
        
        json_bytes = json.dumps(backup_data, default=str, ensure_ascii=False).encode("utf-8")
        
        return Response(
            content=json_bytes,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(json_bytes)),
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
