from pathlib import Path
import os
import sys

from dotenv import load_dotenv


# ============================================================
# APPLICATION LOCATION
# ============================================================

if getattr(sys, "frozen", False):
    
    APP_DIR = Path(
        sys.executable
    ).resolve().parent

else:
    APP_DIR = Path(
        __file__
    ).resolve().parent

BASE_FOLDER = APP_DIR


# ============================================================
# ENVIRONMENT
# ============================================================

ENV_FILE = APP_DIR / ".env"

load_dotenv(
    ENV_FILE
)


IGDB_CLIENT_ID = os.getenv(
    "IGDB_CLIENT_ID"
)

IGDB_CLIENT_SECRET = os.getenv(
    "IGDB_CLIENT_SECRET"
)


# ============================================================
# DATA DIRECTORY
# ============================================================

DATA_FOLDER = (
    APP_DIR / "data"
)

DATA_FOLDER.mkdir(
    parents=True,
    exist_ok=True,
)


DATABASE_FILE = (
    DATA_FOLDER / "database.json"
)

LOG_FILE = (
    DATA_FOLDER / "organizer.log"
)


# ============================================================
# GAME MATCHING
# ============================================================

IGNORED_GAME_WORDS = {
    "game",
    "games",
    "edition",
    "ultimate",
    "deluxe",
    "goty",
    "complete",
    "collection",
    "remastered",
    "remaster",
    "remake",
    "repack",
    "portable",
    "full",
    "steam",
    "gog",
    "epic",
    "setup",
    "installer",
}


JOINER_WORDS = {
    "and",
    "the",
    "of",
    "for",
    "with",
    "edition",
}


# ============================================================
# DEFAULT CATEGORIES
# ============================================================

DEFAULT_CATEGORIES = {
    "Images": {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
        ".bmp",
        ".tiff",
        ".tif",
        ".ico",
        ".heic",
        ".raw",
    },

    "Videos": {
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".flv",
        ".wmv",
        ".webm",
        ".m4v",
        ".mpeg",
        ".mpg",
        ".3gp",
    },

    "Audio": {
        ".mp3",
        ".wav",
        ".aac",
        ".flac",
        ".ogg",
        ".wma",
        ".m4a",
        ".aiff",
        ".opus",
    },

    "Documents": {
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".odt",
        ".rtf",
        ".tex",
        ".md",
        ".epub",
        ".pages",
    },

    "Spreadsheets": {
        ".xls",
        ".xlsx",
        ".ods",
        ".numbers",
    },

    "Presentations": {
        ".ppt",
        ".pptx",
        ".odp",
        ".key",
    },

    "Code": {
        ".py",
        ".js",
        ".ts",
        ".html",
        ".css",
        ".java",
        ".c",
        ".cpp",
        ".cs",
        ".go",
        ".rs",
        ".php",
        ".rb",
        ".swift",
        ".kt",
        ".sh",
        ".yaml",
        ".yml",
        ".sql",
    },

    "Archives": {
        ".zip",
        ".tar",
        ".gz",
        ".rar",
        ".7z",
        ".bz2",
        ".xz",
        ".iso",
    },

    "Fonts": {
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
    },

    "Executables": {
        ".exe",
        ".msi",
        ".dmg",
        ".pkg",
        ".deb",
        ".rpm",
        ".appimage",
    },

    "Data": {
        ".json",
        ".xml",
        ".csv",
        ".parquet",
        ".sqlite",
        ".db",
        ".hdf5",
        ".feather",
    },

    "Visual Object": {
        ".obj",
        ".fbx",
        ".stl",
        ".blend",
        ".dae",
        ".3ds",
        ".psd",
        ".ai",
        ".sketch",
        ".fig",
    },

    "Other": set(),
}


# ============================================================
# PROTECTED CATEGORIES
# ============================================================

PROTECTED_CATEGORIES = {
    "Images",
    "Videos",
    "Audio",
    "Documents",
    "Spreadsheets",
    "Presentations",
    "Code",
    "Archives",
    "Fonts",
    "Executables",
    "Data",
    "Visual Object",
    "Other",
}


# ============================================================
# RESERVED FOLDER NAMES
# ============================================================

RESERVED_FOLDER_NAMES = {
    "Games",
}