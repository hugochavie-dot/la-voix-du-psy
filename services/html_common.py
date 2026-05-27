"""Utilitaires HTML partagés (cours, fiches, résumés)."""

from __future__ import annotations

import html
import re

LEVEL_LABELS = {
    "L1": "Licence 1",
    "L2": "Licence 2",
    "L3": "Licence 3",
    "mixte": "Tous niveaux",
    "recherche_avancee": "Recherche avancée",
}

SUBJECT_LABELS = {
    "psychologie_generale": "Psychologie générale",
    "psychologie_sociale": "Psychologie sociale",
    "psychologie_cognitive": "Psychologie cognitive",
    "psychologie_du_developpement": "Développement",
    "psychopathologie": "Psychopathologie",
    "neurosciences": "Neurosciences",
    "statistiques": "Statistiques",
    "methodologie_experimentale": "Méthodologie",
    "epistemologie": "Épistémologie",
    "psychologie_differentielle": "Psychologie différentielle",
    "psychologie_du_travail": "Psychologie du travail",
    "psychologie_clinique": "Psychologie clinique",
    "memoire_recherche": "Mémoire / recherche",
    "glossaire": "Glossaire",
    "quiz": "Quiz",
    "fiches_de_revision": "Fiches de révision",
    "liens_entre_notions": "Liens entre notions",
}


def escape(text: str) -> str:
    return html.escape(text or "")


def page_shell(*, title: str, body: str, css_href: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)} — Psych IA Cours</title>
  <link rel="stylesheet" href="{escape(css_href)}" />
</head>
<body>
  <header class="site-header">
    <a href="/cours/index.html">← Catalogue des cours</a>
  </header>
  <div class="layout">
    <main class="content">{body}</main>
  </div>
  <footer class="site-footer">
  <p>Usage pédagogique personnel — respectez les licences des documents sources.</p>
  <p>L'IA ne remplace pas un psychologue.</p>
  </footer>
</body>
</html>
"""
