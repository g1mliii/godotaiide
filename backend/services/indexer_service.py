"""
Code indexing service using ChromaDB for RAG
"""

import chromadb
from chromadb.config import Settings as ChromaSettings
from pathlib import Path
import re
from typing import List, Dict, Tuple, Optional, Pattern
import hashlib
import json
import asyncio
import aiofiles
import logging

from models.index_models import CodeChunk

logger = logging.getLogger(__name__)


class CodeIndexer:
    """Service for indexing and searching code using ChromaDB"""

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {".gd", ".cs", ".cpp", ".h", ".hpp", ".c"}

    # Pre-compiled regex patterns for chunking code (performance optimization)
    PATTERNS: Dict[str, Dict[str, Pattern]] = {
        ".gd": {
            "function": re.compile(r"^func\s+(\w+)\s*\([^)]*\):", re.MULTILINE),
            "class": re.compile(r"^class\s+(\w+)\s*:", re.MULTILINE),
        },
        ".cs": {
            "function": re.compile(
                r"^\s*(?:public|private|protected|internal)?\s*(?:static)?\s*\w+\s+(\w+)\s*\([^)]*\)",
                re.MULTILINE,
            ),
            "class": re.compile(
                r"^\s*(?:public|private|protected|internal)?\s*class\s+(\w+)",
                re.MULTILINE,
            ),
        },
        ".cpp": {
            "function": re.compile(r"^\s*\w+\s+(\w+)\s*\([^)]*\)\s*{", re.MULTILINE),
            "class": re.compile(r"^\s*class\s+(\w+)", re.MULTILINE),
        },
        ".h": {
            "function": re.compile(r"^\s*\w+\s+(\w+)\s*\([^)]*\);", re.MULTILINE),
            "class": re.compile(r"^\s*class\s+(\w+)", re.MULTILINE),
        },
        ".hpp": {
            "function": re.compile(r"^\s*\w+\s+(\w+)\s*\([^)]*\)", re.MULTILINE),
            "class": re.compile(r"^\s*class\s+(\w+)", re.MULTILINE),
        },
    }

    # Multiline patterns for faster parsing (captures entire function/class)
    MULTILINE_PATTERNS: Dict[str, Dict[str, Pattern]] = {
        ".gd": {
            "functions": re.compile(
                r"^(func\s+(\w+)\s*\([^)]*\):.*?)(?=^func\s+|\Z)",
                re.MULTILINE | re.DOTALL,
            ),
            "classes": re.compile(
                r"^(class\s+(\w+)\s*:.*?)(?=^class\s+|\Z)", re.MULTILINE | re.DOTALL
            ),
        },
        ".py": {
            "functions": re.compile(
                r"^(def\s+(\w+)\s*\([^)]*\):.*?)(?=^def\s+|^class\s+|\Z)",
                re.MULTILINE | re.DOTALL,
            ),
            "classes": re.compile(
                r"^(class\s+(\w+).*?)(?=^class\s+|\Z)", re.MULTILINE | re.DOTALL
            ),
        },
        ".cpp": {
            "functions": re.compile(
                r"^(\w+\s+(\w+)\s*\([^)]*\)\s*\{(?:[^{}]|\{[^{}]*\})*\})",
                re.MULTILINE | re.DOTALL,
            ),
            "classes": re.compile(
                r"^(class\s+(\w+).*?\{(?:[^{}]|\{[^{}]*\})*\};)",
                re.MULTILINE | re.DOTALL,
            ),
        },
    }

    def __init__(self, persist_directory: str = ".godot_minds/index"):
        """
        Initialize the code indexer

        Args:
            persist_directory: Directory to persist ChromaDB data
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="code_chunks", metadata={"description": "Code chunks for RAG"}
        )

        # File hash cache for incremental indexing
        self._file_hashes: Dict[str, str] = {}
        self._load_file_hashes()

    def index_project(
        self, project_path: str, force_reindex: bool = False
    ) -> Tuple[int, int]:
        """
        Index all supported files in a project

        Args:
            project_path: Path to the project directory
            force_reindex: If True, clear existing index first

        Returns:
            Tuple of (files_indexed, chunks_created)
        """
        if force_reindex:
            # Delete collection and recreate it
            try:
                self.client.delete_collection("code_chunks")
            except Exception:
                pass
            self.collection = self.client.create_collection(
                name="code_chunks", metadata={"description": "Code chunks for RAG"}
            )

        project_dir = Path(project_path).resolve()
        files_indexed = 0
        chunks_created = 0

        for ext in self.SUPPORTED_EXTENSIONS:
            for file_path in project_dir.rglob(f"*{ext}"):
                # Skip ignored directories
                if any(
                    part in [".git", ".godot", ".godot_minds", "addons"]
                    for part in file_path.parts
                ):
                    continue

                try:
                    chunks = self._chunk_file(file_path, project_dir)
                    if chunks:
                        self._add_chunks_to_index(chunks)
                        files_indexed += 1
                        chunks_created += len(chunks)
                except Exception as e:
                    print(f"Error indexing {file_path}: {e}")

        return files_indexed, chunks_created

    def _chunk_file(self, file_path: Path, project_root: Path) -> List[Dict]:
        """
        Chunk a file into functions/classes or whole file

        Args:
            file_path: Path to the file
            project_root: Root directory of the project

        Returns:
            List of chunk dictionaries
        """
        try:
            # Use read_text for synchronous operations (indexing is already in background)
            # For async contexts, use aiofiles in the caller
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return []

        ext = file_path.suffix

        # Use multiline patterns if available for better performance
        if ext in self.MULTILINE_PATTERNS:
            return self._process_file_content_multiline(
                content, file_path, project_root
            )

        # Fallback to line-by-line processing
        relative_path = str(file_path.relative_to(project_root))

        # Get patterns for this file type
        patterns = self.PATTERNS.get(ext, {})

        chunks = []
        lines = content.split("\n")

        # Try to find functions/classes
        current_chunk = None
        current_lines = []

        for i, line in enumerate(lines):
            # Check for function
            if "function" in patterns:
                match = patterns["function"].match(line)
                if match:
                    # Save previous chunk
                    if current_chunk:
                        chunks.append(current_chunk)

                    # Start new function chunk
                    current_chunk = {
                        "file_path": relative_path,
                        "chunk_type": "function",
                        "name": match.group(1),
                        "line_start": i + 1,
                        "lines": [line],
                    }
                    current_lines = [line]
                    continue

            # Check for class
            if "class" in patterns:
                match = patterns["class"].match(line)
                if match:
                    # Save previous chunk
                    if current_chunk:
                        chunks.append(current_chunk)

                    # Start new class chunk
                    current_chunk = {
                        "file_path": relative_path,
                        "chunk_type": "class",
                        "name": match.group(1),
                        "line_start": i + 1,
                        "lines": [line],
                    }
                    current_lines = [line]
                    continue

            # Add line to current chunk
            if current_chunk:
                current_lines.append(line)

                # End chunk on empty line or significant indentation decrease (heuristic)
                if not line.strip() or (
                    len(current_lines) > 5 and not line.startswith((" ", "\t"))
                ):
                    current_chunk["content"] = "\n".join(current_lines)
                    current_chunk["line_end"] = i + 1
                    chunks.append(current_chunk)
                    current_chunk = None
                    current_lines = []

        # Add last chunk
        if current_chunk:
            current_chunk["content"] = "\n".join(current_lines)
            current_chunk["line_end"] = len(lines)
            chunks.append(current_chunk)

        # If no chunks found, index entire file
        if not chunks:
            chunks.append(
                {
                    "file_path": relative_path,
                    "chunk_type": "file",
                    "name": file_path.name,
                    "line_start": 1,
                    "line_end": len(lines),
                    "content": content,
                }
            )

        return chunks

    def _add_chunks_to_index(self, chunks: List[Dict]) -> None:
        """
        Add code chunks to ChromaDB

        Args:
            chunks: List of chunk dictionaries
        """
        if not chunks:
            return

        documents = []
        metadatas = []
        ids = []

        for chunk in chunks:
            # Create unique ID for chunk
            chunk_id = hashlib.md5(
                f"{chunk['file_path']}:{chunk.get('name', '')}:{chunk['line_start']}".encode()
            ).hexdigest()

            documents.append(chunk["content"])
            metadatas.append(
                {
                    "file_path": chunk["file_path"],
                    "chunk_type": chunk["chunk_type"],
                    "name": chunk.get("name", ""),
                    "line_start": chunk["line_start"],
                    "line_end": chunk["line_end"],
                }
            )
            ids.append(chunk_id)

        # Add to collection
        self.collection.add(documents=documents, metadatas=metadatas, ids=ids)

    def search(
        self, query: str, max_results: int = 5, file_types: Optional[List[str]] = None
    ) -> List[CodeChunk]:
        """
        Search for code chunks matching a query

        Args:
            query: Search query
            max_results: Maximum number of results
            file_types: Optional list of file extensions to filter

        Returns:
            List of CodeChunk objects
        """
        # Build filter
        _where = None
        if file_types:
            # This is a simplified filter - ChromaDB filtering is limited
            # In production, you might want to filter results post-query
            pass

        # Query collection
        results = self.collection.query(query_texts=[query], n_results=max_results)

        # Convert to CodeChunk objects
        chunks = []
        if results["documents"]:
            for i in range(len(results["documents"][0])):
                metadata = results["metadatas"][0][i]
                chunks.append(
                    CodeChunk(
                        file_path=metadata["file_path"],
                        content=results["documents"][0][i],
                        chunk_type=metadata["chunk_type"],
                        name=metadata.get("name"),
                        line_start=metadata.get("line_start"),
                        line_end=metadata.get("line_end"),
                        similarity_score=1.0
                        - results["distances"][0][i],  # Convert distance to similarity
                    )
                )

        return chunks

    def remove_file(self, file_path: Path, project_root: Path) -> None:
        """
        Remove a file from the index

        Args:
            file_path: Path to the file
            project_root: Root directory of the project
        """
        try:
            relative_path = str(file_path.relative_to(project_root))

            # Delete from ChromaDB using metadata filter
            self.collection.delete(where={"file_path": relative_path})

            # Remove from hash cache
            if relative_path in self._file_hashes:
                del self._file_hashes[relative_path]
                self._save_file_hashes()

            logger.info(f"Removed file from index: {relative_path}")

        except Exception as e:
            logger.error(f"Error removing file {file_path}: {e}")

    def clear_index(self) -> None:
        """Clear all indexed data"""
        try:
            self.client.delete_collection("code_chunks")
        except Exception:
            pass
        self.collection = self.client.create_collection(
            name="code_chunks", metadata={"description": "Code chunks for RAG"}
        )

    def get_stats(self) -> Dict:
        """Get indexing statistics"""
        count = self.collection.count()
        return {"total_chunks": count, "persist_directory": str(self.persist_directory)}

    def _load_file_hashes(self):
        """Load file hash cache from disk"""
        hash_file = self.persist_directory / "file_hashes.json"
        if hash_file.exists():
            try:
                with open(hash_file, "r") as f:
                    self._file_hashes = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load file hashes: {e}")
                self._file_hashes = {}

    def _save_file_hashes(self):
        """Save file hash cache to disk"""
        hash_file = self.persist_directory / "file_hashes.json"
        try:
            with open(hash_file, "w") as f:
                json.dump(self._file_hashes, f)
        except Exception as e:
            logger.error(f"Could not save file hashes: {e}")

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file"""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            hasher.update(f.read())
        return hasher.hexdigest()

    def _find_files(
        self, project_dir: Path, extensions: set, max_files: int = 10000
    ) -> List[Path]:
        """
        Find files with limit to prevent runaway searches

        Args:
            project_dir: Project directory
            extensions: Set of file extensions
            max_files: Maximum files to find

        Returns:
            List of file paths
        """
        all_files = []
        for ext in extensions:
            for file_path in project_dir.rglob(f"*{ext}"):
                # Skip ignored directories
                if any(
                    part in [".git", ".godot", ".godot_minds", "addons"]
                    for part in file_path.parts
                ):
                    continue

                all_files.append(file_path)
                if len(all_files) >= max_files:
                    logger.warning(f"Hit max file limit ({max_files}), stopping search")
                    return all_files
        return all_files

    async def _chunk_file_async(
        self, file_path: Path, project_root: Path
    ) -> List[Dict]:
        """
        Async version of _chunk_file

        Args:
            file_path: Path to the file
            project_root: Root directory of the project

        Returns:
            List of chunk dictionaries
        """
        try:
            async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
                content = await f.read()
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return []

        # CPU-bound processing - use multiline if available for better performance
        ext = file_path.suffix
        if ext in self.MULTILINE_PATTERNS:
            return self._process_file_content_multiline(
                content, file_path, project_root
            )
        else:
            return self._process_file_content(content, file_path, project_root)

    def _process_file_content_multiline(
        self, content: str, file_path: Path, project_root: Path
    ) -> List[Dict]:
        """
        Process file content using multiline regex for better performance

        Args:
            content: File content
            file_path: Path to the file
            project_root: Root directory of the project

        Returns:
            List of chunk dictionaries
        """
        ext = file_path.suffix
        relative_path = str(file_path.relative_to(project_root))

        # Get multiline patterns for this file type
        patterns = self.MULTILINE_PATTERNS.get(ext, {})

        chunks = []
        lines = content.split("\n")

        # Find all functions at once using multiline regex
        if "functions" in patterns:
            for match in patterns["functions"].finditer(content):
                function_content = match.group(1)
                function_name = match.group(2)

                # Calculate line numbers
                start_pos = match.start(1)
                line_start = content[:start_pos].count("\n") + 1
                line_end = line_start + function_content.count("\n")

                chunks.append(
                    {
                        "file_path": relative_path,
                        "chunk_type": "function",
                        "name": function_name,
                        "line_start": line_start,
                        "line_end": line_end,
                        "content": function_content.strip(),
                        "lines": [],  # Not needed with multiline
                    }
                )

        # Find all classes at once using multiline regex
        if "classes" in patterns:
            for match in patterns["classes"].finditer(content):
                class_content = match.group(1)
                class_name = match.group(2)

                # Calculate line numbers
                start_pos = match.start(1)
                line_start = content[:start_pos].count("\n") + 1
                line_end = line_start + class_content.count("\n")

                chunks.append(
                    {
                        "file_path": relative_path,
                        "chunk_type": "class",
                        "name": class_name,
                        "line_start": line_start,
                        "line_end": line_end,
                        "content": class_content.strip(),
                        "lines": [],  # Not needed with multiline
                    }
                )

        # If no chunks found, index entire file
        if not chunks:
            chunks.append(
                {
                    "file_path": relative_path,
                    "chunk_type": "file",
                    "name": file_path.name,
                    "line_start": 1,
                    "line_end": len(lines),
                    "content": content,
                }
            )

        return chunks

    def _process_file_content(
        self, content: str, file_path: Path, project_root: Path
    ) -> List[Dict]:
        """
        Process file content into chunks (CPU-bound, called from async)

        Args:
            content: File content
            file_path: Path to the file
            project_root: Root directory of the project

        Returns:
            List of chunk dictionaries
        """
        ext = file_path.suffix
        relative_path = str(file_path.relative_to(project_root))

        # Get patterns for this file type
        patterns = self.PATTERNS.get(ext, {})

        chunks = []
        lines = content.split("\n")

        # Try to find functions/classes
        current_chunk = None
        current_lines = []

        for i, line in enumerate(lines):
            # Check for function
            if "function" in patterns:
                match = patterns["function"].match(line)
                if match:
                    # Save previous chunk
                    if current_chunk:
                        chunks.append(current_chunk)

                    # Start new function chunk
                    current_chunk = {
                        "file_path": relative_path,
                        "chunk_type": "function",
                        "name": match.group(1),
                        "line_start": i + 1,
                        "lines": [line],
                    }
                    current_lines = [line]
                    continue

            # Check for class
            if "class" in patterns:
                match = patterns["class"].match(line)
                if match:
                    # Save previous chunk
                    if current_chunk:
                        chunks.append(current_chunk)

                    # Start new class chunk
                    current_chunk = {
                        "file_path": relative_path,
                        "chunk_type": "class",
                        "name": match.group(1),
                        "line_start": i + 1,
                        "lines": [line],
                    }
                    current_lines = [line]
                    continue

            # Add line to current chunk
            if current_chunk:
                current_lines.append(line)

                # End chunk on empty line or significant indentation decrease (heuristic)
                if not line.strip() or (
                    len(current_lines) > 5 and not line.startswith((" ", "\t"))
                ):
                    current_chunk["content"] = "\n".join(current_lines)
                    current_chunk["line_end"] = i + 1
                    chunks.append(current_chunk)
                    current_chunk = None
                    current_lines = []

        # Add last chunk
        if current_chunk:
            current_chunk["content"] = "\n".join(current_lines)
            current_chunk["line_end"] = len(lines)
            chunks.append(current_chunk)

        # If no chunks found, index entire file
        if not chunks:
            chunks.append(
                {
                    "file_path": relative_path,
                    "chunk_type": "file",
                    "name": file_path.name,
                    "line_start": 1,
                    "line_end": len(lines),
                    "content": content,
                }
            )

        return chunks

    async def index_project_async(
        self,
        project_path: str,
        force_reindex: bool = False,
        incremental: bool = True,
        max_files: int = 10000,
    ) -> Tuple[int, int]:
        """
        Async version of index_project with incremental support

        Args:
            project_path: Path to the project directory
            force_reindex: If True, clear existing index first
            incremental: If True, only index changed files
            max_files: Maximum files to index

        Returns:
            Tuple of (files_indexed, chunks_created)
        """
        if force_reindex:
            # Delete collection and recreate it
            try:
                self.client.delete_collection("code_chunks")
            except Exception:
                pass
            self.collection = self.client.create_collection(
                name="code_chunks", metadata={"description": "Code chunks for RAG"}
            )
            self._file_hashes.clear()

        project_dir = Path(project_path).resolve()

        # Find all files (blocking operation, run in thread)
        all_files = await asyncio.to_thread(
            self._find_files, project_dir, self.SUPPORTED_EXTENSIONS, max_files
        )

        # Determine which files need indexing
        files_to_index = []
        if incremental and not force_reindex:
            for file_path in all_files:
                file_hash = self._compute_file_hash(file_path)
                rel_path = str(file_path.relative_to(project_dir))

                # Only index if hash changed
                if self._file_hashes.get(rel_path) != file_hash:
                    files_to_index.append(file_path)
                    self._file_hashes[rel_path] = file_hash
        else:
            files_to_index = all_files
            # Update all hashes
            for file_path in all_files:
                file_hash = self._compute_file_hash(file_path)
                rel_path = str(file_path.relative_to(project_dir))
                self._file_hashes[rel_path] = file_hash

        # Index files
        chunks_created = 0
        for file_path in files_to_index:
            try:
                chunks = await self._chunk_file_async(file_path, project_dir)
                if chunks:
                    # Add to index (blocking, run in thread)
                    await asyncio.to_thread(self._add_chunks_to_index, chunks)
                    chunks_created += len(chunks)
            except Exception as e:
                logger.error(f"Error indexing {file_path}: {e}", exc_info=True)

        # Save file hashes
        self._save_file_hashes()

        return len(files_to_index), chunks_created
