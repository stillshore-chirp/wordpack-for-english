from __future__ import annotations

from functools import partial

import anyio

from ...application.quiz.generation_jobs import QuizGenerator
from ...domain.quiz.generation_progress import QuizGenerationProgressCallback
from ...flows.quiz_generate import QuizGenerateFlow
from ...models.quiz import Quiz, QuizGenerateRequest


class QuizGenerateFlowAdapter(QuizGenerator):
    def __init__(self, *, owner_user_id: str | None = None) -> None:
        self._owner_user_id = owner_user_id

    async def generate(
        self,
        req: QuizGenerateRequest,
        store: object,
        *,
        on_progress: QuizGenerationProgressCallback | None = None,
    ) -> Quiz:
        flow = QuizGenerateFlow(store=store, owner_user_id=self._owner_user_id)
        return await anyio.to_thread.run_sync(partial(flow.run, req, on_progress))
