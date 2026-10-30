"""DI-контейнер (dishka): какой порт какой реализацией закрывается. Единственное место «склейки»."""

import subprocess
from collections.abc import AsyncIterator

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide, provide_all
from dishka.integrations.aiogram import AiogramProvider
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from muallim import __version__
from muallim.application.feedback import FeedbackCatalog
from muallim.application.ports.annotation import AnnotationTasks, AnnotatorDirectory
from muallim.application.ports.erasures import ErasureLog
from muallim.application.ports.reading import AyahSyllables, ReadingGuide
from muallim.application.ports.recognition import PronunciationRecognizer
from muallim.application.ports.repositories import (
    AttemptRepository,
    CurriculumSnapshots,
    LearnerProfileRepository,
    LearnerRepository,
    LearnerSettingsRepository,
    QuizAnswerRepository,
    ReminderRecipients,
    UnitOfWork,
)
from muallim.application.ports.storage import (
    ArticulationVideoLibrary,
    AudioStore,
    ReferenceAudioLibrary,
)
from muallim.application.ports.system import BuildInfo, Clock, EventLog, IdGenerator
from muallim.application.use_cases.annotation import (
    AnnotatorAccess,
    JoinAnnotation,
    NextAnnotation,
    RedeemInvite,
    SubmitAnnotation,
)
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.application.use_cases.learners import (
    DeleteMyData,
    EnsureLearner,
    Questionnaire,
    SetFeedbackLanguage,
    SetResearchConsent,
)
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz
from muallim.application.use_cases.reading import HowToRead
from muallim.application.use_cases.recitation import AssessRecitation
from muallim.application.use_cases.reference import GetReferenceAudio, RecordReference
from muallim.application.use_cases.reminders import DueReminders
from muallim.application.use_cases.reports import ReportMistake
from muallim.application.use_cases.review import GetReview
from muallim.application.use_cases.screen import ScreenState
from muallim.application.use_cases.settings import ChangeSetting, GetSettings
from muallim.application.use_cases.staff import StaffAccess
from muallim.application.use_cases.video import GetArticulationVideo, RecordVideoPlayed
from muallim.bootstrap.config import PROJECT_ROOT, Settings
from muallim.domain.curriculum import Curriculum
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.asr.stub import StubRecognizer
from muallim.infrastructure.audio.ffmpeg import trim_silence
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.audio.http import fetch
from muallim.infrastructure.audio.reference_library import (
    CombinedReferenceAudio,
    FileReferenceAudio,
    RecitationCache,
    SoundLibrary,
)
from muallim.infrastructure.curriculum.syllables import SyllableLibrary
from muallim.infrastructure.curriculum.yaml_loader import load_curriculum, load_feedback_catalog
from muallim.infrastructure.db.engine import create_engine, create_session_factory
from muallim.infrastructure.db.repositories.annotation import (
    SqlAnnotationTasks,
    SqlAnnotatorDirectory,
)
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.curriculum import SqlCurriculumSnapshots
from muallim.infrastructure.db.repositories.events import SqlEventLog
from muallim.infrastructure.db.repositories.learners import (
    SqlLearnerProfileRepository,
    SqlLearnerRepository,
)
from muallim.infrastructure.db.repositories.quiz import SqlQuizAnswerRepository
from muallim.infrastructure.db.repositories.reminders import SqlReminderRecipients
from muallim.infrastructure.db.repositories.settings import SqlLearnerSettingsRepository
from muallim.infrastructure.db.uow import SqlUnitOfWork
from muallim.infrastructure.erasures import FileErasureLog
from muallim.infrastructure.system import RandomIdGenerator, SystemClock
from muallim.infrastructure.video.library import VideoLibrary
from muallim.presentation.telegram.display import Display
from muallim.presentation.telegram.learner import LearnerProvider


class AppProvider(Provider):
    """Объекты на всё время работы бота."""

    scope = Scope.APP

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings

    @provide
    def settings_(self) -> Settings:
        return self.settings

    @provide
    def curriculum(self) -> Curriculum:
        d = self.settings.curriculum_dir
        return load_curriculum(d / "course.ru.yaml", d / "lexicon.ru.yaml")

    @provide
    def policy(self) -> GradingPolicy:
        return GradingPolicy(self.settings.pass_threshold, self.settings.excellent_threshold)

    @provide
    def feedback_catalog(self) -> FeedbackCatalog:
        return load_feedback_catalog(self.settings.curriculum_dir)

    @provide
    def reference_audio(self, curriculum: Curriculum) -> ReferenceAudioLibrary:
        ayat = {i.id: i.quran for les in curriculum.lessons for i in les.items if i.quran}
        texts = {i.id: i.text for les in curriculum.lessons for i in les.items if not i.quran}
        return CombinedReferenceAudio(
            FileReferenceAudio(self.settings.reference_audio_dir),
            RecitationCache(
                self.settings.recitations_dir, fetch, self.settings.reciter, trim_silence
            ),
            ayat,
            SoundLibrary.load(self.settings.reference_audio_dir / "library"),
            texts,
        )

    @provide
    def videos(self) -> ArticulationVideoLibrary:
        """Ролики «🎬 Как произносить» (ADR-0074): манифест читается один раз при запуске."""
        return VideoLibrary.load(self.settings.video_dir)

    @provide
    def syllables(self) -> AyahSyllables:
        """Аяты по слогам (ADR-0077): разбор заранее, файл читается один раз при запуске."""
        return SyllableLibrary.load(self.settings.curriculum_dir / "syllables" / "ayat.yaml")

    @provide
    def display(self) -> Display:
        """Кэш экранов Telegram — один на контейнер: у каждого бота (и теста) свой."""
        return Display()

    @provide
    def build_info(self) -> BuildInfo:
        return BuildInfo(self.settings.app_version or detect_version())

    @provide
    def recognizer(self) -> PronunciationRecognizer:
        if self.settings.asr_backend == "stub":
            return StubRecognizer()
        from muallim.infrastructure.asr.muaalem import MuaalemRecognizer  # noqa: PLC0415

        recognizer = MuaalemRecognizer(device=self.settings.asr_device)
        recognizer.load()
        return recognizer

    @provide
    def reading_guide(self) -> ReadingGuide:
        from muallim.infrastructure.asr.reading import QuranReadingGuide  # noqa: PLC0415

        return QuranReadingGuide()

    @provide
    def audio_store(self) -> AudioStore:
        return FileAudioStore(self.settings.audio_dir)

    @provide
    def erasure_log(self, clock: Clock) -> ErasureLog:
        return FileErasureLog(self.settings.erasure_log_path, clock)

    @provide
    async def engine(self) -> AsyncIterator[AsyncEngine]:
        engine = create_engine(self.settings.database_url.get_secret_value())
        yield engine
        await engine.dispose()

    @provide
    def session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return create_session_factory(engine)

    clock = provide(SystemClock, provides=Clock)
    ids = provide(RandomIdGenerator, provides=IdGenerator)


class RequestProvider(Provider):
    """Объекты на один апдейт: одна сессия БД и одна транзакция на запрос."""

    scope = Scope.REQUEST

    @provide
    async def session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    uow = provide(SqlUnitOfWork, provides=UnitOfWork)
    learners = provide(SqlLearnerRepository, provides=LearnerRepository)
    profiles = provide(SqlLearnerProfileRepository, provides=LearnerProfileRepository)
    learner_settings = provide(SqlLearnerSettingsRepository, provides=LearnerSettingsRepository)
    quiz_answers = provide(SqlQuizAnswerRepository, provides=QuizAnswerRepository)
    attempts = provide(SqlAttemptRepository, provides=AttemptRepository)
    reminder_recipients = provide(SqlReminderRecipients, provides=ReminderRecipients)
    events = provide(SqlEventLog, provides=EventLog)
    snapshots = provide(SqlCurriculumSnapshots, provides=CurriculumSnapshots)
    annotator_directory = provide(SqlAnnotatorDirectory, provides=AnnotatorDirectory)
    annotation_tasks = provide(SqlAnnotationTasks, provides=AnnotationTasks)

    @provide
    def annotator_access(
        self, directory: AnnotatorDirectory, settings: Settings
    ) -> AnnotatorAccess:
        return AnnotatorAccess(directory, settings.annotators)

    @provide
    def staff_access(self, settings: Settings, annotators: AnnotatorAccess) -> StaffAccess:
        return StaffAccess(settings.teachers, annotators)

    @provide
    def record_reference(
        self,
        library: ReferenceAudioLibrary,
        settings: Settings,
        uow: UnitOfWork,
        events: EventLog,
    ) -> RecordReference:
        return RecordReference(library, settings.teachers, uow, events)

    @provide
    def progress(
        self,
        curriculum: Curriculum,
        attempts: AttemptRepository,
        policy: GradingPolicy,
        clock: Clock,
        learner_settings: LearnerSettingsRepository,
    ) -> GetProgress:
        """«Сегодня» и серия дней — по местной дате ученика (ADR-0061)."""
        return GetProgress(curriculum, attempts, policy, clock, learner_settings)

    @provide
    def review(
        self,
        curriculum: Curriculum,
        attempts: AttemptRepository,
        policy: GradingPolicy,
        clock: Clock,
        learner_settings: LearnerSettingsRepository,
    ) -> GetReview:
        """«🔁 Повторение» на сегодня — по местной дате ученика (ADR-0062, ADR-0061)."""
        return GetReview(curriculum, attempts, policy, clock, learner_settings)

    @provide
    def quiz(
        self,
        *,
        curriculum: Curriculum,
        attempts: AttemptRepository,
        answers: QuizAnswerRepository,
        library: ReferenceAudioLibrary,
        events: EventLog,
        uow: UnitOfWork,
        clock: Clock,
        ids: IdGenerator,
        learner_settings: LearnerSettingsRepository,
    ) -> PracticeQuiz:
        """«🧠 Закрепление» — по местной дате ученика (ADR-0066, ADR-0061)."""
        return PracticeQuiz(
            curriculum=curriculum, attempts=attempts, answers=answers, audio=library,
            events=events, uow=uow, clock=clock, ids=ids, settings=learner_settings,
        )  # fmt: skip

    use_cases = provide_all(
        EnsureLearner,
        SetResearchConsent,
        Questionnaire,
        SetFeedbackLanguage,
        DeleteMyData,
        OpenItem,
        AssessRecitation,
        HowToRead,
        ScreenState,
        GetSettings,
        ChangeSetting,
        DueReminders,
        GetReferenceAudio,
        GetArticulationVideo,
        RecordVideoPlayed,
        ReportMistake,
        PublishCurriculum,
        RedeemInvite,
        JoinAnnotation,
        NextAnnotation,
        SubmitAnnotation,
    )


def detect_version() -> str:
    """«0.2.0+a1b2c3d» — версия пакета и git-коммит; «-dirty», если есть незакоммиченные правки."""
    try:
        sha = subprocess.run(
            ["git", "describe", "--always", "--dirty", "--exclude", "*"],  # noqa: S607
            cwd=PROJECT_ROOT, capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return __version__
    return f"{__version__}+{sha}" if sha else __version__


def create_container(settings: Settings) -> AsyncContainer:
    return make_async_container(
        AppProvider(settings), RequestProvider(), AiogramProvider(), LearnerProvider()
    )
