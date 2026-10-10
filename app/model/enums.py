from enum import Enum


class MeetingSource(str, Enum):
    MANUAL = "manual"
    UPSTREAM = "upstream"
    PERSONAL = "personal"


class EntryStatus(str, Enum):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    FINISHED = "finished"
