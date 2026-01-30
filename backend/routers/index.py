"""
Index router - API endpoints for code indexing and search
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional

from services.indexer_service import CodeIndexer
from models.index_models import IndexRequest, IndexResponse, SearchResponse

router = APIRouter()

# Initialize indexer service
try:
    indexer: Optional[CodeIndexer] = CodeIndexer()
except Exception as e:
    indexer = None
    print(f"Warning: Could not initialize CodeIndexer: {e}")


@router.post("/", response_model=IndexResponse)
async def index_project(request: IndexRequest):
    """Index a project directory for RAG search"""
    if indexer is None:
        raise HTTPException(status_code=500, detail="Indexer not initialized")

    try:
        files_indexed, chunks_created = indexer.index_project(
            request.project_path, request.force_reindex
        )

        return IndexResponse(
            status="success",
            files_indexed=files_indexed,
            chunks_created=chunks_created,
            message=f"Indexed {files_indexed} files with {chunks_created} code chunks",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=SearchResponse)
async def search_code(
    query: str, max_results: int = 5, file_types: Optional[List[str]] = None
):
    """Search indexed codebase for relevant code chunks"""
    if indexer is None:
        raise HTTPException(status_code=500, detail="Indexer not initialized")

    try:
        results = indexer.search(query, max_results, file_types)

        return SearchResponse(query=query, results=results, total_results=len(results))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_index_stats():
    """Get indexing statistics"""
    if indexer is None:
        raise HTTPException(status_code=500, detail="Indexer not initialized")

    try:
        return indexer.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear")
async def clear_index():
    """Clear all indexed data"""
    if indexer is None:
        raise HTTPException(status_code=500, detail="Indexer not initialized")

    try:
        indexer.clear_index()
        return {"status": "success", "message": "Index cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
