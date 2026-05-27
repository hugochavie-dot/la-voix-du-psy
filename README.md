# Psych IA Ressources

Outil de **collecte, classification et indexation légale** de ressources pédagogiques en psychologie (Licence 1, 2 et 3), préparé pour une IA intégrative avec RAG.

## Pipeline principal (`main.py`)

Architecture modulaire à la racine du projet :

```
psych-ia-ressources/
├── main.py                  # Pipeline CLI (validation, download, RAG)
├── sources.json             # Catalogue des sources (canonique)
├── requirements.txt
├── README.md
├── data/
│   ├── downloads/           # PDF téléchargés (open access)
│   ├── metadata/            # JSON par source
│   ├── rag_ready/
│   │   ├── texts/           # Texte brut extrait (pypdf)
│   │   └── rag_chunks.jsonl # Chunks RAG (800–1200 car.)
│   ├── to_verify/           # Sources à vérifier manuellement
│   ├── created_by_user/     # Glossaire, quiz, fiches, concepts
│   ├── index_resources.csv
│   └── index_resources.json
└── src/
    ├── config_loader.py
    ├── source_validator.py
    ├── downloader.py
    ├── metadata_builder.py
    ├── pdf_extractor.py
    ├── rag_chunker.py
    ├── index_writer.py
    └── safety.py
```

### Installation

```bash
cd ~/psych-ia-ressources
python3 -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

### Simulation (dry-run)

Affiche les sources activées, téléchargeables, ignorées, les raisons et les fichiers qui seraient créés — **sans télécharger ni écrire** :

```bash
python main.py --sources sources.json --output data --dry-run
```

### Exécution réelle

```bash
python main.py --sources sources.json --output data
```

Étapes exécutées :

1. Lecture de `sources.json` (sources, `blocked_patterns`, `trusted_publishers`)
2. Validation légale et technique de chaque source
3. Téléchargement **uniquement** si : `enabled`, `download`, `open_access` ou licence, `pdf_url`, domaine fiable, aucun motif bloqué
4. Métadonnées JSON dans `data/metadata/`
5. Index CSV/JSON + `data/to_verify/sources_a_verifier.csv`
6. Extraction PDF → `data/rag_ready/texts/` → chunks → `data/rag_ready/rag_chunks.jsonl`
7. Fichiers modèles utilisateur dans `data/created_by_user/`

### Sources téléchargées vs référencées

| Source | Statut attendu |
|--------|----------------|
| **OpenStax Psychology 2e** | `downloadable` → `downloaded` (seul PDF auto) |
| France Compétences, CNRS, INSERM | `reference_only` (`download: false`) |
| HAL, arXiv (désactivés) | `disabled` |
| Glossaire, quiz, fiches, concepts | `local_user_content` |
| Règles de sécurité IA | `reference_only` |

### Ajouter une source

1. Éditer `sources.json` : `id`, `title`, `url`, `pdf_url`, `legal_status`, `license`, `enabled`, `download`.
2. Vérifier que le domaine figure dans `trusted_publishers`.
3. Lancer `python main.py --sources sources.json --output data --dry-run`.
4. Si statut `to_verify`, corriger la licence ou le domaine avant l'exécution réelle.

### Vérifier une licence

- Consulter la page source (OpenStax : CC BY, HAL : licence indiquée sur la fiche).
- Ne mettre `download: true` que si `legal_status: open_access` **ou** une `license` explicite est renseignée.
- Les motifs `sci-hub`, `libgen`, `z-lib`, `paywall` dans une URL bloquent le téléchargement.

### Générer la base RAG

```bash
python main.py --sources sources.json --output data
```

Le fichier `data/rag_ready/rag_chunks.jsonl` contient une ligne JSON par chunk :

```json
{
  "chunk_id": "openstax_psychology_2e_0001",
  "source_id": "openstax_psychology_2e",
  "title": "OpenStax Psychology 2e",
  "subject": "psychologie_generale",
  "level": "L1",
  "document_type": "manuel_libre",
  "license": "CC BY 4.0",
  "url": "https://openstax.org/details/books/psychology-2e",
  "chunk_number": 1,
  "chunk_text": "..."
}
```

---

## Principes légaux

Le système **n'intègre jamais** de manière automatique :

- livres commerciaux ou scans non autorisés ;
- cours Moodle privés / payants ;
- contournement de paywall (Sci-Hub, LibGen, etc.).

Statuts acceptés pour l'indexation RAG automatique :

| `legal_status`      | Usage RAG auto |
|---------------------|----------------|
| `open_access`       | Oui            |
| `created_by_user`   | Oui            |
| `authorized`        | Oui (validation manuelle) |
| `unknown`           | **Non**        |
| `rejected`          | **Non**        |

## Architecture complémentaire (API FastAPI)

```
psych-ia-ressources/
├── app/
│   ├── main.py              # FastAPI + admin
│   ├── api/routes.py        # REST API
│   ├── core/                # enums, chemins, logs
│   ├── db/                  # SQLAlchemy + SQLite
│   ├── services/            # légal, download, classify, index
│   └── admin/               # interface HTML
├── config/
│   └── system_rules.txt     # règles IA pédagogiques
├── concepts_links.json      # graphe de notions
├── data2/                   # arborescence PDF (API legacy)
├── scripts/
│   ├── download_sources.py
│   └── index_documents.py
├── storage/                 # DB + ChromaDB + uploads
└── logs/
```

## Lancer l'API et l'admin

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Ouvrir : [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Scripts CLI (API legacy)

```bash
python scripts/download_sources.py --dry-run
python scripts/index_documents.py
python scripts/build_cours_html.py --document-id 1
python scripts/build_fiches_resume.py
```

## Sécurité pédagogique

Règles dans `data/created_by_user/system_rules.txt` (généré par le pipeline) et `config/system_rules.txt` :

- L'IA ne remplace pas un psychologue.
- L'IA ne pose pas de diagnostic.
- L'IA ne propose pas de traitement médical.
- L'IA cite ses sources.
- L'IA distingue cours de base et recherche avancée.
- L'IA oriente vers un professionnel en cas de détresse.
- L'IA explique clairement les limites de ses réponses.

## Mise en ligne (déploiement)

Le projet inclut un `Dockerfile` et un blueprint `render.yaml` pour héberger l’API + les contenus HTML (fiches, cours, questionnaires).

### Prérequis

- Compte [GitHub](https://github.com)
- Compte [Render](https://render.com) (gratuit) ou autre hébergeur Docker

### Étapes (Render)

1. **Créer un dépôt GitHub** et y pousser le dossier `psych-ia-ressources` :

```bash
cd ~/psych-ia-ressources
git init
git add .
git commit -m "Initial commit — Psych IA Ressources"
git branch -M main
git remote add origin https://github.com/VOTRE_COMPTE/psych-ia-ressources.git
git push -u origin main
```

2. Sur [render.com](https://render.com) → **New** → **Blueprint** → connecter le dépôt → Render lit `render.yaml`.

3. Une fois déployé, l’URL publique ressemble à `https://psych-ia-ressources.onrender.com` :
   - `/` — interface admin
   - `/hub/` — accueil pédagogique
   - `/fiches/`, `/cours/`, `/questionnaires/` — contenus générés
   - `/api/health` — santé de l’API

### Déploiement local avec Docker

```bash
cd ~/psych-ia-ressources
docker build -t psych-ia-ressources .
docker run -p 8000:8000 psych-ia-ressources
```

Ouvrir [http://localhost:8000](http://localhost:8000).

### Frontend « La Voix du Psy » (React)

Le site vitrine React se déploie séparément sur [Vercel](https://vercel.com) ou [Netlify](https://netlify.com) :

```bash
cd ~/Documents/psycologia/app
npm install && npm run build
```

Puis importer le dépôt sur Vercel (détecte Vite automatiquement) ou glisser le dossier `dist/` sur Netlify.

## Licence du projet

Code du projet : usage éducatif local. Respecter les licences de chaque ressource indexée.
