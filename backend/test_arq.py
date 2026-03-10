import asyncio
from arq.worker import Worker
from app.worker.settings import WorkerSettings

async def main():
    print("Testing worker startup...")
    print(f"Functions: {WorkerSettings.functions}")
    print(f"Has on_startup: {hasattr(WorkerSettings, 'on_startup')}")
    
    # Simulate ARQ worker startup
    class DummyCtx(dict):
        pass
        
    ctx = DummyCtx()
    await WorkerSettings.on_startup(ctx)
    print("Startup complete. Context keys:", list(ctx.keys()))

if __name__ == "__main__":
    asyncio.run(main())
