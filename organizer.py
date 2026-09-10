# organizer.py
#
# This is where the actual sorting happens. gui.py calls into
# organize_files() (via organize_downloads() below) to kick off a
# run; everything else in this file exists to answer two questions
# for each item in the folder:
#
#   1. Where should this go? (get_file_destination /
#      get_keyword_destination / organize_game_folder)
#   2. How do I safely move it there without clobbering anything?
#      (move_file_to_destination / move_folder_to_destination /
#      merge_directory_contents)
#
# Category/subcategory rules come from database.py, and game
# identification is handed off to igdb.py.

from pathlib import Path
import shutil
from config import BASE_FOLDER

from logger import logger

from database import (
    get_all_categories,
    get_category,
    get_game,
    save_game,
    get_child_subcategories,
)

from igdb import (
    find_best_igdb_match,
    score_game_match,
)


# ============================================================
# CONSTANTS
# ============================================================

GAMES_FOLDER_NAME = "Games"


# ============================================================
# PATH / NAME HELPERS
# ============================================================

def names_match(first, second):
    """
    Case-insensitive filesystem name comparison.
    """
    return (
        str(first).strip().lower()
        == str(second).strip().lower()
    )


def path_key(path):
    """
    Return a normalized, lowercase, absolute path string so two
    different-looking paths that point at the same file can be
    compared with a plain ==.
    """
    try:
        return str(Path(path).resolve()).lower()
    except OSError:
        return str(Path(path).absolute()).lower()


# ============================================================
# CATEGORY TREE CREATION
#
# Runs before every organize pass so the destination folders already
# exist -- Images, Videos, Games, and all their configured
# subcategories -- even before anything's been moved into them.
# ============================================================

def create_category_tree(current_folder):
    """
    Create all configured category folders and their recursive
    subcategory folders.
    """

    current_folder = Path(current_folder)

    if not current_folder.exists():
        current_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

    categories = get_all_categories()

    for category in categories:
        category_name = category.get("name")

        if not category_name:
            continue

        category_path = (
            current_folder / category_name
        )

        try:
            category_path.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as error:
            logger.error(
                "Could not create category '%s': %s",
                category_name,
                error,
            )
            continue

        category_id = category.doc_id

        create_subcategory_tree(
            category_path,
            category_id,
            "category",
        )


def create_subcategory_tree(
    parent_folder,
    parent_id,
    parent_type="category",
):
    """
    Recursively create subcategory folders under a category (or
    another subcategory), mirroring the nesting stored in the
    database.
    """

    parent_folder = Path(parent_folder)

    try:
        children = get_child_subcategories(
            parent_id,
            parent_type=parent_type,
        )
    except Exception:
        logger.exception(
            "Could not load child subcategories for %s",
            parent_id,
        )
        return

    for child in children:
        child_name = child.get("name")

        if not child_name:
            continue

        child_folder = (
            parent_folder / child_name
        )

        try:
            child_folder.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as error:
            logger.error(
                "Could not create subcategory '%s': %s",
                child_name,
                error,
            )
            continue

        child_id = child.doc_id

        create_subcategory_tree(
            child_folder,
            child_id,
            "subcategory",
        )


# ============================================================
# KEYWORD / EXCLUSION MATCHING
# ============================================================

def keyword_matches(
    name,
    keyword,
):
    """
    Case-insensitive substring match.
    """

    if not name or not keyword:
        return False

    name = str(name).lower()
    keyword = str(keyword).strip().lower()

    if not keyword:
        return False

    return keyword in name


def item_matches_keywords(
    name,
    keywords,
):
    """
    Return True if at least one keyword matches.
    """

    if not keywords:
        return False

    for keyword in keywords:
        if keyword_matches(
            name,
            keyword,
        ):
            return True

    return False


def item_matches_exclusions(
    name,
    exclusions,
):
    """
    Return True if at least one exclusion matches.
    """

    if not exclusions:
        return False

    for exclusion in exclusions:
        if keyword_matches(
            name,
            exclusion,
        ):
            return True

    return False


# ============================================================
# CATEGORY HELPERS
#
# Small accessors that let the rest of this file treat a category
# either as a TinyDB dict or as a plain string, without every caller
# having to check which one it got.
# ============================================================

def get_category_name(category):
    if isinstance(category, dict):
        return category.get("name", "")

    return str(category)


def get_category_extensions(category):
    if not isinstance(category, dict):
        return []

    return category.get(
        "extensions",
        [],
    ) or []


def get_category_keywords(category):
    if not isinstance(category, dict):
        return []

    return category.get(
        "keywords",
        [],
    ) or []


def get_category_exclusions(category):
    if not isinstance(category, dict):
        return []

    return category.get(
        "exclusions",
        [],
    ) or []


# ============================================================
# SUBCATEGORY MATCHING
# ============================================================

def find_best_subcategory_match(
    name,
    category,
):
    """
    Recursively find the deepest matching subcategory under a
    category, so a name matching both a subcategory and one of its
    own nested subcategories ends up at the more specific one.

    Returns:

        (subcategory, path_parts, depth)

    or:

        None
    """

    category_id = category.doc_id

    best_match = None

    def walk(
        parent_id,
        parent_type,
        path_parts,
    ):
        nonlocal best_match

        try:
            children = get_child_subcategories(
                parent_id,
                parent_type=parent_type,
            )
        except Exception:
            logger.exception(
                "Could not load subcategories for parent %s",
                parent_id,
            )
            return

        for child in children:
            child_name = child.get(
                "name",
                "",
            )

            if not child_name:
                continue

            child_keywords = child.get(
                "keywords",
                [],
            ) or []

            child_exclusions = child.get(
                "exclusions",
                [],
            ) or []

            next_path = (
                path_parts
                + [child_name]
            )

            # An exclusion on this node only prevents THIS node
            # from matching -- deeper subcategories nested under
            # it should still be searched.
            excluded_here = item_matches_exclusions(
                name,
                child_exclusions,
            )

            if not excluded_here and item_matches_keywords(
                name,
                child_keywords,
            ):
                depth = len(next_path)

                if (
                    best_match is None
                    or depth > best_match[2]
                ):
                    best_match = (
                        child,
                        next_path,
                        depth,
                    )

            child_id = child.doc_id

            walk(
                child_id,
                "subcategory",
                next_path,
            )

    walk(
        category_id,
        "category",
        [],
    )

    return best_match


def get_keyword_destination(
    name,
    current_folder=None,
):
    """
    Find the deepest configured keyword destination for a name,
    checking subcategories first and only falling back to a
    top-level category match if nothing more specific fits.

    Returns:

        ["Documents", "College", "INSY"]

    or:

        ["Documents"]

    or:

        None
    """

    categories = get_all_categories()

    best_destination = None
    best_depth = -1

    for category in categories:
        category_name = get_category_name(
            category
        )

        if not category_name:
            continue

        category_exclusions = (
            get_category_exclusions(
                category
            )
        )

        if item_matches_exclusions(
            name,
            category_exclusions,
        ):
            continue

        result = find_best_subcategory_match(
            name,
            category,
        )

        if result:
            _, path_parts, depth = result

            if depth > best_depth:
                best_depth = depth
                best_destination = (
                    [category_name]
                    + path_parts
                )

    # Only after checking every subcategory do we fall back to a
    # plain category-level keyword -- a deep subcategory match
    # always wins over this.
    for category in categories:
        category_name = get_category_name(
            category
        )

        if not category_name:
            continue

        if item_matches_exclusions(
            name,
            get_category_exclusions(
                category
            ),
        ):
            continue

        if item_matches_keywords(
            name,
            get_category_keywords(
                category
            ),
        ):
            category_depth = 0

            if category_depth > best_depth:
                best_depth = category_depth
                best_destination = [
                    category_name
                ]

    return best_destination


# ============================================================
# EXTENSION MATCHING
# ============================================================

def extension_matches(
    suffix,
    extensions,
):
    """
    Case-insensitive extension comparison.
    """

    if not suffix:
        return False

    suffix = suffix.lower()

    for extension in extensions or []:
        extension = str(
            extension
        ).strip().lower()

        if not extension:
            continue

        if not extension.startswith("."):
            extension = "." + extension

        if suffix == extension:
            return True

    return False


def get_extension_destination(
    file_path,
):
    """
    Return the category matching a file's extension, if any.
    """

    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if not suffix:
        return None

    for category in get_all_categories():
        category_name = get_category_name(
            category
        )

        if not category_name:
            continue

        if extension_matches(
            suffix,
            get_category_extensions(
                category
            ),
        ):
            return [category_name]

    return None


# ============================================================
# FILE DESTINATION
# ============================================================

def get_file_destination(
    file_path,
    current_folder=None,
):
    """
    Determine the destination for a file.

    Priority:

        1. Deepest subcategory keyword
        2. Category keyword
        3. Extension
        4. Other
    """

    file_path = Path(file_path)

    # Keyword matching first -- an explicit rule always beats
    # falling back to the extension.
    keyword_destination = (
        get_keyword_destination(
            file_path.name,
            current_folder,
        )
    )

    if keyword_destination:
        return keyword_destination

    # Extension matching second.
    extension_destination = (
        get_extension_destination(
            file_path,
        )
    )

    if extension_destination:
        return extension_destination

    # Nothing matched -- dump it in "Other" rather than leaving it
    # where it is.
    return ["Other"]


# ============================================================
# GAME EXCLUSIONS
# ============================================================

def game_is_excluded(
    folder_name,
):
    """
    Check whether a folder name is on the user's global "don't treat
    this as a game" list.
    """

    try:
        from database import get_game_exclusions

        exclusions = (
            get_game_exclusions()
            or []
        )

    except Exception:
        logger.exception(
            "Could not load game exclusions."
        )
        return False

    return item_matches_exclusions(
        folder_name,
        exclusions,
    )


# ============================================================
# FOLDER MOVE HELPERS
# ============================================================

def _destination_path_for_folder(
    source,
    destination,
):
    """
    Determine the final folder path while preserving the ORIGINAL
    source folder name.
    """

    source = Path(source)
    destination = Path(destination)

    # Important protection:
    #
    # If source is:
    #
    #   Downloads\ReadyorNot
    #
    # and destination is:
    #
    #   Downloads\Games\ReadyorNot
    #
    # preserve the exact original name.
    return destination / source.name


def merge_directory_contents(
    source,
    destination,
):
    """
    Merge a source directory's contents into an already-existing
    destination directory, one item at a time.

    Existing files are never overwritten.
    """

    source = Path(source)
    destination = Path(destination)

    try:
        destination.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as error:
        logger.error(
            "Could not create merge destination '%s': %s",
            destination,
            error,
        )
        return False

    try:
        items = list(
            source.iterdir()
        )
    except OSError as error:
        logger.error(
            "Could not read source directory '%s': %s",
            source,
            error,
        )
        return False

    for item in items:
        target = destination / item.name

        # ----------------------------------------------------
        # Directory
        # ----------------------------------------------------

        if item.is_dir():

            if target.exists():

                if target.is_dir():
                    # Same subfolder exists on both sides --
                    # recurse and merge those too.
                    merge_directory_contents(
                        item,
                        target,
                    )

                else:
                    logger.warning(
                        "Destination contains file with same name: %s",
                        target,
                    )

            else:

                try:
                    shutil.move(
                        str(item),
                        str(target),
                    )
                except PermissionError as error:
                    logger.error(
                        "Access denied moving folder '%s': %s",
                        item,
                        error,
                    )
                except OSError as error:
                    logger.error(
                        "Could not move folder '%s': %s",
                        item,
                        error,
                    )

            continue

        # ----------------------------------------------------
        # File
        # ----------------------------------------------------

        if target.exists():
            logger.warning(
                "Destination already contains: %s",
                target,
            )
            continue

        try:
            shutil.move(
                str(item),
                str(target),
            )
        except PermissionError as error:
            logger.error(
                "Access denied moving file '%s': %s",
                item,
                error,
            )
        except OSError as error:
            logger.error(
                "Could not move file '%s': %s",
                item,
                error,
            )

    # Clean up the now-hopefully-empty source folder. If anything
    # was left behind (conflicts we skipped above), rmdir just fails
    # quietly and the folder stays put.
    try:
        source.rmdir()
    except OSError:
        pass

    return True


def move_folder_to_destination(
    folder,
    current_folder,
    destination_parts,
):
    """
    Move a directory to a category/subcategory destination.

    The original folder name is ALWAYS preserved.
    """

    folder = Path(folder)
    current_folder = Path(current_folder)

    destination = current_folder

    for part in destination_parts:
        destination /= part

    try:
        destination.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as error:
        logger.error(
            "Could not create destination '%s': %s",
            destination,
            error,
        )
        return False

    target = _destination_path_for_folder(
        folder,
        destination,
    )

    # Already there -- nothing to do.
    if path_key(target) == path_key(folder):
        return True

    # Safety net: never move a folder into a path that's inside
    # itself.
    try:
        target.relative_to(folder)

        logger.error(
            "Refusing to move folder into itself: %s -> %s",
            folder,
            target,
        )

        return False

    except ValueError:
        pass

    # --------------------------------------------------------
    # Existing target -> merge.
    # --------------------------------------------------------

    if target.exists():

        if not target.is_dir():
            logger.warning(
                "Destination is not a directory: %s",
                target,
            )
            return False

        logger.warning(
            "Folder already exists, merging: %s",
            target,
        )

        return merge_directory_contents(
            folder,
            target,
        )

    # --------------------------------------------------------
    # Normal move.
    # --------------------------------------------------------

    try:
        shutil.move(
            str(folder),
            str(target),
        )

        logger.info(
            "Moved folder: %s -> %s",
            folder,
            target,
        )

        return True

    except PermissionError as error:
        logger.error(
            "Access denied moving folder: %s -> %s: %s",
            folder,
            target,
            error,
        )
        return False

    except OSError as error:
        logger.error(
            "Could not move folder: %s -> %s: %s",
            folder,
            target,
            error,
        )
        return False


# ============================================================
# FILE MOVE
# ============================================================

def move_file_to_destination(
    file_path,
    current_folder,
    destination_parts,
):
    """
    Move a file to its destination without overwriting anything
    already there.
    """

    file_path = Path(file_path)
    current_folder = Path(current_folder)

    destination = current_folder

    for part in destination_parts:
        destination /= part

    try:
        destination.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as error:
        logger.error(
            "Could not create file destination '%s': %s",
            destination,
            error,
        )
        return False

    target = (
        destination / file_path.name
    )

    # Already there -- nothing to do.
    if path_key(target) == path_key(file_path):
        return True

    # Don't overwrite an existing file with the same name.
    if target.exists():
        logger.warning(
            "Destination already contains: %s",
            target,
        )
        return False

    try:
        shutil.move(
            str(file_path),
            str(target),
        )

        logger.info(
            "Moved file: %s -> %s",
            file_path,
            target,
        )

        return True

    except PermissionError as error:
        logger.error(
            "Access denied moving file: %s -> %s: %s",
            file_path,
            target,
            error,
        )
        return False

    except OSError as error:
        logger.error(
            "Could not move file: %s -> %s: %s",
            file_path,
            target,
            error,
        )
        return False


# ============================================================
# GAME FOLDER ORGANIZATION
#
# Decides what to do with a single top-level directory: skip it if
# it's excluded, honor an explicit keyword rule if there is one,
# trust a previously-cached IGDB match if it still looks right, or
# fall back to a fresh IGDB search. This is the function
# organize_downloads() calls for every folder it finds.
# ============================================================

def organize_game_folder(
    folder,
    current_folder,
):

    folder = Path(folder)
    current_folder = Path(current_folder)

    original_folder_name = folder.name

    # --------------------------------------------------------
    # Game exclusion
    # --------------------------------------------------------

    if game_is_excluded(
        original_folder_name
    ):
        logger.info(
            "Game excluded: %s",
            original_folder_name,
        )
        return False

    # --------------------------------------------------------
    # Explicit keyword destination
    #
    # If the user has set up a keyword/subcategory rule that matches
    # this folder name, that always wins over game detection.
    # --------------------------------------------------------

    keyword_path = get_keyword_destination(
        original_folder_name,
        current_folder,
    )

    if keyword_path:
        logger.info(
            "Game folder matched nested rule: %s -> %s",
            original_folder_name,
            "\\".join(keyword_path),
        )

        return move_folder_to_destination(
            folder,
            current_folder,
            keyword_path,
        )

    # --------------------------------------------------------
    # Cached game
    #
    # We've seen this exact folder name before and already resolved
    # it to a game -- re-validate the cached match's score rather
    # than trusting it blindly, in case the scoring rules have
    # changed since it was cached.
    # --------------------------------------------------------

    cached = None

    try:
        cached = get_game(
            original_folder_name
        )
    except Exception:
        logger.exception(
            "Could not load cached game: %s",
            original_folder_name,
        )

    if cached:

        cached_name = cached.get(
            "game_name",
            "",
        )

        cached_score = 0

        if cached_name:

            try:
                cached_score = score_game_match(
                    original_folder_name,
                    {
                        "name": cached_name,
                    },
                )
            except Exception:
                logger.exception(
                    "Could not validate cached game: %s",
                    original_folder_name,
                )

        # ----------------------------------------------------
        # Only accept a strong cached match.
        # ----------------------------------------------------

        if (
            cached_name
            and cached_score >= 70
        ):

            logger.info(
                "Known game validated: %s -> %s (score %s)",
                original_folder_name,
                cached_name,
                cached_score,
            )

            return move_folder_to_destination(
                folder,
                current_folder,
                [GAMES_FOLDER_NAME],
            )

        logger.warning(
            "Ignoring stale cached game: %s -> %s (score %s)",
            original_folder_name,
            cached_name,
            cached_score,
        )

    # --------------------------------------------------------
    # Fresh IGDB search
    # --------------------------------------------------------

    match = None

    try:
        match = find_best_igdb_match(
            original_folder_name,
            minimum_score=70,
        )

    except TypeError:
        # Fallback for an older/simpler igdb.py that only accepts
        # the game name and doesn't know about minimum_score.
        try:
            match = find_best_igdb_match(
                original_folder_name
            )
        except Exception:
            logger.exception(
                "IGDB matching failed for '%s'",
                original_folder_name,
            )

    except Exception:
        logger.exception(
            "IGDB matching failed for '%s'",
            original_folder_name,
        )

    # --------------------------------------------------------
    # Valid game found
    # --------------------------------------------------------

    if match:

        game_name = match.get(
            "name",
            original_folder_name,
        )

        igdb_id = match.get(
            "id",
        )

        try:
            save_game(
                original_folder_name,
                game_name,
                igdb_id,
            )
        except TypeError:
            # Same idea as above -- tolerate a save_game() that
            # doesn't accept an igdb_id argument.
            try:
                save_game(
                    original_folder_name,
                    game_name,
                )
            except Exception:
                logger.exception(
                    "Could not save game cache: %s",
                    original_folder_name,
                )

        except Exception:
            logger.exception(
                "Could not save game cache: %s",
                original_folder_name,
            )

        logger.info(
            "IGDB game detected: %s -> Games",
            game_name,
        )

        return move_folder_to_destination(
            folder,
            current_folder,
            [GAMES_FOLDER_NAME],
        )

    # --------------------------------------------------------
    # Not a game
    # --------------------------------------------------------

    logger.info(
        "Folder not identified as game: %s",
        original_folder_name,
    )

    return False


# ============================================================
# FILE ORGANIZATION
# ============================================================

def organize_file(
    file_path,
    current_folder,
):
    """
    Work out where a single file belongs and move it there.
    """

    file_path = Path(file_path)

    destination = get_file_destination(
        file_path,
        current_folder,
    )

    if not destination:
        destination = ["Other"]

    return move_file_to_destination(
        file_path,
        current_folder,
        destination,
    )


# ============================================================
# PROTECTED DIRECTORIES
# ============================================================

def is_protected_directory(
    folder,
    current_folder,
):
    """
    Don't treat one of our own destination folders (Games, Images,
    Documents, ...) as source material to be organized -- only
    direct children of the root folder are ever protected this way.
    """

    folder = Path(folder)
    current_folder = Path(current_folder)

    # Only protect direct children of the root.
    if path_key(folder.parent) != path_key(
        current_folder
    ):
        return False

    protected_names = {
        GAMES_FOLDER_NAME.lower(),
    }

    for category in get_all_categories():
        name = get_category_name(
            category
        )

        if name:
            protected_names.add(
                name.lower()
            )

    return (
        folder.name.lower()
        in protected_names
    )


# ============================================================
# MAIN ORGANIZER
#
# The actual entry point: builds the destination tree, then makes
# two passes over the folder's contents -- directories first (since
# some of them might be games), then files, using a fresh directory
# listing for the file pass in case any folders were just moved out
# from under us.
# ============================================================

def organize_downloads(
    current_folder,
):

    current_folder = Path(
        current_folder
    )

    if not current_folder.exists():
        logger.error(
            "Folder does not exist: %s",
            current_folder,
        )
        return False

    if not current_folder.is_dir():
        logger.error(
            "Path is not a directory: %s",
            current_folder,
        )
        return False

    logger.info(
        "Starting organization: %s",
        current_folder,
    )

    # --------------------------------------------------------
    # Pre-create destination tree.
    # --------------------------------------------------------

    try:
        create_category_tree(
            current_folder
        )
    except Exception:
        logger.exception(
            "Could not create category tree."
        )

    # --------------------------------------------------------
    # Read current contents.
    # --------------------------------------------------------

    try:
        entries = list(
            current_folder.iterdir()
        )
    except OSError as error:
        logger.error(
            "Could not read folder '%s': %s",
            current_folder,
            error,
        )
        return False

    # --------------------------------------------------------
    # Process directories first.
    # --------------------------------------------------------

    for entry in entries:

        if not entry.is_dir():
            continue

        if is_protected_directory(
            entry,
            current_folder,
        ):
            continue

        try:
            organize_game_folder(
                entry,
                current_folder,
            )

        except Exception:
            logger.exception(
                "Unexpected error processing folder: %s",
                entry,
            )

    # --------------------------------------------------------
    # Refresh root contents because some directories may
    # have been moved.
    # --------------------------------------------------------

    try:
        entries = list(
            current_folder.iterdir()
        )
    except OSError:
        entries = []

    # --------------------------------------------------------
    # Process files.
    # --------------------------------------------------------

    for entry in entries:

        if not entry.is_file():
            continue

        try:
            organize_file(
                entry,
                current_folder,
            )

        except Exception:
            logger.exception(
                "Unexpected error processing file: %s",
                entry,
            )

    logger.info(
        "Organization complete: %s",
        current_folder,
    )

    return True


# ============================================================
# GUI COMPATIBILITY FUNCTION
# ============================================================

def organize_files(
    current_folder,
):
    """
    Compatibility function used by gui.py.

    gui.py currently imports:

        from organizer import organize_files
    """

    return organize_downloads(
        current_folder
    )


# ============================================================
# ADDITIONAL COMPATIBILITY ALIASES
#
# A couple of alternate names for the same entry point, kept around
# in case another part of the app (or an older build) calls the
# organizer under a different name.
# ============================================================

def organize_folder(
    current_folder,
):
    """
    Compatibility wrapper.
    """

    return organize_downloads(
        current_folder
    )


def organize(
    current_folder,
):
    """
    Compatibility wrapper.
    """

    return organize_downloads(
        current_folder
    )
