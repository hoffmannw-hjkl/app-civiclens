# -*- coding: utf-8 -*-
"""
schema.py - Schéma de données structurées pour l'analyse des délibérations municipales (CivicLens).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class FinancialImpact(BaseModel):
    """Impact financier ou subvention mentionné dans une délibération."""
    amount_eur: Optional[float] = Field(
        default=None, 
        description="Montant financier exact en Euros (TTC ou HT) extrait de la délibération, ou null si non financier."
    )
    budget_code: Optional[str] = Field(
        default=None, 
        description="Chapitre, ligne budgétaire ou nomenclature comptable (ex: M57, M14, article 6574)."
    )
    beneficiary: Optional[str] = Field(
        default=None, 
        description="Bénéficiaire de la subvention, titulaire du marché public, ou organisme tiers mentionné."
    )
    operation_type: Optional[str] = Field(
        default="SUBVENTION",
        description="Type d'opération : SUBVENTION, MARCHE_PUBLIC, TARIFICATION, DOTATION, INDEMNITE, RESTRUCTURATION, AUTRE."
    )


class CivicDeliberation(BaseModel):
    """Fiche synthétique et structurée d'une délibération municipale ou acte administratif."""
    deliberation_id: str = Field(
        description="Numéro ou identifiant officiel de la délibération (ex: DELIB-2024-042, n° 113-2012)."
    )
    city_or_collectivity: str = Field(
        description="Nom de la commune, métropole, syndicat mixte ou collectivité territoriale émettrice."
    )
    session_date: Optional[str] = Field(
        default=None, 
        description="Date de la séance du conseil municipal au format AAAA-MM-JJ (ex: 2024-06-25)."
    )
    theme: str = Field(
        description="Domaine principal d'action publique : Finances & Fiscalité, Éducation & Jeunesse, Urbanisme & Logement, Environnement & Transition Écologique, Culture & Sport, Solidarités & Social, Transports & Voirie, Administration Générale."
    )
    title: str = Field(
        description="Titre officiel ou objet clair de la délibération."
    )
    executive_summary: str = Field(
        description="Résumé factuel, vulgarisé et sans jargon à destination des citoyens (3 à 5 phrases expliquant l'enjeu, la décision et ses effets concrets)."
    )
    financials: List[FinancialImpact] = Field(
        default_factory=list,
        description="Liste détaillée des montants, subventions, attributions budgétaires identifiés dans l'acte."
    )
    vote_result: Optional[str] = Field(
        default="ADOPTE",
        description="Résultat du vote : ADOPTE_UNANIMITE, ADOPTE_MAJORITE, REJETE, INCONNU."
    )
    legal_references: List[str] = Field(
        default_factory=list,
        description="Articles de loi ou codes cités (ex: CGCT art. L. 2121-29, Code de la Commande Publique)."
    )
    key_entities: List[str] = Field(
        default_factory=list,
        description="Personnes, entreprises, associations ou lieux géographiques clés cités."
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Mots-clés normalisés pour l'indexation thématique."
    )
