# database.py
#
# The storage layer for OrganizePY. Everything the app needs to
# remember between runs lives here, backed by a small TinyDB JSON
# file (config.DATABASE_FILE):
#
#   - categories / subcategories -- the folder rules the user has
#     configured (which extensions/keywords route where)
#   - games -- a cache of "this folder name maps to this IGDB game",
#     so we don't have to hit the IGDB API again for something we've
#     already identified
#   - game_exclusions -- folder names the user has said "never treat
#     this as a game"
#   - folders -- previously-used source folders, for the GUI's
#     folder-picker history
#
# gui.py and organizer.py both import from here rather than touching
# TinyDB directly.

from pathlib import Path

from tinydb import TinyDB, Query

from config import DATABASE_FILE, DEFAULT_CATEGORIES


DATABASE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

db = TinyDB(
    DATABASE_FILE
)

folders = db.table(
    "folders"
)

games = db.table(
    "games"
)

categories = db.table(
    "categories"
)

subcategories = db.table(
    "subcategories"
)

game_exclusions = db.table(
    "game_exclusions"
)


# ============================================================
# NORMALIZATION
#
# Small helpers to keep stored extensions/keywords consistent
# (lowercase, deduplicated, extensions always with a leading dot)
# no matter how they were typed in.
# ============================================================

def normalize_extensions(values):
    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    result = set()

    for value in values:
        value = str(value).strip().lower()

        if not value:
            continue

        if not value.startswith("."):
            value = "." + value

        result.add(value)

    return sorted(result)


def normalize_keywords(values):
    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    result = set()

    for value in values:
        value = str(value).strip().lower()

        if value:
            result.add(value)

    return sorted(result)


# ============================================================
# CATEGORY LOOKUP
# ============================================================

# Flexible lookup: pass a TinyDB document, a dict with a doc_id or
# name, a raw doc_id, or a category name string -- whatever's on
# hand at the call site -- and get back the matching category record.
def get_category(identifier):
    if identifier is None:
        return None

    if hasattr(identifier, "doc_id"):
        return identifier

    if isinstance(identifier, dict):

        if "doc_id" in identifier:
            identifier = identifier["doc_id"]

        elif "name" in identifier:
            identifier = identifier["name"]

        else:
            return None

    try:
        document_id = int(identifier)

        category = categories.get(
            doc_id=document_id
        )

        if category is not None:
            return category

    except (TypeError, ValueError):
        pass

    query = Query()

    return categories.get(
        query.name == str(
            identifier
        ).strip()
    )


def get_all_categories():
    return categories.all()


def get_category_names():
    return [
        category.get(
            "name",
            ""
        )
        for category in categories.all()
        if category.get(
            "name",
            ""
        )
    ]


# ============================================================
# CATEGORY SEEDING
#
# Makes sure the built-in categories from config.DEFAULT_CATEGORIES
# exist in the database and are marked protected, without clobbering
# any customizations (extra keywords, etc.) the user has already
# added to them. Runs once at import time, and again after
# clear_database().
# ============================================================

def seed_default_categories():
    query = Query()

    for name, extensions in DEFAULT_CATEGORIES.items():

        existing = categories.get(
            query.name == name
        )

        if existing is None:

            categories.insert({
                "name": name,
                "extensions": normalize_extensions(
                    extensions
                ),
                "keywords": [],
                "exclusions": [],
                "protected": True
            })

            continue

        changed = False

        if "extensions" not in existing:
            existing["extensions"] = normalize_extensions(
                extensions
            )
            changed = True

        if "keywords" not in existing:
            existing["keywords"] = []
            changed = True

        if "exclusions" not in existing:
            existing["exclusions"] = []
            changed = True

        if not existing.get(
            "protected",
            False
        ):
            existing["protected"] = True
            changed = True

        if changed:

            categories.update(
                existing,
                doc_ids=[
                    existing.doc_id
                ]
            )


# ============================================================
# CATEGORY CRUD
#
# save_category() is the one place that actually writes a category
# record -- add/remove-extension/keyword/exclusion below all just
# build the updated set and hand it back to this function.
# ============================================================

def save_category(
    name,
    extensions=None,
    keywords=None,
    exclusions=None,
    protected=None,
    doc_id=None
):
    name = str(
        name
    ).strip()

    if not name:
        return False

    existing = None

    if doc_id is not None:

        try:
            existing = categories.get(
                doc_id=int(
                    doc_id
                )
            )

        except (
            TypeError,
            ValueError
        ):
            existing = None

    if existing is None:
        existing = get_category(
            name
        )

    # Any field left as None falls back to whatever the existing
    # record already has, so callers can update just one field at a
    # time without having to re-supply everything else.
    if extensions is None:
        extensions = (
            existing.get(
                "extensions",
                []
            )
            if existing
            else []
        )

    if keywords is None:
        keywords = (
            existing.get(
                "keywords",
                []
            )
            if existing
            else []
        )

    if exclusions is None:
        exclusions = (
            existing.get(
                "exclusions",
                []
            )
            if existing
            else []
        )

    if protected is None:
        protected = (
            existing.get(
                "protected",
                False
            )
            if existing
            else False
        )

    # Built-in categories can't lose their protected status, even if
    # a caller tries to pass protected=False.
    if name in DEFAULT_CATEGORIES:
        protected = True

    data = {
        "name": name,
        "extensions": normalize_extensions(
            extensions
        ),
        "keywords": normalize_keywords(
            keywords
        ),
        "exclusions": normalize_keywords(
            exclusions
        ),
        "protected": bool(
            protected
        )
    }

    if existing:

        categories.update(
            data,
            doc_ids=[
                existing.doc_id
            ]
        )

    else:

        categories.insert(
            data
        )

    return True


# Deletes a category and everything nested under it -- refuses to
# touch protected (built-in) categories.
def remove_category(
    name
):
    category = get_category(
        name
    )

    if category is None:
        return False

    if category.get(
        "protected",
        False
    ):
        return False

    remove_all_descendants(
        category.doc_id,
        "category"
    )

    categories.remove(
        doc_ids=[
            category.doc_id
        ]
    )

    return True


# ============================================================
# CATEGORY EXTENSIONS
# ============================================================

def add_extension(
    category_name,
    extension
):
    category = get_category(
        category_name
    )

    if category is None:
        return False

    extension = str(
        extension
    ).strip().lower()

    if not extension:
        return False

    if not extension.startswith("."):
        extension = "." + extension

    extensions = set(
        category.get(
            "extensions",
            []
        )
    )

    extensions.add(
        extension
    )

    return save_category(
        name=category.get(
            "name"
        ),
        extensions=extensions,
        keywords=category.get(
            "keywords",
            []
        ),
        exclusions=category.get(
            "exclusions",
            []
        ),
        protected=category.get(
            "protected",
            False
        ),
        doc_id=category.doc_id
    )


def remove_extension(
    category_name,
    extension
):
    category = get_category(
        category_name
    )

    if category is None:
        return False

    extension = str(
        extension
    ).strip().lower()

    if not extension.startswith("."):
        extension = "." + extension

    extensions = set(
        category.get(
            "extensions",
            []
        )
    )

    extensions.discard(
        extension
    )

    return save_category(
        name=category.get(
            "name"
        ),
        extensions=extensions,
        keywords=category.get(
            "keywords",
            []
        ),
        exclusions=category.get(
            "exclusions",
            []
        ),
        protected=category.get(
            "protected",
            False
        ),
        doc_id=category.doc_id
    )


# ============================================================
# CATEGORY KEYWORDS
# ============================================================

def add_keyword(
    category_name,
    keyword
):
    category = get_category(
        category_name
    )

    if category is None:
        return False

    keyword = str(
        keyword
    ).strip().lower()

    if not keyword:
        return False

    keywords = set(
        category.get(
            "keywords",
            []
        )
    )

    keywords.add(
        keyword
    )

    return save_category(
        name=category.get(
            "name"
        ),
        extensions=category.get(
            "extensions",
            []
        ),
        keywords=keywords,
        exclusions=category.get(
            "exclusions",
            []
        ),
        protected=category.get(
            "protected",
            False
        ),
        doc_id=category.doc_id
    )


def remove_keyword(
    category_name,
    keyword
):
    category = get_category(
        category_name
    )

    if category is None:
        return False

    keyword = str(
        keyword
    ).strip().lower()

    keywords = set(
        category.get(
            "keywords",
            []
        )
    )

    keywords.discard(
        keyword
    )

    return save_category(
        name=category.get(
            "name"
        ),
        extensions=category.get(
            "extensions",
            []
        ),
        keywords=keywords,
        exclusions=category.get(
            "exclusions",
            []
        ),
        protected=category.get(
            "protected",
            False
        ),
        doc_id=category.doc_id
    )


# ============================================================
# CATEGORY EXCLUSIONS
# ============================================================

def add_category_exclusion(
    category_name,
    exclusion
):
    category = get_category(
        category_name
    )

    if category is None:
        return False

    exclusion = str(
        exclusion
    ).strip().lower()

    if not exclusion:
        return False

    exclusions = set(
        category.get(
            "exclusions",
            []
        )
    )

    exclusions.add(
        exclusion
    )

    return save_category(
        name=category.get(
            "name"
        ),
        extensions=category.get(
            "extensions",
            []
        ),
        keywords=category.get(
            "keywords",
            []
        ),
        exclusions=exclusions,
        protected=category.get(
            "protected",
            False
        ),
        doc_id=category.doc_id
    )


def remove_category_exclusion(
    category_name,
    exclusion
):
    category = get_category(
        category_name
    )

    if category is None:
        return False

    exclusion = str(
        exclusion
    ).strip().lower()

    exclusions = set(
        category.get(
            "exclusions",
            []
        )
    )

    exclusions.discard(
        exclusion
    )

    return save_category(
        name=category.get(
            "name"
        ),
        extensions=category.get(
            "extensions",
            []
        ),
        keywords=category.get(
            "keywords",
            []
        ),
        exclusions=exclusions,
        protected=category.get(
            "protected",
            False
        ),
        doc_id=category.doc_id
    )


# ============================================================
# SUBCATEGORY LOOKUP
#
# Subcategories can nest under a category OR under another
# subcategory (see parent_type below), so most of the lookup/CRUD
# functions here take a parent_type alongside a parent_id.
# ============================================================

# Two ways to call this: get_subcategory(doc_id) to fetch by id
# directly, or get_subcategory(category_name, subcategory_name) to
# find a subcategory that's a direct child of a given category.
def get_subcategory(
    identifier,
    subcategory_name=None
):
    if subcategory_name is None:

        try:
            identifier = int(
                identifier
            )
        except (
            TypeError,
            ValueError
        ):
            return None

        return subcategories.get(
            doc_id=identifier
        )

    category = get_category(
        identifier
    )

    if category is None:
        return None

    category_id = str(
        category.doc_id
    )

    target_name = str(
        subcategory_name
    ).strip().lower()

    query = Query()

    matches = subcategories.search(
        (
            query.parent_type == "category"
        )
        & (
            query.parent_id == category_id
        )
    )

    for item in matches:

        if item.get(
            "name",
            ""
        ).strip().lower() == target_name:

            return item

    return None


# ============================================================
# DIRECT CHILDREN
# ============================================================

def get_child_subcategories(
    parent_id,
    parent_type="subcategory"
):
    query = Query()

    parent_id = str(
        parent_id
    )

    return subcategories.search(
        (
            query.parent_id == parent_id
        )
        & (
            query.parent_type == parent_type
        )
    )


def get_subcategories(
    category_name
):
    category = get_category(
        category_name
    )

    if category is None:
        return []

    return get_child_subcategories(
        category.doc_id,
        "category"
    )


def get_subcategory_children(
    subcategory_id
):
    return get_child_subcategories(
        subcategory_id,
        "subcategory"
    )


# ============================================================
# SUBCATEGORY PATH
# ============================================================

# Walk up from a subcategory through its parents until we hit the
# top-level category, building the full path along the way, e.g.
# ["Documents", "College", "INSY"].
def get_subcategory_path(
    subcategory
):
    if subcategory is None:
        return []

    if not hasattr(
        subcategory,
        "get"
    ):
        return []

    path = []

    current = subcategory

    visited = set()

    while current is not None:

        current_id = str(
            current.doc_id
        )

        # Guards against an accidental cycle in the parent chain
        # (shouldn't happen, but better to stop than loop forever).
        if current_id in visited:
            break

        visited.add(
            current_id
        )

        name = current.get(
            "name",
            ""
        ).strip()

        if name:
            path.insert(
                0,
                name
            )

        parent_id = current.get(
            "parent_id"
        )

        parent_type = current.get(
            "parent_type"
        )

        if parent_type == "subcategory":

            if parent_id is None:
                break

            current = get_subcategory(
                parent_id
            )

            continue

        if parent_type == "category":

            category = get_category(
                parent_id
            )

            if category is not None:

                category_name = category.get(
                    "name",
                    ""
                ).strip()

                if category_name:
                    path.insert(
                        0,
                        category_name
                    )

            break

        break

    return path


# ============================================================
# SUBCATEGORY SAVE
# ============================================================

def save_subcategory(
    category_name=None,
    name=None,
    keywords=None,
    exclusions=None,
    parent_id=None,
    parent_type="category",
    doc_id=None
):
    if name is None:
        return False

    name = str(
        name
    ).strip()

    if not name:
        return False

    category_name_value = ""

    # --------------------------------------------------------
    # Direct child of category
    # --------------------------------------------------------

    if parent_type == "category":

        category = None

        if category_name is not None:

            category = get_category(
                category_name
            )

        elif parent_id is not None:

            category = get_category(
                parent_id
            )

        if category is None:
            return False

        parent_id = str(
            category.doc_id
        )

        category_name_value = category.get(
            "name",
            ""
        )

    # --------------------------------------------------------
    # Child of another subcategory
    # --------------------------------------------------------

    elif parent_type == "subcategory":

        if parent_id is None:
            return False

        parent = get_subcategory(
            parent_id
        )

        if parent is None:
            return False

        parent_id = str(
            parent.doc_id
        )

        parent_path = get_subcategory_path(
            parent
        )

        if parent_path:
            category_name_value = parent_path[0]
        else:
            category_name_value = ""

    else:
        return False

    # --------------------------------------------------------
    # Find existing record
    # --------------------------------------------------------

    existing = None

    if doc_id is not None:

        try:

            existing = subcategories.get(
                doc_id=int(
                    doc_id
                )
            )

        except (
            TypeError,
            ValueError
        ):
            existing = None

    if existing is None:

        query = Query()

        matches = subcategories.search(
            (
                query.parent_id
                == str(parent_id)
            )
            & (
                query.parent_type
                == parent_type
            )
            & (
                query.name
                == name
            )
        )

        if matches:
            existing = matches[0]

    # --------------------------------------------------------
    # Preserve rules
    #
    # If the caller didn't pass keywords/exclusions, keep whatever
    # the existing record already had rather than wiping them out.
    # --------------------------------------------------------

    if keywords is None:

        keywords = (
            existing.get(
                "keywords",
                []
            )
            if existing
            else []
        )

    if exclusions is None:

        exclusions = (
            existing.get(
                "exclusions",
                []
            )
            if existing
            else []
        )

    data = {
        "name": name,
        "parent_id": str(
            parent_id
        ),
        "parent_type": parent_type,
        "category": category_name_value,
        "keywords": normalize_keywords(
            keywords
        ),
        "exclusions": normalize_keywords(
            exclusions
        )
    }

    if existing:

        subcategories.update(
            data,
            doc_ids=[
                existing.doc_id
            ]
        )

    else:

        subcategories.insert(
            data
        )

    return True


# ============================================================
# SUBCATEGORY REMOVE
# ============================================================

def remove_subcategory(
    identifier,
    name=None
):
    if name is not None:

        subcategory = get_subcategory(
            identifier,
            name
        )

    else:

        subcategory = get_subcategory(
            identifier
        )

    if subcategory is None:
        return False

    remove_all_descendants(
        subcategory.doc_id,
        "subcategory"
    )

    subcategories.remove(
        doc_ids=[
            subcategory.doc_id
        ]
    )

    return True


# ============================================================
# RECURSIVE DESCENDANTS
# ============================================================

def get_descendants(
    parent_id,
    parent_type="subcategory"
):
    children = get_child_subcategories(
        parent_id,
        parent_type
    )

    result = []

    for child in children:

        result.append(
            child
        )

        result.extend(
            get_descendants(
                child.doc_id,
                "subcategory"
            )
        )

    return result


# Recursively deletes every subcategory nested under parent_id --
# used before removing a category or subcategory so nothing gets
# left behind as an orphan.
def remove_all_descendants(
    parent_id,
    parent_type
):
    children = get_child_subcategories(
        parent_id,
        parent_type
    )

    for child in children:

        remove_all_descendants(
            child.doc_id,
            "subcategory"
        )

        subcategories.remove(
            doc_ids=[
                child.doc_id
            ]
        )


# ============================================================
# SUBCATEGORY KEYWORDS
# ============================================================

def add_subcategory_keyword(
    category_name,
    subcategory_name,
    keyword
):
    subcategory = get_subcategory(
        category_name,
        subcategory_name
    )

    if subcategory is None:
        return False

    keyword = str(
        keyword
    ).strip().lower()

    if not keyword:
        return False

    keywords = set(
        subcategory.get(
            "keywords",
            []
        )
    )

    keywords.add(
        keyword
    )

    return save_subcategory(
        name=subcategory.get(
            "name"
        ),
        parent_id=subcategory.get(
            "parent_id"
        ),
        parent_type=subcategory.get(
            "parent_type"
        ),
        keywords=keywords,
        exclusions=subcategory.get(
            "exclusions",
            []
        ),
        doc_id=subcategory.doc_id
    )


def remove_subcategory_keyword(
    category_name,
    subcategory_name,
    keyword
):
    subcategory = get_subcategory(
        category_name,
        subcategory_name
    )

    if subcategory is None:
        return False

    keyword = str(
        keyword
    ).strip().lower()

    keywords = set(
        subcategory.get(
            "keywords",
            []
        )
    )

    keywords.discard(
        keyword
    )

    return save_subcategory(
        name=subcategory.get(
            "name"
        ),
        parent_id=subcategory.get(
            "parent_id"
        ),
        parent_type=subcategory.get(
            "parent_type"
        ),
        keywords=keywords,
        exclusions=subcategory.get(
            "exclusions",
            []
        ),
        doc_id=subcategory.doc_id
    )


# ============================================================
# SUBCATEGORY EXCLUSIONS
# ============================================================

def add_subcategory_exclusion(
    category_name,
    subcategory_name,
    exclusion
):
    subcategory = get_subcategory(
        category_name,
        subcategory_name
    )

    if subcategory is None:
        return False

    exclusion = str(
        exclusion
    ).strip().lower()

    if not exclusion:
        return False

    exclusions = set(
        subcategory.get(
            "exclusions",
            []
        )
    )

    exclusions.add(
        exclusion
    )

    return save_subcategory(
        name=subcategory.get(
            "name"
        ),
        parent_id=subcategory.get(
            "parent_id"
        ),
        parent_type=subcategory.get(
            "parent_type"
        ),
        keywords=subcategory.get(
            "keywords",
            []
        ),
        exclusions=exclusions,
        doc_id=subcategory.doc_id
    )


def remove_subcategory_exclusion(
    category_name,
    subcategory_name,
    exclusion
):
    subcategory = get_subcategory(
        category_name,
        subcategory_name
    )

    if subcategory is None:
        return False

    exclusion = str(
        exclusion
    ).strip().lower()

    exclusions = set(
        subcategory.get(
            "exclusions",
            []
        )
    )

    exclusions.discard(
        exclusion
    )

    return save_subcategory(
        name=subcategory.get(
            "name"
        ),
        parent_id=subcategory.get(
            "parent_id"
        ),
        parent_type=subcategory.get(
            "parent_type"
        ),
        keywords=subcategory.get(
            "keywords",
            []
        ),
        exclusions=exclusions,
        doc_id=subcategory.doc_id
    )


# ============================================================
# GAME EXCLUSIONS
#
# A flat, app-wide list of keywords -- if a game folder's name
# matches one of these, organizer.py leaves it alone instead of
# trying to identify it as a game.
# ============================================================

def add_game_exclusion(
    exclusion
):
    query = Query()

    exclusion = str(
        exclusion
    ).strip().lower()

    if not exclusion:
        return False

    if not game_exclusions.contains(
        query.keyword == exclusion
    ):

        game_exclusions.insert({
            "keyword": exclusion
        })

    return True


def remove_game_exclusion(
    exclusion
):
    query = Query()

    exclusion = str(
        exclusion
    ).strip().lower()

    game_exclusions.remove(
        query.keyword == exclusion
    )

    return True


def get_game_exclusions():
    return [
        item.get(
            "keyword",
            ""
        )
        for item in game_exclusions.all()
        if item.get(
            "keyword",
            ""
        )
    ]


# ============================================================
# FOLDERS
#
# Just a history of folders the user has previously pointed the app
# at, so the GUI can offer them again without retyping the path.
# ============================================================

def save_folder(
    path
):
    query = Query()

    path = str(
        Path(path).resolve()
    )

    if not folders.contains(
        query.path == path
    ):

        folders.insert({
            "path": path
        })


def get_previous_folders():
    return [
        item.get(
            "path",
            ""
        )
        for item in folders.all()
        if item.get(
            "path",
            ""
        )
    ]


def remove_folder(
    path
):
    query = Query()

    path = str(
        Path(path).resolve()
    )

    folders.remove(
        query.path == path
    )


# ============================================================
# GAMES
#
# Caches "this folder name is this IGDB game" so organizer.py can
# skip a fresh IGDB lookup the next time it sees the same folder.
# ============================================================

def save_game(
    filename,
    game_name,
    igdb_id=None
):
    query = Query()

    data = {
        "filename": filename,
        "game_name": game_name,
        "igdb_id": igdb_id
    }

    if games.contains(
        query.filename == filename
    ):

        games.update(
            data,
            query.filename == filename
        )

    else:

        games.insert(
            data
        )


def get_game(
    filename
):
    query = Query()

    return games.get(
        query.filename == filename
    )


def remove_game(
    filename
):
    query = Query()

    games.remove(
        query.filename == filename
    )


def get_all_games():
    return games.all()


# ============================================================
# HIERARCHY REPAIR
#
# Small self-healing checks that run at startup to patch up
# subcategory records that could have gotten out of sync -- for
# example after a category was renamed, or after data written by an
# older version of the app.
# ============================================================

def repair_subcategory_categories():
    for subcategory in subcategories.all():

        path = get_subcategory_path(
            subcategory
        )

        if not path:
            continue

        root_category = path[0]

        if subcategory.get(
            "category"
        ) == root_category:
            continue

        subcategories.update(
            {
                "category": root_category
            },
            doc_ids=[
                subcategory.doc_id
            ]
        )


def repair_missing_parent_types():
    changed = False

    for subcategory in subcategories.all():

        parent_id = subcategory.get(
            "parent_id"
        )

        parent_type = subcategory.get(
            "parent_type"
        )

        if parent_id is None:
            continue

        if parent_type in {
            "category",
            "subcategory"
        }:
            continue

        old_category = subcategory.get(
            "category"
        )

        category = get_category(
            old_category
        )

        if category is None:
            continue

        subcategories.update(
            {
                "parent_id": str(
                    category.doc_id
                ),
                "parent_type": "category"
            },
            doc_ids=[
                subcategory.doc_id
            ]
        )

        changed = True

    return changed


# ============================================================
# LEGACY MIGRATION
#
# Handles subcategory records saved by an older schema, where a
# subcategory only knew its category by name rather than by a proper
# parent_id/parent_type pair.
# ============================================================

def migrate_subcategories():
    records = subcategories.all()

    for record in records:

        parent_id = record.get(
            "parent_id"
        )

        parent_type = record.get(
            "parent_type"
        )

        if (
            parent_id is not None
            and parent_type in {
                "category",
                "subcategory"
            }
        ):
            continue

        old_category = record.get(
            "category"
        )

        if not old_category:
            continue

        category = get_category(
            old_category
        )

        if category is None:
            continue

        subcategories.update(
            {
                "parent_id": str(
                    category.doc_id
                ),
                "parent_type": "category",
                "category": category.get(
                    "name",
                    old_category
                ),
                "keywords": normalize_keywords(
                    record.get(
                        "keywords",
                        []
                    )
                ),
                "exclusions": normalize_keywords(
                    record.get(
                        "exclusions",
                        []
                    )
                )
            },
            doc_ids=[
                record.doc_id
            ]
        )


# ============================================================
# INITIALIZATION
#
# Runs once, on import: make sure the default categories exist, then
# clean up any subcategory records left in an old or inconsistent
# shape. Order matters -- migration has to happen before the repair
# passes so they're working with parent_id/parent_type already
# filled in.
# ============================================================

seed_default_categories()

migrate_subcategories()

repair_missing_parent_types()

repair_subcategory_categories()


# ============================================================
# CLEAR DATABASE
# ============================================================

def clear_database():
    folders.truncate()

    games.truncate()

    categories.truncate()

    subcategories.truncate()

    game_exclusions.truncate()

    seed_default_categories()
