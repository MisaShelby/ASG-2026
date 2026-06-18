"""Parsing FASTQ / FASTA en Python pur.

FASTQ : 4 lignes par read
    @identifiant
    SEQUENCE
    +
    SCORES_QUALITE (ASCII Phred+33)

FASTA : 2 lignes par read
    >identifiant
    SEQUENCE
"""
from dataclasses import dataclass

PHRED_OFFSET = 33


@dataclass
class Read:
    """Un read de séquençage."""

    identifier: str
    sequence: str
    qualities: list[int]  # scores Phred décodés (vide pour le FASTA)


def decode_quality(quality_line: str) -> list[int]:
    """Décode une ligne de qualité ASCII (Phred+33) en scores entiers."""
    return [ord(c) - PHRED_OFFSET for c in quality_line]


def parse_fastq(handle):
    """Itère sur les reads d'un fichier FASTQ.

    `handle` est un itérable de lignes (fichier texte ouvert).
    Lève ValueError si la structure 4-lignes est invalide.
    """
    while True:
        header = handle.readline()
        if not header:
            break  # fin de fichier
        header = header.rstrip("\n")
        if header == "":
            continue  # ligne vide tolérée entre les reads
        if not header.startswith("@"):
            raise ValueError(f"En-tête FASTQ invalide : {header!r}")

        seq = handle.readline().rstrip("\n")
        plus = handle.readline().rstrip("\n")
        qual = handle.readline().rstrip("\n")

        if not plus.startswith("+"):
            raise ValueError(f"Ligne séparateur '+' attendue, reçu : {plus!r}")
        if len(seq) != len(qual):
            raise ValueError(
                f"Séquence ({len(seq)}) et qualité ({len(qual)}) de longueurs différentes "
                f"pour le read {header!r}"
            )

        yield Read(
            identifier=header[1:],
            sequence=seq.upper(),
            qualities=decode_quality(qual),
        )


def parse_fasta(handle):
    """Itère sur les reads d'un fichier FASTA (sans qualité)."""
    identifier = None
    seq_parts: list[str] = []
    for line in handle:
        line = line.rstrip("\n")
        if line.startswith(">"):
            if identifier is not None:
                yield Read(identifier, "".join(seq_parts).upper(), [])
            identifier = line[1:]
            seq_parts = []
        elif line:
            seq_parts.append(line)
    if identifier is not None:
        yield Read(identifier, "".join(seq_parts).upper(), [])


def parse(handle, input_format: str):
    """Dispatch selon le format ('FASTQ' ou 'FASTA')."""
    fmt = input_format.upper()
    if fmt == "FASTQ":
        return parse_fastq(handle)
    if fmt == "FASTA":
        return parse_fasta(handle)
    raise ValueError(f"Format non supporté : {input_format!r}")
