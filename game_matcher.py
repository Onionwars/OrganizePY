# game_matcher.py
#
# Home of an earlier take on "is this folder a game, and which game is
# it" matching. It lives alongside igdb.py, which now does this same
# job (normalizing names, generating search variants, scoring matches)
# and is the version actually wired up to organizer.py.
#
# NOTE: nothing in the app currently imports this file. organizer.py
# gets find_best_igdb_match() and score_game_match() from igdb.py, not
# from here, and this module's find_best_igdb_match() even has a
# different signature (it expects you to pass in your own
# search_function). Keeping it around in case some of the matching
# ideas here are still useful, but it's effectively dead code right
# now — safe to delete if you don't need it, or worth merging the
# useful bits into igdb.py if you do.

import re

from difflib import SequenceMatcher

from config import IGNORED_GAME_WORDS, JOINER_WORDS


# Strip a folder name down to lowercase words with junk (brackets,
# version numbers, years, punctuation) removed, so two names that are
# "basically the same" end up as the same string.
def normalize_game_name(name):
    name = str(name).lower()

    name = re.sub(
        r"\[[^\]]*\]",
        " ",
        name
    )

    name = re.sub(
        r"\([^)]*\)",
        " ",
        name
    )

    name = re.sub(
        r"\{[^}]*\}",
        " ",
        name
    )

    name = re.sub(
        r"\b(v|ver|version)[\s._-]*\d+(?:\.\d+)*\b",
        " ",
        name
    )

    name = re.sub(
        r"\b\d{4}\b",
        " ",
        name
    )

    name = re.sub(
        r"[._\-]+",
        " ",
        name
    )

    name = re.sub(
        r"[^a-z0-9\s]",
        " ",
        name
    )

    words = name.split()

    words = [
        word
        for word in words
        if word not in IGNORED_GAME_WORDS
    ]

    return " ".join(words)


# True if a folder name and a candidate result name are the same game,
# allowing one to be a prefix of the other (e.g. "Portal" vs
# "Portal 2" would NOT match here since neither is a prefix of the
# other once normalized -- this is for near-identical names).
def game_names_match(folder_name, result_name):
    folder_normalized = normalize_game_name(
        folder_name
    )

    result_normalized = normalize_game_name(
        result_name
    )

    if not folder_normalized or not result_normalized:
        return False

    if folder_normalized == result_normalized:
        return True

    if folder_normalized.startswith(
        result_normalized + " "
    ):
        return True

    if result_normalized.startswith(
        folder_normalized + " "
    ):
        return True

    return False


# Release folders are often smashed together with no spaces or
# punctuation, e.g. "ReadyorNot" or "ArmaReforger". This tries to pull
# that back apart into separate words using capitalization and digit
# boundaries as hints.
def split_concatenated_word(word):
    if not word:
        return []

    words = re.findall(
        r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+",
        word
    )

    if len(words) <= 1:
        return [word]

    return [
        part.lower()
        for part in words
        if part
    ]


# Break a folder name into individual words, splitting any
# concatenated words along the way and dropping filler/junk words.
def get_folder_words(folder_name):
    normalized = normalize_game_name(
        folder_name
    )

    words = []

    for word in normalized.split():
        parts = split_concatenated_word(
            word
        )

        if parts:
            words.extend(parts)
        else:
            words.append(word)

    return [
        word
        for word in words
        if word not in JOINER_WORDS
        and word not in IGNORED_GAME_WORDS
    ]


# Build a handful of different phrasings of a folder name to try
# against a search API -- the full name, the word-split version, and
# shorter two/three-word prefixes for when the full title is too
# specific to find a hit.
def build_search_variants(folder_name):
    normalized = normalize_game_name(
        folder_name
    )

    if not normalized:
        return []

    variants = [
        normalized
    ]

    words = get_folder_words(
        folder_name
    )

    if words:
        variants.append(
            " ".join(words)
        )

    if len(words) >= 2:
        variants.append(
            " ".join(words[:2])
        )

    if len(words) >= 3:
        variants.append(
            " ".join(words[:3])
        )

    result = []

    for variant in variants:
        variant = variant.strip()

        if variant and variant not in result:
            result.append(
                variant
            )

    return result


# Plain string-similarity ratio between two (normalized) names, 0-1.
def similarity(first, second):
    return SequenceMatcher(
        None,
        normalize_game_name(first),
        normalize_game_name(second)
    ).ratio()


# True if one normalized name is a leading prefix of the other, used
# as a small scoring bonus elsewhere.
def result_matches_prefix(
    folder_name,
    result_name
):
    folder_normalized = normalize_game_name(
        folder_name
    )

    result_normalized = normalize_game_name(
        result_name
    )

    if not folder_normalized or not result_normalized:
        return False

    return (
        result_normalized.startswith(
            folder_normalized
        )
        or folder_normalized.startswith(
            result_normalized
        )
    )


# Look for a search result that's a near-exact match for the folder
# name (per game_names_match) and, among those, pick the one that's
# most textually similar.
def find_complete_folder_match(
    folder_name,
    results
):
    best_result = None
    best_score = 0.0

    for result in results:
        result_name = result.get("name")

        if not result_name:
            continue

        if game_names_match(
            folder_name,
            result_name
        ):
            score = similarity(
                folder_name,
                result_name
            )

            if score > best_score:
                best_score = score
                best_result = result

    return best_result


# Fallback for when nothing matches exactly: score every result by how
# many of the folder's words it contains, plus a bit of general
# similarity and a small bonus if it shares a prefix with the folder
# name.
def find_progressive_match(
    folder_name,
    results
):
    folder_words = get_folder_words(
        folder_name
    )

    if not folder_words:
        return None

    best_result = None
    best_score = 0.0

    for result in results:
        result_name = result.get("name")

        if not result_name:
            continue

        result_words = get_folder_words(
            result_name
        )

        if not result_words:
            continue

        matches = sum(
            1
            for word in folder_words
            if word in result_words
        )

        if matches == 0:
            continue

        coverage = matches / len(
            folder_words
        )

        similarity_score = similarity(
            folder_name,
            result_name
        )

        score = (
            coverage * 0.7
            + similarity_score * 0.3
        )

        if result_matches_prefix(
            folder_name,
            result_name
        ):
            score += 0.15

        if score > best_score:
            best_score = score
            best_result = result

    return best_result


# Try for an exact-ish match first, and only fall back to the fuzzier
# word-overlap scoring if that comes up empty.
def find_best_result(
    folder_name,
    results
):
    if not results:
        return None

    complete_match = find_complete_folder_match(
        folder_name,
        results
    )

    if complete_match:
        return complete_match

    return find_progressive_match(
        folder_name,
        results
    )


# Try several phrasings of the folder name against the caller-supplied
# search function, collecting every unique result along the way, and
# return whichever one looks like the best match overall.
#
# search_function is expected to take a query string and return a
# list of dicts that at least have "id" and "name" keys -- this file
# doesn't call any search API itself.
def find_best_igdb_match(
    folder_name,
    search_function
):
    variants = build_search_variants(
        folder_name
    )

    collected_results = []

    for variant in variants:
        try:
            results = search_function(
                variant
            )
        except Exception:
            continue

        if not results:
            continue

        for result in results:
            result_id = result.get("id")

            if result_id is None:
                continue

            if not any(
                existing.get("id") == result_id
                for existing in collected_results
            ):
                collected_results.append(
                    result
                )

        complete_match = find_complete_folder_match(
            folder_name,
            results
        )

        if complete_match:
            return complete_match

    if not collected_results:
        return None

    return find_best_result(
        folder_name,
        collected_results
    )
