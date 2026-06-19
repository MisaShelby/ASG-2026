-- =====================================================================
--  Projet ASG-2026 — Lot 1 : Module d'Ingestion et de Qualité
--                    Lot 2 : Module d'Alignement par Programmation Dynamique
--  Schéma PostgreSQL (base : asg_2026)
--  Convention de nommage : tables Django "back_<modele>"
--  Ce fichier documente / recrée les tables des sous-modules :
--    Q1 Ingestion & Qualité  : back_dataset, back_qualityreport, back_fastaconversion
--    Q2 K-mers               : back_kmeranalysis, back_kmercount
--    Q3 Histogramme/spectre  : back_kmerspectrumbin
--    Lot 2 Alignement        : back_alignmentrun
--
--  NB : en production ces tables sont créées par les migrations Django.
--       Ce script sert de référence et permet un (re)montage manuel.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Nettoyage (ordre inverse des dépendances)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS back_alignmentrun CASCADE;

DROP TABLE IF EXISTS back_kmerspectrumbin CASCADE;

DROP TABLE IF EXISTS back_kmercount CASCADE;

DROP TABLE IF EXISTS back_kmeranalysis CASCADE;

DROP TABLE IF EXISTS back_fastaconversion CASCADE;

DROP TABLE IF EXISTS back_qualityreport CASCADE;

DROP TABLE IF EXISTS back_dataset CASCADE;

-- =====================================================================
--  Q1 — INGESTION & QUALITÉ
-- =====================================================================

-- Un fichier de séquençage importé (FASTQ ou FASTA)
CREATE TABLE back_dataset (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file VARCHAR(255) NOT NULL, -- chemin relatif dans MEDIA_ROOT
    input_format VARCHAR(10) NOT NULL DEFAULT 'FASTQ',
    total_reads INTEGER NULL, -- calculé après ingestion
    status VARCHAR(20) NOT NULL DEFAULT 'UPLOADED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT back_dataset_input_format_chk CHECK (
        input_format IN ('FASTQ', 'FASTA')
    ),
    CONSTRAINT back_dataset_status_chk CHECK (
        status IN (
            'UPLOADED',
            'PROCESSING',
            'DONE',
            'ERROR'
        )
    )
);

COMMENT ON TABLE back_dataset IS 'Fichier de séquençage importé (Q1)';

COMMENT ON COLUMN back_dataset.file IS 'Chemin du fichier brut stocké sur disque (MEDIA_ROOT)';

COMMENT ON COLUMN back_dataset.total_reads IS 'Nombre de reads, NULL tant que non calculé';

-- Rapport qualité d'un dataset (relation 1-1)
CREATE TABLE back_qualityreport (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id BIGINT NOT NULL UNIQUE,
    mean_quality DOUBLE PRECISION NOT NULL, -- score Phred moyen
    min_length INTEGER NOT NULL,
    max_length INTEGER NOT NULL,
    mean_length DOUBLE PRECISION NOT NULL,
    gc_content DOUBLE PRECISION NOT NULL, -- % GC
    per_position_quality JSONB NOT NULL DEFAULT '[]'::jsonb, -- qualité moy. par position
    length_distribution JSONB NOT NULL DEFAULT '{}'::jsonb, -- histogramme des longueurs
    CONSTRAINT back_qualityreport_dataset_fk FOREIGN KEY (dataset_id) REFERENCES back_dataset (id) ON DELETE CASCADE
);

COMMENT ON TABLE back_qualityreport IS 'Statistiques qualité agrégées d''un dataset (Q1)';

-- Conversion sélective FASTQ -> FASTA (filtres définis par l'utilisateur)
CREATE TABLE back_fastaconversion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id BIGINT NOT NULL,
    min_mean_quality INTEGER NOT NULL, -- FILTRE PRINCIPAL : qualité moyenne min (choisie par l'utilisateur)
    min_length INTEGER NULL, -- filtre secondaire optionnel
    reads_kept INTEGER NOT NULL DEFAULT 0,
    reads_discarded INTEGER NOT NULL DEFAULT 0,
    output_file VARCHAR(255) NULL, -- FASTA généré (MEDIA_ROOT)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT back_fastaconversion_dataset_fk FOREIGN KEY (dataset_id) REFERENCES back_dataset (id) ON DELETE CASCADE
);

CREATE INDEX back_fastaconversion_dataset_idx ON back_fastaconversion (dataset_id);

COMMENT ON TABLE back_fastaconversion IS 'Résultat d''une conversion sélective FASTQ->FASTA (Q1)';

COMMENT ON COLUMN back_fastaconversion.min_mean_quality IS 'Seuil de qualité moyenne minimal saisi par l''utilisateur';

-- =====================================================================
--  Q2 — DÉCOUPAGE EN K-MERS (k paramétrable par l'utilisateur)
-- =====================================================================

-- Un run de découpage en k-mers pour une valeur de k donnée
CREATE TABLE back_kmeranalysis (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id BIGINT NOT NULL,
    k INTEGER NOT NULL, -- taille du k-mer, saisie par l'utilisateur
    source VARCHAR(10) NOT NULL DEFAULT 'RAW', -- reads bruts ou filtrés
    total_kmers BIGINT NOT NULL DEFAULT 0,
    distinct_kmers BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT back_kmeranalysis_dataset_fk FOREIGN KEY (dataset_id) REFERENCES back_dataset (id) ON DELETE CASCADE,
    CONSTRAINT back_kmeranalysis_source_chk CHECK (source IN ('RAW', 'FILTERED')),
    CONSTRAINT back_kmeranalysis_k_chk CHECK (k >= 1),
    CONSTRAINT back_kmeranalysis_unique UNIQUE (dataset_id, k, source) -- évite les runs en double
);

COMMENT ON TABLE back_kmeranalysis IS 'Run de découpage en k-mers (Q2)';

COMMENT ON COLUMN back_kmeranalysis.k IS 'Longueur du k-mer définie par l''utilisateur';

-- Comptage par k-mer (par défaut : top-N k-mers les plus fréquents)
CREATE TABLE back_kmercount (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id BIGINT NOT NULL,
    sequence VARCHAR(64) NOT NULL, -- le k-mer (ex. 'ATGGC')
    count INTEGER NOT NULL,
    CONSTRAINT back_kmercount_analysis_fk FOREIGN KEY (analysis_id) REFERENCES back_kmeranalysis (id) ON DELETE CASCADE
);

CREATE INDEX back_kmercount_analysis_count_idx ON back_kmercount (analysis_id, count DESC);

COMMENT ON TABLE back_kmercount IS 'Occurrences des k-mers (top-N) d''un run (Q2)';

-- =====================================================================
--  Q3 — HISTOGRAMME / SPECTRE DE K-MERS
-- =====================================================================

-- Une barre du spectre : X = multiplicité, Y = nb de k-mers distincts
CREATE TABLE back_kmerspectrumbin (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id BIGINT NOT NULL,
    multiplicity INTEGER NOT NULL, -- nb d'occurrences (axe X)
    distinct_count BIGINT NOT NULL, -- nb de k-mers distincts ayant cette multiplicité (axe Y)
    CONSTRAINT back_kmerspectrumbin_analysis_fk FOREIGN KEY (analysis_id) REFERENCES back_kmeranalysis (id) ON DELETE CASCADE,
    CONSTRAINT back_kmerspectrumbin_unique UNIQUE (analysis_id, multiplicity)
);

CREATE INDEX back_kmerspectrumbin_analysis_idx ON back_kmerspectrumbin (analysis_id, multiplicity);

COMMENT ON TABLE back_kmerspectrumbin IS 'Spectre de k-mers servant à tracer l''histogramme de fréquence (Q3)';

-- =====================================================================
--  LOT 2 — ALIGNEMENT DE CHEVAUCHEMENT (overlap alignment, DP bords libres)
-- =====================================================================

-- Un calcul d'alignement de chevauchement entre deux reads (A et B)
CREATE TABLE back_alignmentrun (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    read_a_label VARCHAR(255) NOT NULL,
    read_a_sequence TEXT NOT NULL,
    dataset_a_id BIGINT NULL, -- traçabilité si A vient d'un dataset Lot 1
    read_a_index INTEGER NULL, -- position du read dans le fichier dataset
    read_b_label VARCHAR(255) NOT NULL,
    read_b_sequence TEXT NOT NULL,
    dataset_b_id BIGINT NULL,
    read_b_index INTEGER NULL,
    score INTEGER NOT NULL, -- score pondéré : match=+1, mismatch=-1, gap=-2
    read_a_start INTEGER NULL, -- position (1-based, inclusive) du chevauchement contigu dans A
    read_a_end INTEGER NULL,
    read_b_start INTEGER NULL, -- position (1-based, inclusive) du chevauchement contigu dans B
    read_b_end INTEGER NULL,
    aligned_a TEXT NOT NULL, -- ligne A avec gaps '-' pour l'affichage
    match_line TEXT NOT NULL, -- '|' match, '.' mismatch, espace sous un gap
    aligned_b TEXT NOT NULL, -- ligne B avec gaps '-' pour l'affichage
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT back_alignmentrun_dataset_a_fk FOREIGN KEY (dataset_a_id) REFERENCES back_dataset (id) ON DELETE SET NULL,
    CONSTRAINT back_alignmentrun_dataset_b_fk FOREIGN KEY (dataset_b_id) REFERENCES back_dataset (id) ON DELETE SET NULL
);

CREATE INDEX back_alignmentrun_dataset_a_idx ON back_alignmentrun (dataset_a_id);

CREATE INDEX back_alignmentrun_dataset_b_idx ON back_alignmentrun (dataset_b_id);

COMMENT ON TABLE back_alignmentrun IS 'Alignement de chevauchement (overlap, bords libres) entre deux reads (Lot 2)';

COMMENT ON COLUMN back_alignmentrun.score IS 'Score pondéré : match=+1, mismatch=-1, gap=-2';