# -*- coding: utf-8 -*-
"""
extractor.py - Analyseur multimodale de délibérations via Vertex AI / Gemini 2.5 Flash.
Extrait des données structurées fidèles (résumé, montants financiers, bénéficiaires, votes).
"""

import os
import re
import json
import logging
import subprocess
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CivicLensExtractor")

PROMPT_EXTRACTION_SYSTEM = """
Tu es un expert juriste et analyste spécialisé dans l'examen des actes administratifs des collectivités territoriales françaises (délibérations de conseil municipal, arrêtés, procès-verbaux).

Ta mission est d'analyser le document officiel fourni (en PDF ou image) et d'en extraire TOUTES les informations clés sous une forme JSON rigoureuse et structurée, sans hallucination.

RÈGLES D'EXTRACTION :
1. **Numéro de délibération** : Identifie l'identifiant exact de l'acte (ex: "DELIB-2024-12", "N° 113-2012").
2. **Collectivité** : Commune, EPCI, métropole ou syndicat émetteur.
3. **Date de séance** : Format AAAA-MM-JJ de la réunion du conseil.
4. **Thématique** : Choisis parmi : [Finances & Fiscalité, Éducation & Jeunesse, Urbanisme & Logement, Environnement & Transition Écologique, Culture & Sport, Solidarités & Social, Transports & Voirie, Administration Générale].
5. **Résumé exécutif citoyen** : Rédige une synthèse de 3 à 5 phrases, claire, neutre, expliquant concrètement l'enjeu, ce qui est décidé, et les conséquences pratiques pour la collectivité ou les administrés.
6. **Impacts financiers** : Extrais avec une précision chirurgicale tous les montants en euros (TTC ou HT), les subventions allouées, les marchés attribués, et les bénéficiaires précis (nom d'association, société, etc.). S'il n'y a pas d'impact financier, renvoie une liste vide [].
7. **Résultat du vote** : Indique si la délibération a été adoptée à l'unanimité, à la majorité, ou rejetée.
8. **Références légales** : Codes (CGCT, Commande publique) et articles mentionnés.

FORMAT DE RÉPONSE ATTENDU (JSON STRICT SANS BALISES MARKDOWN) :
{
  "deliberation_id": "DELIB-XXXX",
  "city_or_collectivity": "Nom de la Ville",
  "session_date": "AAAA-MM-JJ",
  "theme": "Thématique",
  "title": "Titre ou objet officiel",
  "executive_summary": "Résumé citoyen...",
  "financials": [
    {
      "amount_eur": 15000.0,
      "budget_code": "Article 6574 / Chapitre 65",
      "beneficiary": "Association Sportive Municipale",
      "operation_type": "SUBVENTION"
    }
  ],
  "vote_result": "ADOPTE_UNANIMITE",
  "legal_references": ["CGCT art. L. 2121-29"],
  "key_entities": ["Association Sportive", "Maire de la Ville"],
  "keywords": ["subvention", "sport", "jeunesse"]
}
"""


class CivicLensExtractor:
    """Extracteur d'informations administratives via Vertex AI Gemini 2.5 Flash."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "global",
        model_name: str = "gemini-3.6-flash",
        account: str = "william@hoffmannw.altostrat.com"
    ):
        self.project_id = project_id or os.environ.get("GCP_PROJECT", "wh-testagy")
        self.location = os.environ.get("GCP_LOCATION", location)
        self.model_name = model_name
        self.account = account
        self._init_vertex()

    def _init_vertex(self):
        """Initialise la connexion Vertex AI avec le jeton gcloud adéquat."""
        try:
            import vertexai
            from google.oauth2.credentials import Credentials

            token_cmd = ["gcloud", "auth", "print-access-token", f"--account={self.account}"]
            token = subprocess.check_output(token_cmd, stderr=subprocess.DEVNULL).decode().strip()
            creds = Credentials(token=token) if token else None

            vertexai.init(project=self.project_id, location=self.location, credentials=creds)
            logger.info(f"Vertex AI initialisé sur le projet '{self.project_id}' ({self.location}) avec le modèle '{self.model_name}'.")
        except Exception as e:
            logger.warning(f"Initialisation standard Vertex AI (fallback sans token gcloud explicite) : {e}")
            try:
                import vertexai
                vertexai.init(project=self.project_id, location=self.location)
            except Exception as e_inner:
                logger.error(f"Échec initialisation Vertex AI : {e_inner}")

    def analyze_pdf(self, pdf_path: str, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Analyse un document PDF complet ou extrait via Gemini Multimodal."""
        from vertexai.generative_models import GenerativeModel, Part

        chosen_model = model_name or self.model_name
        logger.info(f"Envoi du PDF à Gemini ({chosen_model}) : {pdf_path}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
        generation_config = {
            "temperature": 0.1,
            "response_mime_type": "application/json"
        }

        # Tentative avec le modèle choisi, puis repli automatique
        models_to_try = [chosen_model]
        if "gemini-3.6-flash" not in models_to_try:
            models_to_try.append("gemini-3.6-flash")
        if "gemini-2.5-flash" not in models_to_try:
            models_to_try.append("gemini-2.5-flash")

        last_error = None
        for m in models_to_try:
            try:
                model = GenerativeModel(m)
                response = model.generate_content(
                    [pdf_part, PROMPT_EXTRACTION_SYSTEM],
                    generation_config=generation_config
                )
                raw_text = response.text.strip()
                clean_json = re.sub(r"^```json\s*|\s*```$", "", raw_text, flags=re.MULTILINE).strip()
                result = json.loads(clean_json)
                result["model_used"] = m
                return result
            except Exception as e:
                logger.warning(f"Modèle '{m}' indisponible ou en erreur : {e}")
                last_error = e

        return {"error": str(last_error), "deliberation_id": "INCONNU", "title": os.path.basename(pdf_path)}


if __name__ == "__main__":
    import sys
    extractor = CivicLensExtractor()
    if len(sys.argv) > 1:
        res = extractor.analyze_pdf(sys.argv[1])
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("Usage: python3 extractor.py <chemin_vers_pdf>")
