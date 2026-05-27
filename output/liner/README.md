# Export Liner — Psych IA Ressources

Ce dossier contient vos cours en **Markdown** et **PDF**, prêts pour [Liner](https://liner.com).

## Importer dans Liner

### Option 1 — PDF (recommandé)
1. Ouvrez [liner.com](https://liner.com) ou l'extension navigateur Liner.
2. Allez dans **My Space** → **Upload** / import de fichier.
3. Uploadez les PDF du dossier `pdf/` (un fichier = un module de cours).
4. Surlignez et annotez directement dans Liner.

### Option 2 — Markdown
1. Ouvrez un fichier `.md` dans le navigateur (ou VS Code + preview).
2. Utilisez l'**extension Liner** pour surligner les passages importants.
3. Les surlignages sont enregistrés dans My Space.

## Contenu exporté

- **17** PDF (modules par matière et niveau)
- **17** fichiers Markdown
- Pas de sources HAL — programme français + OpenStax séparément

## Structure

```
liner/
  README.md          ← ce fichier
  pdf/L1/…           ← PDF par module (upload Liner)
  markdown/L1/…      ← sources Markdown
```

## OpenStax (anglais, 755 pages)

Le manuel complet reste dans `output/cours/1-psychology-2e/`.
Pour Liner, importez plutôt les modules **français** ci-dessus, ou un chapitre OpenStax à la fois.

Généré par : `python scripts/export_liner.py`
