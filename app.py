import os
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from helper import process_query  # Make sure helper.py exists

app = FastAPI()

# Optional: Add CORS for frontend use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Use specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/", include_in_schema=False)
@app.head("/", include_in_schema=False)
async def root():
    return {"message": "API is up and running"}

@app.get("/health/")
async def health_check():
    return {"status": "healthy"}

@app.post("/query/")
async def query_product(request: Request):
    """
    Expects JSON like: {"query": "your question"}
    """
    try:
        body = await request.json()
        query = body.get("query")

        if not query:
            raise HTTPException(status_code=400, detail="Missing 'query' in request body.")

        logger.info(f"Received query: {query}")
        result = process_query(query)
        return {"status": "success", "result": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error occurred.")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
