from uuid import UUID

from arq.connections import ArqRedis


class ArqPhotoJobQueue:
    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    async def enqueue_processing(self, photo_id: UUID) -> None:
        # Deterministic job id: a double confirmation cannot start two concurrent runs.
        await self._pool.enqueue_job(
            "process_photo", str(photo_id), _job_id=f"process_photo:{photo_id}"
        )
