"""«🔤 Как читается» на карточке — транскрипцией по слогам, под спойлером (FR-43, M-09)."""

from dataclasses import dataclass

from muallim.application.feedback import FeedbackCatalog
from muallim.application.ports.reading import ReadingGuide
from muallim.application.transcription import Reading, as_text, legend, reading
from muallim.domain.curriculum import LessonItem
from muallim.domain.learner import Learner


@dataclass(frozen=True, slots=True)
class CardReading:
    reading: Reading
    legend: tuple[str, ...]  # пояснения к значкам, которые есть в этой строке


@dataclass(frozen=True, slots=True)
class HowToRead:
    guide: ReadingGuide
    catalog: FeedbackCatalog

    def execute(self, learner: Learner, item: LessonItem) -> CardReading | None:
        if not item.is_practice:
            return None
        phonemes = self.guide.phonemes(item.text)
        if not phonemes:
            return None
        lexicon = self.catalog.renderer(self.catalog.resolve(learner)).lexicon
        shown = reading(phonemes, lexicon)
        return CardReading(shown, legend(as_text(shown), lexicon))
