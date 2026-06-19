"""Alignement de chevauchement (overlap alignment) par programmation dynamique.

Contrairement à une LCS classique (sous-séquence, trous n'importe où), on cherche
ici un **chevauchement contigu** : la fin d'un read qui recouvre le début de
l'autre, comme lors d'un assemblage réel. La table DP est construite avec des
bords libres (dp[i][0] = 0, dp[0][j] = 0) pour ne pas pénaliser la partie de
chaque read qui n'appartient pas au chevauchement ; le meilleur score est
cherché sur la dernière ligne et la dernière colonne de la table.
"""

MATCH_SCORE = 1
MISMATCH_SCORE = -1
GAP_SCORE = -2

# Garde-fou de coût : la table DP est en O(n*m) en pure Python. Au-delà de ce
# nombre de cellules (~1.5s mesurées sur cette machine), une requête HTTP
# synchrone bloquerait trop longtemps pour ce prototype.
MAX_CELLS = 4_000_000

EMPTY_RESULT = {
    "score": 0,
    "a_start": None,
    "a_end": None,
    "b_start": None,
    "b_end": None,
    "aligned_a": "",
    "match_line": "",
    "aligned_b": "",
}


def overlap_align(
    a: str,
    b: str,
    match: int = MATCH_SCORE,
    mismatch: int = MISMATCH_SCORE,
    gap: int = GAP_SCORE,
) -> dict:
    """Cherche le meilleur chevauchement contigu entre `a` et `b`.

    Retourne un dict : score, a_start/a_end, b_start/b_end (1-based,
    inclusifs), aligned_a/match_line/aligned_b (représentation à 3 lignes).
    Si aucun chevauchement positif n'existe, `score` vaut 0 et les positions
    sont `None`.
    """
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = dp[i - 1][j - 1] + (
                match if a[i - 1] == b[j - 1] else mismatch
            )
            up = dp[i - 1][j] + gap
            left = dp[i][j - 1] + gap
            dp[i][j] = max(diag, up, left)

    best_score = 0
    best_cell = None
    for j in range(m + 1):
        if dp[n][j] > best_score:
            best_score, best_cell = dp[n][j], (n, j)
    for i in range(n + 1):
        if dp[i][m] > best_score:
            best_score, best_cell = dp[i][m], (i, m)

    if best_cell is None:
        return dict(EMPTY_RESULT)

    aligned_a_rev, aligned_b_rev, match_rev = [], [], []
    i, j = best_cell
    a_end, b_end = i, j
    while i > 0 and j > 0:
        if dp[i][j] == dp[i - 1][j - 1] + (
            match if a[i - 1] == b[j - 1] else mismatch
        ):
            aligned_a_rev.append(a[i - 1])
            aligned_b_rev.append(b[j - 1])
            match_rev.append("|" if a[i - 1] == b[j - 1] else ".")
            i, j = i - 1, j - 1
        elif dp[i][j] == dp[i - 1][j] + gap:
            aligned_a_rev.append(a[i - 1])
            aligned_b_rev.append("-")
            match_rev.append(" ")
            i -= 1
        else:
            aligned_a_rev.append("-")
            aligned_b_rev.append(b[j - 1])
            match_rev.append(" ")
            j -= 1

    return {
        "score": best_score,
        "a_start": i + 1,
        "a_end": a_end,
        "b_start": j + 1,
        "b_end": b_end,
        "aligned_a": "".join(reversed(aligned_a_rev)),
        "match_line": "".join(reversed(match_rev)),
        "aligned_b": "".join(reversed(aligned_b_rev)),
    }
