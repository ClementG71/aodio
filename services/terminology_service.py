"""
Service de correction terminologique et normalisation du texte.
Gère le remplacement des termes techniques mal transcrits.
"""
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

class TerminologyService:
    """Service de correction des termes techniques et acronymes"""
    
    def __init__(self):
        # Dictionnaire des termes techniques (Acronyme -> Définition ou Forme Correcte)
        # Ici on mappe les erreurs potentielles ou les formes étendues vers la forme canonique (souvent l'acronyme ou le terme exact)
        # Pour l'instant, on s'assure que si l'acronyme est détecté (même en minuscules ou mal orthographié), il est mis en forme.
        # On peut aussi définir des mappings d'erreurs courantes ("ces VEC" -> "CVEC").
        
        self.terms_mapping = {
            # Erreurs phonétiques courantes identifiées
            r"\bces VEC\b": "CVEC",
            r"\bC VEC\b": "CVEC",
            r"\bc'est VEC\b": "CVEC",
            
            # Liste fournie par l'utilisateur (Acronymes)
            # On s'assure que s'ils sont écrits en minuscules ou avec des points, ils sont normalisés
            r"\badmission post[- ]bac\b": "APB",
            r"\bbrevet d['’]études professionnelles\b": "BEP",
            r"\bbulletin officiel de l['’]éducation nationale\b": "BOEN",
            r"\bbulletin officiel de l['’]enseignement supérieur\b": "BOESR",
            r"\bbrevet de technicien supérieur\b": "BTS",
            r"\bbachelor universitaire de technologie\b": "BUT",
            r"\bcour administrative d['’]appel\b": "CAA",
            r"\bcertificat d['’]aptitude professionnelle\b": "CAP",
            r"\bcour de cassation\b": "C. Cas.",
            r"\bcommission des droits et de l['’]autonomie\b": "CDAPH",
            r"\bcontrat à durée déterminée\b": "CDD",
            r"\bcontrat à durée indéterminée\b": "CDI",
            r"\bconseil d['’]état\b": "CE",
            r"\bcode de l['’]entrée et du séjour\b": "CESEDA",
            r"\bcentre de formation par apprentissage\b": "CFA",
            r"\bconseil national de l['’]enseignement supérieur\b": "CNESER",
            r"\bcommission nationale de l['’]informatique et des libertés\b": "CNIL",
            r"\bclasse préparatoire aux grandes écoles\b": "CPGE",
            r"\bcentre régional des œuvres universitaires\b": "CROUS",
            r"\bcode des relations entre le public\b": "CRPA",
            r"\bcode de justice administrative\b": "CJA",
            r"\bcode de la sécurité sociale\b": "CSS",
            r"\bcontribution de vie étudiante\b": "CVEC",
            r"\bdiplôme d['’]accès aux études universitaires\b": "DAEU",
            r"\bdiplôme d['’]études approfondies\b": "DEA",
            r"\bdiplôme d['’]études supérieures spécialisées\b": "DESS",
            r"\bdiplôme d['’]études universitaires générales\b": "DEUG",
            r"\bdiplôme d['’]études universitaires scientifiques\b": "DEUST",
            r"\bdirection générale de l['’]enseignement supérieur\b": "DGESIP",
            r"\bdiplôme d['’]université\b": "DU",
            r"\bdiplôme universitaire de technologie\b": "DUT",
            r"\bélément constitutif\b": "EC",
            r"\benseignant[- ]chercheur\b": "EC",
            r"\beuropean credits transfer system\b": "ECTS",
            r"\bétablissement public à caractère scientifique\b": "EPSCP",
            r"\bformation tout au long de la vie\b": "FTLV",
            r"\bhabilitation à diriger des recherches\b": "HDR",
            r"\binstitut universitaire de technologie\b": "IUT",
            r"\bjuge des référés\b": "JRTA",
            r"\blicence,? master,? doctorat\b": "LMD",
            r"\bloi n° 2000-321\b": "Loi DCRA",
            r"\bloi relative à l['’]enseignement supérieur\b": "Loi ESR",
            r"\bloi relative aux libertés et responsabilités\b": "Loi LRU",
            r"\bloi relative à l['’]orientation et à la réussite\b": "Loi ORE",
            r"\bloi de programmation de la recherche\b": "LPR",
            r"\bministère de l['’]éducation nationale\b": "MENESR",
            r"\bministère de l['’]enseignement supérieur\b": "MESRI",
            r"\bpasseport pour réussir et s['’]orienter\b": "PaRéO",
            r"\bprofesseur agrégé\b": "PRAG",
            r"\bsciences et techniques des activités physiques\b": "STAPS",
            r"\btribunal administratif\b": "TA",
            r"\bunité d['’]enseignement\b": "UE",
            r"\bvalidation des acquis de l['’]expérience\b": "VAE",
            r"\bvalidation des études supérieures\b": "VES"
        }
        
        # Compilation des regex pour performance
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.terms_mapping.items()
        ]
        
        # Ajout des acronymes seuls pour normaliser leur casse (ex: "cvec" -> "CVEC")
        self.acronyms = [
            "APB", "BEP", "BOEN", "BOESR", "BTS", "BUT", "CAA", "CAP", "CDAPH", 
            "CDD", "CDI", "CE", "CESEDA", "CFA", "CNESER", "CNIL", "CPGE", 
            "CROUS", "CRPA", "CJA", "CSS", "CVEC", "DAEU", "DEA", "DESS", 
            "DEUG", "DEUST", "DGES", "DGESIP", "DU", "DUCTI", "DUETI", "DUSTI", 
            "DUT", "EC", "ECTS", "EPSCP", "FTLV", "HDR", "IUT", "JRTA", "LMD", 
            "MENESR", "MESR", "MESRI", "PaRéO", "PRAG", "STAPS", "TA", "UE", 
            "VAE", "VES"
        ]
        
        for acr in self.acronyms:
            # Pattern pour matcher l'acronyme en minuscules ou mixte, entouré de boundary
            pattern = re.compile(r"\b" + re.escape(acr) + r"\b", re.IGNORECASE)
            # On ne l'ajoute que si pas déjà couvert par un pattern plus complexe qui donnerait le même résultat
            self.compiled_patterns.append((pattern, acr))

    def correct_text(self, text: str) -> str:
        """
        Applique les corrections terminologiques sur le texte
        
        Args:
            text: Texte brut
            
        Returns:
            str: Texte corrigé
        """
        if not text:
            return ""
            
        corrected_text = text
        
        # Appliquer les remplacements
        for pattern, replacement in self.compiled_patterns:
            corrected_text = pattern.sub(replacement, corrected_text)
            
        return corrected_text
