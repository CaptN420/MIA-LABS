# 🧪 MIA — Multi-Agent Intelligence Alchemy

> "Quand une IA a une idée, une autre la critique, une troisième la répare, une quatrième la mute, et une cinquième l'archive pour la postérité."

Bienvenue dans **MIA**, un laboratoire expérimental où plusieurs IA collaborent (et se disputent parfois) pour générer, valider, réparer et faire évoluer des équations symboliques.

⚠️ Aucun alchimiste n'a été blessé durant le développement.

---

## ✨ C'est quoi ce truc ?

MIA est un framework Python de recherche symbolique multi-agents.

Au lieu de demander à une seule IA :

> "Trouve-moi une équation"

MIA organise un véritable conseil des sages numériques :

- 🧠 Générateurs d'idées
- 🛡️ Validateurs
- 🔧 Réparateurs
- 🧬 Mutateurs
- 📚 Archivistes
- 👁️ Sentinelles

Chaque agent possède son rôle et participe à l'évolution des équations.

---

## 🔬 Ce que MIA fait

✅ Génère des variables

✅ Génère des équations

✅ Vérifie la cohérence des unités

✅ Vérifie les rôles causaux

✅ Détecte les incohérences

✅ Répare automatiquement les équations rejetées

✅ Fait muter les équations prometteuses

✅ Conserve un historique complet

✅ Maintient une mémoire persistante

✅ Suit les lignées d'équations

✅ Fonctionne avec des modèles locaux via Ollama

---

## 🧬 Cycle de vie d'une équation

```text
Génération
     ↓
Validation
     ↓
Acceptée ? ── Non ──► Réparation
     ↓                    ↓
    Oui                  Validation
     ↓                    ↓
 Archivage ◄──────────────┘
     ↓
 Mutation
     ↓
 Nouvelle génération

Une équation dans MIA peut avoir :

des parents
des enfants
des mutations
des réparations
un historique complet

Oui.

Les équations ont parfois une vie sociale plus riche que leurs développeurs.

🧠 Mémoire persistante

MIA ne repart pas de zéro à chaque lancement.

Il conserve :

équations validées
équations rejetées
variables
rôles causaux
définitions
connaissances utiles
historiques de validation

L'objectif est que le système apprenne progressivement de ses propres expériences.

🤖 Agents

Quelques habitants du laboratoire :

Aurelius

Génère de nouvelles idées.

"Et si on essayait ça ?"

HermesValidator

Cherche les erreurs.

"Non."

Chymicus

Répare les équations cassées.

"Attends, je peux arranger ça."

Archiviste

Range tout soigneusement.

"Je garde ça au cas où."

Sentinelle

Surveille le chaos.

"Je vous avais dit que ça allait casser."

🖥️ Configuration minimale

MIA peut fonctionner sur CPU.

Configuration testée :

Python 3.x
Ollama
Gemma2:2b

Oui, même un petit modèle peut participer à l'expérience.

C'est plus lent.

Mais ça marche.

🚀 Installation
git clone https://github.com/votre-compte/mia.git

cd mia

pip install -r requirements.txt

Installer Ollama :

ollama pull gemma2:2b

Lancer MIA :

python ui_launcher.py

Puis observer le conseil des IA débattre de l'univers.

📸 Captures

Ajoutez ici vos captures d'écran préférées.

Bonus si une IA se contredit elle-même.

⚠️ Important

MIA est un projet expérimental.

Les équations produites :

ne constituent pas des vérités scientifiques ;
ne remplacent pas des expériences réelles ;
peuvent être géniales ;
peuvent être absurdes ;
sont parfois les deux à la fois.
🛠️ Développé avec du Vibe Coding

Ce projet a été développé avec :

Python
beaucoup de café
des modèles locaux
de nombreuses expérimentations
une quantité difficilement mesurable de "tiens, et si..."

L'IA a aidé à écrire du code.

L'humain a survécu aux bugs.

📈 Objectif

Explorer une question simple :

Que se passe-t-il lorsque plusieurs IA coopèrent, débattent, critiquent, réparent et mémorisent leurs découvertes au lieu de simplement répondre à une question ?

MIA est une tentative de réponse.

📜 Licence

MIT

Parce que l'alchimie devrait être libre.

🧪 MIA
## 🤖 Model Configuration

MIA works with local Ollama models.

Each agent can use its own model through `config.py`.

Example:

```python
self.model_aurelius = "gemma2:2b"
self.model_basilide = "qwen3:4b"
self.model_hermes = "llama3.2:3b"

Mix and match models, or run the entire system with a single lightweight model.

Recommended for CPU:

gemma2:2b

Recommended for quality:

gemma3
qwen3
llama3.x

No code modifications required.
Simply edit config.py and restart MIA.

"Transformant le chaos numérique en équations depuis une durée statistiquement significative."
