"""All repositories of the app, created from one open database."""

from dataclasses import dataclass

from database.classes import ClassRepository
from database.connection import EncryptedDatabase
from database.events import EventRepository
from database.photos import PhotoStore
from database.reports import ReportRepository
from database.settings import AppSettings
from database.students import StudentRepository

PHOTOS_DIR = "photos"


@dataclass(frozen=True)
class Repositories:
    classes: ClassRepository
    students: StudentRepository
    events: EventRepository
    settings: AppSettings
    reports: ReportRepository

    @classmethod
    def from_database(cls, database: EncryptedDatabase) -> "Repositories":
        photos = PhotoStore(database.path.parent / PHOTOS_DIR, database)
        return cls(
            classes=ClassRepository(database),
            students=StudentRepository(database),
            events=EventRepository(database, photos),
            settings=AppSettings(database),
            reports=ReportRepository(database),
        )
