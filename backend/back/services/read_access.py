"""Accès en lecture aux reads d'un Dataset existant, sans stockage individuel
en base (cohérent avec le choix du Lot 1) : on relit le fichier à la volée.
"""
from .fastq_parser import parse


def get_read_at(dataset, index: int):
    """Retourne le `Read` à la position `index` (0-based) du fichier dataset.

    Lève IndexError si l'index dépasse le nombre de reads du fichier.
    """
    found = get_reads_at(dataset, [index])
    if index not in found:
        raise IndexError(f"Aucun read à l'index {index}.")
    return found[index]


def get_reads_at(dataset, indices: list[int]) -> dict[int, object]:
    """Retourne {index: Read} pour les indices demandés, en un seul passage du
    fichier (utile quand plusieurs reads d'un même dataset sont demandés, p.ex.
    les deux reads d'un alignement).
    """
    wanted = set(indices)
    found = {}
    with dataset.file.open("rt") as handle:
        for i, read in enumerate(parse(handle, dataset.input_format)):
            if i in wanted:
                found[i] = read
                if len(found) == len(wanted):
                    break
    return found


def load_reads(dataset) -> list:
    """Charge tous les `Read` d'un dataset en mémoire (un seul passage du
    fichier). Utilisé par l'assemblage, qui a besoin de l'ensemble des reads."""
    with dataset.file.open("rt") as handle:
        return list(parse(handle, dataset.input_format))


def preview_reads(dataset, limit: int = 50, offset: int = 0) -> list[dict]:
    """Aperçu paginé des reads d'un dataset : index, identifiant, longueur,
    début de séquence (pour un sélecteur frontend, sans tout charger).
    """
    previews = []
    with dataset.file.open("rt") as handle:
        for i, read in enumerate(parse(handle, dataset.input_format)):
            if i < offset:
                continue
            if len(previews) >= limit:
                break
            previews.append(
                {
                    "index": i,
                    "identifier": read.identifier,
                    "length": len(read.sequence),
                    "preview": read.sequence[:40],
                }
            )
    return previews
