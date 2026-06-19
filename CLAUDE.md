# Cahier des Charges : Prototype de Pipeline d'Assemblage "De Novo" (Projet ASG-2026)

> Ce document est le cahier des charges de référence du projet. Il doit guider toute décision technique, toute suggestion d'architecture et toute évaluation de "complétude" d'une fonctionnalité dans ce dépôt.

## 1. Contexte du Projet

Dans le cadre de l'analyse de nouvelles séquences virales, le laboratoire nécessite un outil capable de reconstruire une séquence consensus à partir de millions de fragments courts (reads). Les approches classiques par alignement global étant trop coûteuses en ressources, nous souhaitons développer un prototype basé sur la théorie des graphes et les structures de données probabilistes.

## 2. Objectifs Techniques

Le prestataire (l'étudiant) doit concevoir une suite logicielle capable de traiter des données brutes de séquençage pour produire un "contig" (séquence assemblée).

### Lot 1 : Module d'Ingestion et de Qualité

- **Format d'entrée** : Prise en charge des fichiers FASTQ (données brutes avec scores de qualité) et conversion sélective en FASTA.
- **Analyse de granularité** : Implémentation d'un découpage en k-mers paramétrable.
- **Livrable** : Des pages avec des scripts capables de générer un histogramme de fréquence des k-mers pour identifier le taux d'erreur.

### Lot 2 : Module d'Alignement par Programmation Dynamique

Afin de valider localement certains chevauchements complexes, un moteur d'alignement est requis :

- **Algorithme** : Implémentation d'une variante de programmation dynamique pour trouver la Plus Longue Sous-Séquence Commune entre deux reads.
- **Contrainte** : Le module doit retourner le score d'alignement et la position du chevauchement.
- **Livrable** : Une page pour choisir ou uploader deux reads et puis affiche l'alignement de façon lisible.

### Lot 3 : Moteur d'Assemblage "Memory-Efficient" (Approche Minia 2)

L'objectif est de reconstruire les contigs sans jamais construire explicitement le Graphe de de Bruijn en mémoire, en utilisant une structure probabiliste pour tester la connectivité.

**Structure Oracle (Filtre de Bloom)** :
- Implémenter un Filtre de Bloom où seront insérés tous les k-mers distincts considérés comme "solides" (apparaissant au-delà d'un seuil de fréquence).
- Ce filtre servira d'outil de test d'appartenance à coût mémoire constant.
- À comprendre : comment marche un filtre de Bloom.

**Algorithme de Traversée "On-the-fly"** :
- À partir d'un k-mer de départ (seed), le système doit explorer les voisins potentiels en générant les 4 extensions possibles (A, C, G, T) en 3'.
- Chaque extension est soumise au Filtre de Bloom : si le test est positif, la progression continue dans cette direction.
- Le Graphe de de Bruijn est donc ici conceptuel. Il n'est jamais construit entièrement ni stocké quelque part.

**Sortie** :
- L'algorithme doit s'arrêter ou marquer un embranchement lorsque plusieurs extensions sont validées par le filtre (bifurcation dans le graphe implicite).
- Plusieurs contigs peuvent sortir du parcours.

**Analyse critique** :
- Étude de l'impact des faux positifs inhérents au Filtre de Bloom (création de chemins fantômes) et comment les paramètres du filtre (m bits, k fonctions de hachage) influencent la qualité de l'assemblage.

## 3. Contraintes de Performance & Tests

- **Robustesse** : Le code doit pouvoir gérer des reads comportant un taux d'erreur de 1%.
- **Scalabilité** : L'étudiant devra justifier du choix du Filtre de Bloom par une analyse de la consommation mémoire comparée à un dictionnaire standard.
- **Validation** : Un "Toy Dataset" (séquence courte connue) sera fourni pour valider l'exactitude de la reconstruction.

## 4. Livrables Attendus

- Code Source de l'application.
- **Rapport Technique** : Justifiant les scores de similarité choisis et l'impact de la taille de k sur la résolution du graphe. Ainsi que l'analyse critique sur l'impact des faux positifs.
- **Analyse de Complexité** : Une note de calcul comparant la complexité spatiale et temporelle de l'alignement O(n²) face à l'approche par graphe.

## 5. Critère de Recette

Le logiciel sera considéré comme validé si, à partir d'un fichier de 10 000 reads, il parvient à reconstruire la séquence cible avec une identité supérieure à 98%.

---

## État d'avancement (à tenir à jour au fil du projet)

- **Lot 1** : terminé (backend + frontend + tests + revue de code). Voir [docs/LOT1_PLAN.md](docs/LOT1_PLAN.md).
- **Lot 2** : terminé (backend + frontend + tests + vérification navigateur + revue de code). Voir [docs/LOT2.md](docs/LOT2.md) pour le plan détaillé. Algorithme implémenté : alignement de chevauchement à bords libres (et non une LCS classique), conformément aux précisions validées dans LOT2.md §0-1. Garde-fou ajouté en revue : combinaison de longueurs trop coûteuse (n×m > 4M cellules) rejetée avant calcul.
- **Lot 3** : non démarré.

## Stack du projet

- **Backend** : Django + DRF + PostgreSQL (`asg_2026`), app `back` dans `backend/`.
- **Frontend** : React + Vite + MUI + chart.js / react-chartjs-2 + axios + react-router-dom, dans `frontend/`.
