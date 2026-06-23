from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path



@dataclass
class RuntimeConfig:
    base_dir: Path

    def __post_init__(self) -> None:
        self.api_url = "http://127.0.0.1:11434/api/chat"

        # Modèles principaux
        self.model_aurelius = "gemma2:2b"
        self.model_basilide = "gemma2:2b"
        self.model_hermes = "gemma2:2b"
        self.model_synthetiseur = "gemma2:2b"

        # Modèles support / validation
        self.model_chymicus = "gemma2:2b"
        self.model_sentinelle = "gemma2:2b"
        self.model_archiviste = "gemma2:2b"
        self.model_variablevalidator = "gemma2:2b"
        self.model_equationvalidator = "gemma2:2b"
        self.model_finalvalidator = "gemma2:2b"
        self.model_reviseur = "gemma2:2b"
        self.model_hermetica = "gemma2:2b"

        # Alias de compatibilité attendus par le code existant
        self.model_variable_validator = self.model_variablevalidator
        self.model_equation_validator = self.model_equationvalidator
        self.model_final_validator = self.model_finalvalidator
        self.model_hermes_validator = self.model_variablevalidator

        # Réglages génération / robustesse
        self.request_timeout = 55
        self.max_api_retries = 4
        self.retry_backoff_seconds = 1.0
        self.max_generation_attempts = 4

        # Anti-fallback
        self.enable_role_guard_fallbacks = True
        self.allow_generic_equation_fallback = False
        self.allow_generic_mutation_fallback = False
        self.allow_generic_support_equation = False
        self.allow_generic_support_mutation = False

        # Températures attendues par BaseDebateCore
        self.temperature_debate = 0.35
        self.temperature_support = 0.20
        self.temperature_hermes = 0.30

        # Longueur de génération
        self.num_predict_debate = 96
        self.num_predict_support = 72
        self.num_predict_validation = 72
        self.num_predict_archive = 68
        self.num_predict_sentinelle = 64
        self.num_predict_reviseur = 64
        self.num_predict_hermes = 88
        self.num_predict_synth = 96

        # Mémoire / diversité
        self.max_history_messages = 8
        self.variable_family_soft_limit = 2
        self.variable_signature_soft_limit = 2
        self.equation_signature_soft_limit = 2
        self.min_regen_attempts_before_fallback = 2
        self.force_diversity_after_repeats = 2


        # Noyau physique de départ
        self.enable_physics_core = True
        self.physics_core_require_cycle_variable = True
        self.physics_core_starter_pack = {
            "J": {
                "definition": "flux local de matière à travers une interface",
                "unit": "mol·m⁻²·s⁻¹",
                "measure": "bilan de flux sur surface instrumentée",
                "role": "J contrôle directement le transfert net local",
                "family": "flux",
                "links": ["J augmente Ndot", "J convertit une force motrice locale en transfert mesurable"],
                "remarks": ["symbole verrouillé: flux local"],
                "source_agent": "PHYSICS_CORE",
            },
            "A": {
                "definition": "surface d'échange active",
                "unit": "m²",
                "measure": "mesure géométrique ou image calibrée",
                "role": "A convertit un flux local en débit global",
                "family": "structure",
                "links": ["A augmente Ndot", "A augmente la zone disponible pour le transfert"],
                "remarks": ["symbole verrouillé: surface"],
                "source_agent": "PHYSICS_CORE",
            },
            "ΔC": {
                "definition": "gradient ou écart de concentration moteur du transfert",
                "unit": "mol·m⁻³",
                "measure": "différence de concentration entre deux points ou deux phases",
                "role": "ΔC fournit la force motrice du transfert",
                "family": "concentration",
                "links": ["ΔC augmente J", "ΔC augmente la force motrice"],
                "remarks": ["symbole verrouillé: gradient de concentration"],
                "source_agent": "PHYSICS_CORE",
            },
            "D": {
                "definition": "diffusivité effective du milieu",
                "unit": "m²/s",
                "measure": "ajustement de profil de diffusion ou littérature expérimentale",
                "role": "D fixe la vitesse de propagation diffusive",
                "family": "transport",
                "links": ["D augmente J", "D accélère l'homogénéisation"],
                "remarks": ["symbole verrouillé: diffusivité"],
                "source_agent": "PHYSICS_CORE",
            },
            "L": {
                "definition": "distance ou épaisseur caractéristique de transfert",
                "unit": "m",
                "measure": "mesure géométrique directe",
                "role": "L freine le transfert quand le chemin augmente",
                "family": "structure",
                "links": ["L diminue J", "L augmente la résistance géométrique"],
                "remarks": ["symbole verrouillé: longueur/épaisseur"],
                "source_agent": "PHYSICS_CORE",
            },
            "R": {
                "definition": "résistance globale de transfert",
                "unit": "s/m",
                "measure": "identification inverse à partir d'un débit et d'une force motrice",
                "role": "R limite le transfert effectif",
                "family": "resistance",
                "links": ["R diminue Ndot", "R freine la conversion de la force motrice en débit"],
                "remarks": ["symbole verrouillé: résistance"],
                "source_agent": "PHYSICS_CORE",
            },
        }

        # Session (résolue explicitement par launcher.py)
        self.session_dir = self.base_dir

    def model_for_agent(self, agent_name: str) -> str:
        key = (
            agent_name.strip()
            .lower()
            .replace(" ", "")
            .replace("_", "")
            .replace("é", "e")
        )

        mapping = {
            "aurelius": self.model_aurelius,
            "basilide": self.model_basilide,
            "hermes": self.model_hermes,
            "hermesvalidator": self.model_hermes_validator,
            "synthetiseur": self.model_synthetiseur,
            "chymicus": self.model_chymicus,
            "sentinelle": self.model_sentinelle,
            "archiviste": self.model_archiviste,
            "variablevalidator": self.model_variablevalidator,
            "equationvalidator": self.model_equationvalidator,
            "finalvalidator": self.model_finalvalidator,
            "aureliusvalidation": self.model_variablevalidator,
            "basilidevalidation": self.model_variablevalidator,
            "reviseur": self.model_reviseur,
            "hermetica": self.model_hermetica,
        }
        return mapping.get(key, self.model_aurelius)
