import asyncio
from app.database import AsyncSessionLocal
from app.models.job_log import JobLog
from sqlalchemy import select
from app.api.endpoints.tracking import test_job

async def test_job_manually():
    async with AsyncSessionLocal() as db:
        # Pega um job processado recentemente (ou que contenha context_data/payload)
        query = select(JobLog).order_by(JobLog.created_at.desc()).limit(1)
        result = await db.execute(query)
        job = result.scalar_one_or_none()
        
        if not job:
            print('No jobs found')
            return
            
        print(f'Testing job {job.job_id}')
        
        try:
            res = await test_job(job.job_id, db)
            print(f'Success! Response: {res}')
        except Exception as e:
            import traceback
            print(f'Failed to test job:')
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_job_manually())
