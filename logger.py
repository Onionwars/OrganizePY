import logging

from config import DATA_FOLDER, LOG_FILE


DATA_FOLDER.mkdir(
    parents=True,
    exist_ok=True
)


logger = logging.getLogger(
    "DownloadsOrganizer"
)

logger.setLevel(
    logging.INFO
)

logger.propagate = False


# ============================================================
# FILE HANDLER
# ============================================================

if not logger.handlers:
    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8"
    )

    file_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S"
    )

    file_handler.setFormatter(
        file_formatter
    )

    logger.addHandler(
        file_handler
    )


# ============================================================
# GUI HANDLER
# ============================================================

class TkLogHandler(logging.Handler):
    def __init__(
        self,
        callback
    ):
        super().__init__(
            level=logging.INFO
        )

        self.callback = callback

        self.formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(message)s",
            datefmt="%H:%M:%S"
        )

    def emit(
        self,
        record
    ):
        try:
            message = self.format(
                record
            )

            if self.callback:
                self.callback(
                    message + "\n"
                )

        except Exception:
            self.handleError(
                record
            )


_gui_handler = None


def add_gui_log_handler(
    callback
):
    global _gui_handler

    if _gui_handler is not None:
        try:
            logger.removeHandler(
                _gui_handler
            )
        except Exception:
            pass

    _gui_handler = TkLogHandler(
        callback
    )

    logger.addHandler(
        _gui_handler
    )


def remove_gui_log_handler():
    global _gui_handler

    if _gui_handler is None:
        return

    try:
        logger.removeHandler(
            _gui_handler
        )
    except Exception:
        pass

    _gui_handler = None


# ============================================================
# LOAD EXISTING LOG
# ============================================================

def load_existing_log():
    if not LOG_FILE.exists():
        return ""

    try:
        return LOG_FILE.read_text(
            encoding="utf-8",
            errors="replace"
        )

    except OSError as error:
        return (
            f"[LOGGER] Could not read log file: "
            f"{error}\n"
        )


# ============================================================
# CLEAR GUI PREVIEW
# ============================================================

def clear_log_preview():
    return


# ============================================================
# CLEAR LOG FILE
# ============================================================

def clear_log_file():
    try:
        for handler in list(logger.handlers):
            if isinstance(
                handler,
                logging.FileHandler
            ):
                handler.flush()
                handler.close()
                logger.removeHandler(
                    handler
                )

        LOG_FILE.write_text(
            "",
            encoding="utf-8"
        )

        file_handler = logging.FileHandler(
            LOG_FILE,
            encoding="utf-8"
        )

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(message)s",
            datefmt="%H:%M:%S"
        )

        file_handler.setFormatter(
            formatter
        )

        file_handler.setLevel(
            logging.INFO
        )

        logger.addHandler(
            file_handler
        )

    except OSError as error:
        logger.error(
            "Could not clear log file: %s",
            error
        )