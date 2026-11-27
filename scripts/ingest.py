"""Parse, chunk, embed and store the RFCs in data/rfc_list.yaml. Run: make ingest"""

import sys
from pathlib import Path

from app.config import get_settings
from app.db.connection import connect
from app.db.schema_check import SchemaMismatchError
from app.ingest.pipeline import NotMigratedError, ingest
from app.ingest.rfc_list import load_rfc_list
from app.llm.embeddings import FastEmbedEmbedder

RAW_DIR = Path("data/raw")


def main() -> int:
    settings = get_settings()
    embedder = FastEmbedEmbedder(settings.embed_model, settings.embed_dim, settings.embed_cache_dir)
    try:
        with connect(settings.database_url) as conn:
            summary = ingest(
                conn,
                load_rfc_list(),
                RAW_DIR,
                embedder,
                max_tokens=settings.chunk_max_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
    except (NotMigratedError, SchemaMismatchError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"ingested {len(summary.ingested)}, unchanged {len(summary.unchanged)}, "
        f"removed {len(summary.removed)}, chunks written {summary.chunks_written}, "
        f"{summary.seconds:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
