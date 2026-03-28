import httpx
import asyncio
import sys

async def test_api():
    async with httpx.AsyncClient() as client:
        # Get a job ID
        r = await client.get('http://localhost:8009/tracking/logs?limit=5')
        if r.status_code != 200:
            print(f'Failed to fetch logs: {r.status_code} {r.text}')
            return
            
        logs = r.json().get('items', [])
        if not logs:
            print('No logs found')
            return
            
        job_id = None
        for log in logs:
            if log['status'] in ('completed', 'failed'):
                job_id = log['job_id']
                break
                
        if not job_id:
            print('No completed/failed jobs found')
            return
            
        print(f'Found job: {job_id}. Sending POST to /test...')
        sys.stdout.flush()
        
        # Test the job
        res = await client.post(f'http://localhost:8009/tracking/jobs/{job_id}/test', timeout=30.0)
        print(f'Status: {res.status_code}')
        print(f'Response: {res.text}')

if __name__ == '__main__':
    asyncio.run(test_api())
