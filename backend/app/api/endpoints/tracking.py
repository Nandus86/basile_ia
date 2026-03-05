from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from typing import List, Optional

from app.database import get_db
from app.models.job_log import JobLog

router = APIRouter()

@router.get("/logs")
async def get_tracking_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    path: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get paginated list of system webhook/job logs"""
    query = select(JobLog)
    
    if status:
        query = query.where(JobLog.status == status)
    if path:
        query = query.where(JobLog.webhook_path.ilike(f"%{path}%"))
        
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get items
    query = query.order_by(desc(JobLog.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "items": logs,
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/stats")
async def get_tracking_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregated stats for dashboard charts"""
    # Group by status
    status_query = select(JobLog.status, func.count(JobLog.id)).group_by(JobLog.status)
    status_result = await db.execute(status_query)
    status_counts = [{"status": row[0], "count": row[1]} for row in status_result.all()]
    
    # Group by path (top 5)
    path_query = select(JobLog.webhook_path, func.count(JobLog.id)).group_by(JobLog.webhook_path).order_by(desc(func.count(JobLog.id))).limit(5)
    path_result = await db.execute(path_query)
    path_counts = [{"path": row[0], "count": row[1]} for row in path_result.all()]
    
    # Timeline (last 7 days grouped by day) -> simple implementation counting entries
    # In PostgreSQL we could use date_trunc. For SQLite/generic, we simplify:
    
    return {
        "by_status": status_counts,
        "by_path": path_counts,
        "total_calls": sum(s["count"] for s in status_counts)
    }
