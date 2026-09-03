from fastapi import FastAPI
from .api.router import router as api_router

def create_app() -> FastAPI:
    app = FastAPI(title="Mindmap Backend")
    app.include_router(api_router)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
