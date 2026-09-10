# igdb.py
#
# This is OrganizePY's link to IGDB (the Internet Game Database). It
# does two jobs:
#
#   1. Talk to IGDB's API -- get an OAuth token, search for games,
#      look one up by id.
#   2. Decide whether a messy download-folder name ("ReadyorNot",
#      "AgeofHistoryIII") actually refers to a real game, and if so,
#      how confident we are about that.
#
# organizer.py is the caller: when it finds a folder it can't place by
# keyword or extension, it asks find_best_igdb_match() here, and if
# that comes back with something, the folder gets moved into the
# Games folder.

import re
import time
import unicodedata

import requests

from config import (
    IGDB_CLIENT_ID,
    IGDB_CLIENT_SECRET,
    IGNORED_GAME_WORDS,
)


# ============================================================
# IGDB CONFIGURATION
# ============================================================

IGDB_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_API_URL = "https://api.igdb.com/v4"

_igdb_token = None
_igdb_token_expires_at = 0


# ============================================================
# ROMAN NUMERALS
#
# Game sequels love Roman numerals ("Age of History III", "Europa
# Universalis V"), so being able to convert those to plain digits
# helps line up a folder name with IGDB's title.
# ============================================================

ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}


def roman_to_int(value):
    """
    Convert a Roman numeral to an integer.

    Examples:
        I   -> 1
        III -> 3
        IV  -> 4
        V   -> 5
        IX  -> 9
        X   -> 10
    """

    if not value:
        return None

    value = value.upper().strip()

    if not value:
        return None

    if any(char not in ROMAN_VALUES for char in value):
        return None

    total = 0
    previous = 0

    for char in reversed(value):
        current = ROMAN_VALUES[char]

        if current < previous:
            total -= current
        else:
            total += current

        previous = current

    # Reject suspiciously long Roman strings -- past this length
    # it's almost certainly not really a numeral (and computing a
    # "value" for it isn't meaningful).
    if len(value) > 7:
        return None

    return total


# ============================================================
# BASIC TEXT CLEANING
# ============================================================

def remove_accents(value):
    """
    Remove accents/diacritics from text.
    """

    if not value:
        return ""

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    return "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )


def clean_release_tags(value):
    """
    Strip the release-scene noise that shows up in pirated/repacked
    game folder names -- group tags, resolution, codec, etc.

    This is deliberately conservative because movie folders can
    otherwise accidentally become game candidates.

    Examples:
        GameName (CODEX)
        GameName [FitGirl]
        GameName 1080p
        GameName x64
    """

    if not value:
        return ""

    # Drop anything in square brackets -- usually a release group tag.
    value = re.sub(
        r"\[[^\]]*\]",
        " ",
        value,
    )

    # Drop parenthesized release info (year, quality, scene group...).
    value = re.sub(
        r"\((?:"
        r"19|20"
        r"\d{2}"
        r"|1080p"
        r"|720p"
        r"|2160p"
        r"|4k"
        r"|bluray"
        r"|brrip"
        r"|web-dl"
        r"|webrip"
        r"|hdr"
        r"|x264"
        r"|x265"
        r"|hevc"
        r"|repack"
        r"|fitgirl"
        r"|codex"
        r"|rune"
        r"|hoodlum"
        r"|skidrow"
        r")"
        r"[^\)]*"
        r"\)",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    # Drop the same kind of tags when they show up bare, with no
    # brackets around them at all.
    value = re.sub(
        r"\b(?:"
        r"1080p|720p|2160p|4320p|4k|"
        r"bluray|brrip|webrip|web-dl|webdl|"
        r"x264|x265|h264|h265|hevc|"
        r"hdr|remux|proper|repack|"
        r"multi|dubbed|subbed"
        r")\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    return value


# ============================================================
# GAME NAME NORMALIZATION
# ============================================================

def normalize_game_name(name):
    """
    Aggressively normalize a game/folder name so it can be compared
    against an IGDB title on a level playing field.

    Handles:

        AgeofHistoryIII
        -> age history 3

        ArmaReforger
        -> arma reforger

        BanquetforFools
        -> banquet for fools

        ReadyorNot
        -> ready or not

        EuropaUniversalisV
        -> europa universalis 5

        Black.Myth.Wukong
        -> black myth wukong

        Cast.n.Chill
        -> cast n chill
    """

    if not name:
        return ""

    name = str(name)

    # Strip accents so "Pokémon" and "Pokemon" line up.
    name = remove_accents(name)

    # Peel off obvious scene/release junk first.
    name = clean_release_tags(name)

    # Dots, dashes and underscores are really just spaces here.
    name = re.sub(
        r"[_\-.]+",
        " ",
        name,
    )

    # Apostrophes just get dropped rather than turned into spaces.
    name = name.replace("'", "")

    # Split camelCase / PascalCase names back into separate words.
    #
    # Example:
    #
    # ReadyorNot
    #   Ready or Not
    #
    # ArmaReforger
    #   Arma Reforger
    #
    # BanquetforFools
    #   Banquet for Fools
    #
    name = re.sub(
        r"(?<=[a-z])(?=[A-Z])",
        " ",
        name,
    )

    # Also split where an acronym runs straight into a normal word.
    #
    # Example:
    #
    # IDSoftware
    # -> ID Software
    #
    name = re.sub(
        r"(?<=[A-Z])(?=[A-Z][a-z])",
        " ",
        name,
    )

    # Put a space between letters and digits that are jammed
    # together in either direction.

    # AgeofHistory3
    # -> AgeofHistory 3
    name = re.sub(
        r"(?<=[A-Za-z])(?=\d)",
        " ",
        name,
    )

    # 3DMark
    # -> 3 DMark
    name = re.sub(
        r"(?<=\d)(?=[A-Za-z])",
        " ",
        name,
    )

    # Spell out ampersands rather than dropping them.
    name = name.replace(
        "&",
        " and ",
    )

    # Collapse any run of whitespace we've created down to one space.
    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    if not name:
        return ""

    words = name.split()

    converted_words = []

    for word in words:
        clean_word = word.strip()

        if not clean_word:
            continue

        roman = roman_to_int(clean_word)

        # Only convert something that plausibly IS a standalone
        # Roman numeral in a sequel title.
        #
        # III  -> 3
        # IV   -> 4
        # V    -> 5
        # VI   -> 6
        #
        # We don't want ordinary words that happen to be made of
        # I/V/X/L/C/D/M turning into numbers.
        if (
            roman is not None
            and 1 <= roman <= 50
            and len(clean_word) <= 7
        ):
            converted_words.append(
                str(roman)
            )
        else:
            converted_words.append(
                clean_word
            )

    name = " ".join(converted_words)

    # Drop generic words ("edition", "goty", "repack"...) that don't
    # actually help identify which game this is.
    ignored_pattern = r"\b(?:" + "|".join(
        re.escape(word)
        for word in sorted(
            IGNORED_GAME_WORDS,
            key=len,
            reverse=True,
        )
    ) + r")\b"

    name = re.sub(
        ignored_pattern,
        " ",
        name,
        flags=re.IGNORECASE,
    )

    # Anything that isn't a letter or digit at this point is noise.
    name = re.sub(
        r"[^A-Za-z0-9]+",
        " ",
        name,
    )

    # Final whitespace cleanup and lowercase for comparison.
    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip().lower()

    return name


# ============================================================
# COMPOUND / COMPRESSED GAME NAMES
# ============================================================

def split_compound_words(name):
    """
    Return normalized words from a compressed/camel-case game name.

    Examples:

        ReadyorNot
        -> ['ready', 'or', 'not']

        AgeofHistoryIII
        -> ['age', 'of', 'history', '3']

        BanquetforFools
        -> ['banquet', 'for', 'fools']

        ArmaReforger
        -> ['arma', 'reforger']
    """

    normalized = normalize_game_name(name)

    if not normalized:
        return []

    return normalized.split()


# ============================================================
# GAME TOKENS
# ============================================================

def game_tokens(name):
    """
    Turn a name into the list of words we'll actually compare on --
    normalized, split apart, generic filler words removed, and any
    leftover Roman numerals converted to digits.
    """

    tokens = split_compound_words(name)

    result = []

    for token in tokens:
        token = token.lower().strip()

        if not token:
            continue

        # Skip generic words like "edition" or "remastered".
        if token in IGNORED_GAME_WORDS:
            continue

        # Convert any Roman numeral that slipped through.
        roman = roman_to_int(token)

        if (
            roman is not None
            and 1 <= roman <= 50
            and len(token) <= 7
        ):
            token = str(roman)

        result.append(token)

    return result


# ============================================================
# TOKEN VARIANTS
# ============================================================

def compact_token(token):
    """
    Remove all non-alphanumeric characters.

    Used for:
        spider-man -> spiderman
        half-life  -> halflife
    """

    if not token:
        return ""

    return re.sub(
        r"[^a-z0-9]",
        "",
        token.lower(),
    )


def token_matches(target_token, source_token):
    """
    Determine whether two individual tokens are equivalent, once
    punctuation differences are ignored.
    """

    target = compact_token(target_token)
    source = compact_token(source_token)

    if not target or not source:
        return False

    if target == source:
        return True

    return False


# ============================================================
# IGDB AUTHENTICATION
# ============================================================

def get_access_token():
    """
    Get an IGDB access token, reusing the cached one if it's still
    good for at least another minute.
    """

    global _igdb_token
    global _igdb_token_expires_at

    if (
        _igdb_token
        and time.time()
        < _igdb_token_expires_at - 60
    ):
        return _igdb_token

    if not IGDB_CLIENT_ID:
        raise RuntimeError(
            "IGDB_CLIENT_ID is not configured."
        )

    if not IGDB_CLIENT_SECRET:
        raise RuntimeError(
            "IGDB_CLIENT_SECRET is not configured."
        )

    response = requests.post(
        IGDB_TOKEN_URL,
        data={
            "client_id": IGDB_CLIENT_ID,
            "client_secret": IGDB_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    _igdb_token = data.get(
        "access_token"
    )

    expires_in = data.get(
        "expires_in",
        3600,
    )

    _igdb_token_expires_at = (
        time.time() + expires_in
    )

    if not _igdb_token:
        raise RuntimeError(
            "IGDB did not return an access token."
        )

    return _igdb_token


# ============================================================
# IGDB REQUEST HELPER
# ============================================================

def _igdb_request(
    endpoint,
    body,
):
    """
    Send one authenticated POST request to an IGDB endpoint and
    return the parsed JSON response.
    """

    token = get_access_token()

    headers = {
        "Client-ID": IGDB_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain",
    }

    response = requests.post(
        f"{IGDB_API_URL}/{endpoint}",
        headers=headers,
        data=body,
        timeout=20,
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# IGDB SEARCH
# ============================================================

def search_igdb(query):
    """
    Search IGDB for a game name.

    Returns:
        list[dict]
    """

    if not query:
        return []

    query = str(query).strip()

    if not query:
        return []

    escaped_query = query.replace(
        '"',
        '\\"'
    )

    body = (
        f'search "{escaped_query}";'
        "fields "
        "id,"
        "name,"
        "alternative_names,"
        "version_title,"
        "summary,"
        "first_release_date;"
        "limit 20;"
    )

    return _igdb_request(
        "games",
        body,
    )


# ============================================================
# GET GAME BY ID
# ============================================================

def get_game_by_id(game_id):
    """
    Fetch one game from IGDB by its numeric id.
    """

    if game_id is None:
        return None

    try:
        game_id = int(game_id)
    except (
        TypeError,
        ValueError,
    ):
        return None

    body = (
        f"where id = {game_id};"
        "fields "
        "id,"
        "name,"
        "alternative_names,"
        "version_title,"
        "summary,"
        "first_release_date;"
        "limit 1;"
    )

    games = _igdb_request(
        "games",
        body,
    )

    if not games:
        return None

    return games[0]


# ============================================================
# TOKEN MATCHING
# ============================================================

def all_tokens_match(
    target_tokens,
    source_tokens,
):
    """
    Require every meaningful folder token to show up somewhere in the
    candidate game's title tokens.

    This prevents:

        Organize
        -> Organize My Shop

        Module
        -> Module: Whatever

        PROG
        -> unrelated game containing prog

    from being accepted.
    """

    if not target_tokens:
        return False

    if not source_tokens:
        return False

    source_set = {
        compact_token(token)
        for token in source_tokens
    }

    for target_token in target_tokens:
        compact_target = compact_token(
            target_token
        )

        if not compact_target:
            continue

        if compact_target in source_set:
            continue

        return False

    return True


# ============================================================
# LONGEST COMMON SUBSEQUENCE
# ============================================================

def longest_common_sequence(
    first,
    second,
):
    """
    Length of the longest sequence of tokens that appears, in order,
    in both lists. Used to reward candidates whose words are in the
    same order as the folder name, not just the same words.
    """

    if not first or not second:
        return 0

    dp = [
        0
        for _ in range(len(second) + 1)
    ]

    for item in first:
        previous = 0

        for index, other in enumerate(
            second,
            start=1,
        ):
            current = dp[index]

            if token_matches(
                item,
                other,
            ):
                dp[index] = (
                    previous + 1
                )
            else:
                dp[index] = max(
                    dp[index],
                    dp[index - 1],
                )

            previous = current

    return dp[-1]


# ============================================================
# GAME MATCH SCORE
# ============================================================

def score_game_match(
    folder_name,
    game,
):
    """
    Score how confident we are that `game` is what `folder_name`
    actually refers to, from 0 (no) to 100 (certain).

    High confidence examples:

        ReadyorNot
        -> Ready or Not

        AgeofHistoryIII
        -> Age of History 3

        EuropaUniversalisV
        -> Europa Universalis 5

    Deliberately rejects weak one-word matches -- a folder called
    "Organize" shouldn't confidently match some unrelated game that
    happens to contain that word.
    """

    if not folder_name:
        return 0

    if not game:
        return 0

    target_tokens = game_tokens(
        folder_name
    )

    source_name = game.get(
        "name",
        "",
    )

    source_tokens = game_tokens(
        source_name
    )

    if not target_tokens:
        return 0

    if not source_tokens:
        return 0

    target_set = {
        compact_token(token)
        for token in target_tokens
    }

    source_set = {
        compact_token(token)
        for token in source_tokens
    }

    # --------------------------------------------------------
    # SINGLE-WORD FOLDER NAMES
    # --------------------------------------------------------
    #
    # A one-word folder name is only trusted if it's an exact,
    # complete match for a one-word title.
    #
    # This prevents:
    #
    #   Organize -> Organize My Shop
    #   Module   -> Module: something
    #
    # while still allowing a genuinely exact one-word title through.
    #

    if len(target_tokens) == 1:
        target = compact_token(
            target_tokens[0]
        )

        if target not in source_set:
            return 0

        if (
            len(source_tokens) == 1
            and compact_token(
                source_tokens[0]
            ) == target
        ):
            return 100

        return 0

    # --------------------------------------------------------
    # EVERY FOLDER TOKEN MUST APPEAR
    # --------------------------------------------------------

    if not all_tokens_match(
        target_tokens,
        source_tokens,
    ):
        return 0

    matched = len(
        target_set & source_set
    )

    coverage = (
        matched / len(target_set)
        if target_set
        else 0
    )

    # --------------------------------------------------------
    # EXACT TOKEN SET
    # --------------------------------------------------------

    if target_set == source_set:
        return 100

    # --------------------------------------------------------
    # SAME WORDS + EXTRA IGDB WORDS
    # --------------------------------------------------------

    if coverage == 1.0:

        # Three or more matching tokens is a very strong signal.
        if matched >= 3:
            return 96

        # Two meaningful tokens is still solid.
        if matched == 2:
            return 92

        # A single matched token shouldn't be able to reach this
        # branch -- that case is already handled above.
        return 80

    # --------------------------------------------------------
    # TOKEN ORDER BONUS
    # --------------------------------------------------------

    sequence_length = longest_common_sequence(
        target_tokens,
        source_tokens,
    )

    sequence_ratio = (
        sequence_length
        / len(target_tokens)
    )

    score = int(
        (coverage * 70)
        + (sequence_ratio * 30)
    )

    return min(
        score,
        95,
    )


# ============================================================
# SEARCH VARIANTS
# ============================================================

def _search_variants(game_name):
    """
    Generate a few different phrasings of a game name to try against
    IGDB's search, since the raw folder name often won't get a hit on
    its own.

    Example:

        AgeofHistoryIII

    becomes:

        AgeofHistoryIII
        age of history 3
        ageofhistory3
    """

    variants = []

    original = str(
        game_name or ""
    ).strip()

    if original:
        variants.append(
            original
        )

    normalized = normalize_game_name(
        original
    )

    if (
        normalized
        and normalized not in variants
    ):
        variants.append(
            normalized
        )

    # A punctuation-free, squashed-together version of the name.
    compact = compact_token(
        normalized
    )

    if (
        compact
        and compact not in variants
    ):
        variants.append(
            compact
        )

    # And a title-cased version, since IGDB search sometimes behaves
    # a little differently depending on casing.
    title_case = normalized.title()

    if (
        title_case
        and title_case not in variants
    ):
        variants.append(
            title_case
        )

    return variants


# ============================================================
# BEST IGDB MATCH
# ============================================================

def find_best_igdb_match(
    game_name,
    minimum_score=70,
):
    """
    Search IGDB for a game and return whichever result scores highest
    against `game_name`, as long as it clears `minimum_score`.

    This is the function organizer.py actually calls when it's trying
    to figure out whether a download folder is a game.

    Returns:
        dict | None
    """

    if not game_name:
        return None

    game_name = str(
        game_name
    ).strip()

    if not game_name:
        return None

    best_game = None
    best_score = 0

    variants = _search_variants(
        game_name
    )

    seen_game_ids = set()

    for variant in variants:

        try:
            games = search_igdb(
                variant
            )

        except requests.RequestException:
            # A network hiccup or bad response for one variant
            # shouldn't stop us from trying the others.
            continue

        except Exception:
            continue

        for game in games:

            game_id = game.get(
                "id"
            )

            if game_id is not None:

                if game_id in seen_game_ids:
                    continue

                seen_game_ids.add(
                    game_id
                )

            score = score_game_match(
                game_name,
                game,
            )

            if score > best_score:
                best_score = score
                best_game = game

    if (
        best_game is not None
        and best_score >= minimum_score
    ):
        return best_game

    return None


# ============================================================
# GENERAL GAME FINDER
# ============================================================

def find_game(
    game_name,
    minimum_score=65,
):
    """
    Compatibility wrapper for code that calls find_game() instead of
    find_best_igdb_match() -- same lookup, just a friendlier default
    threshold for callers that want a looser match.
    """

    return find_best_igdb_match(
        game_name,
        minimum_score=minimum_score,
    )
