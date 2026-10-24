"""
Serves the built React app (Docker image) from the same process as the API.

After an update the hashed file names in assets/ change, so a browser still
holding the old index.html asks for files that are gone and pages go blank.
index.html is therefore always re-checked with the server (`no-cache`), while
the hashed assets, whose names change with their content, are cached for good.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Re-check with the server every time (a cheap 304 when nothing changed).
REVALIDATE = "no-cache"
# Vite puts a content hash in every file name under assets/.
FOREVER = "public, max-age=31536000, immutable"


class _HashedAssets(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = FOREVER
        return response


def serve_frontend(app: FastAPI, dist: Path) -> None:
    dist = Path(dist).resolve()
    app.mount("/assets", _HashedAssets(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate, headers={"Cache-Control": REVALIDATE})
        return FileResponse(dist / "index.html", headers={"Cache-Control": REVALIDATE})
