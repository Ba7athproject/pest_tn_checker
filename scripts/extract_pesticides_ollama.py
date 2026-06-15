# -*- coding: utf-8 -*-
"""
Pipeline d'extraction OSINT et de structuration documentaire des pesticides en Tunisie.
Ce script utilise pdfplumber pour lire de manière déterministe les fichiers PDF de pesticides,
découpe le texte en chunks cohérents par page, puis interroge un modèle LLM local
(command-r:latest) via l'API Ollama locale pour structurer le texte brut en un tableau CSV propre.

Auteur : Développeur Python Senior (Datajournalisme & OSINT)
Date : Juin 2026
"""

import os
import sys
import re
import csv
import io
import time
import logging
import requests
import pdfplumber

# --- CONFIGURATION DU LOGGING ---
# Configuration d'un logging clair dans la console (stdout/stderr) pour suivre chaque étape du pipeline.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# --- CONFIGURATION DU SYSTEME ET DES CHEMINS ---
# Résolution des chemins de manière relative par rapport à l'emplacement du script pour assurer la portabilité.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Dossiers par défaut
PDF_DIR = os.path.join(PROJECT_ROOT, "pdf")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "input")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "pesticides_tn_cr.csv")

# Paramètres Ollama
OLLAMA_HOST = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip('/')
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "command-r:latest")

# En-têtes CSV cibles demandées par l'utilisateur
CSV_HEADERS = ["Substance(s) active(s)", "P.Comm", "Société", "Fabricant"]

# --- PROMPT SYSTEME INTÉGRÉ ---
# Prompt strict imposant au modèle command-r:latest d'extraire exclusivement du CSV sans bavardage.
SYSTEM_PROMPT = (
    "Vous êtes un agent d'extraction de données documentaire et d'OSINT spécialisé dans les pesticides. "
    "Votre rôle est d'extraire les informations structurées à partir du texte brut fourni, qui provient de listes officielles.\n\n"
    "Vous devez générer UNIQUEMENT un tableau au format CSV (délimiteur point-virgule ';') contenant exactement les 4 colonnes suivantes :\n"
    "Substance(s) active(s);P.Comm;Société;Fabricant\n\n"
    "Consignes strictes de formatage :\n"
    "1. Ne renvoyez AUCUN texte d'introduction, aucune conclusion, aucun commentaire et aucune note. "
    "Pas de blocs de code Markdown (ne pas utiliser de balises ```csv ou ```). Renvoyez uniquement les lignes de données brutes.\n"
    "2. La toute première ligne de votre réponse doit être l'en-tête exact : Substance(s) active(s);P.Comm;Société;Fabricant\n"
    "3. Pour chaque produit ou pesticide identifié dans le texte, extrayez : la ou les substances actives, le nom commercial (P.Comm), la société distributrice/homologataire (Société), et le fabricant (Fabricant).\n"
    "4. Si une donnée est manquante, inconnue ou absente du document, remplacez-la impérativement par 'Non spécifié'. Ne laissez aucun champ vide.\n"
    "5. S'il n'y a aucun produit identifiable dans le texte, renvoyez uniquement la ligne d'en-tête.\n"
    "6. Conservez l'orthographe exacte et la casse des termes originaux du document."
)


def extract_text_from_pdf(pdf_path: str) -> list:
    """
    Parcourt un fichier PDF et extrait le texte brut de chaque page de manière déterministe.
    
    Args:
        pdf_path (str): Chemin d'accès absolu ou relatif vers le fichier PDF.
        
    Returns:
        list: Une liste de dictionnaires, chaque dictionnaire contenant le numéro de page
              et le texte brut associé : [{"page": 1, "text": "..."}].
    """
    logging.info(f"Début de l'extraction textuelle pour : {os.path.basename(pdf_path)}")
    pages_data = []
    
    try:
        # Ouverture sécurisée du PDF avec pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            logging.info(f"Fichier ouvert avec succès. Nombre total de pages : {total_pages}")
            
            for idx, page in enumerate(pdf.pages):
                page_num = idx + 1
                try:
                    text = page.extract_text()
                    if text and text.strip():
                        pages_data.append({
                            "page": page_num,
                            "text": text.strip()
                        })
                    else:
                        logging.warning(f"La page {page_num} de '{os.path.basename(pdf_path)}' ne contient aucun texte extractible.")
                except Exception as page_err:
                    logging.error(f"Erreur d'extraction sur la page {page_num} de '{os.path.basename(pdf_path)}' : {page_err}")
                    
        logging.info(f"Extraction terminée pour '{os.path.basename(pdf_path)}'. {len(pages_data)}/{total_pages} pages lues.")
    except Exception as e:
        logging.error(f"Erreur critique lors de la lecture du fichier PDF '{pdf_path}' : {e}")
        
    return pages_data


def chunk_text(pages_data: list, max_chars: int = 5000) -> list:
    """
    Découpe le texte extrait en blocs cohérents pour éviter de saturer la fenêtre de contexte du LLM.
    La stratégie par défaut privilégie un découpage page par page. Cependant, si le contenu d'une page
    dépasse `max_chars`, le texte est découpé par blocs de lignes afin de ne pas tronquer de données
    au milieu d'un produit.
    
    Args:
        pages_data (list): Liste de dictionnaires contenant le texte par page.
        max_chars (int): Seuil de caractères au-delà duquel la page est divisée.
        
    Returns:
        list: Liste de chunks avec leur métadonnée source : [{"source": "page_X", "text": "..."}].
    """
    logging.info("Démarrage du chunking intelligent...")
    chunks = []
    
    for page_info in pages_data:
        page_num = page_info["page"]
        text = page_info["text"]
        
        # Cas 1 : La page respecte la taille maximale configurée
        if len(text) <= max_chars:
            chunks.append({
                "source": f"page_{page_num}",
                "text": text
            })
        # Cas 2 : La page dépasse le seuil, découpage intelligent par lignes
        else:
            logging.info(f"Page {page_num} trop volumineuse ({len(text)} caractères). Découpage par sous-blocs de lignes...")
            lines = text.split("\n")
            current_chunk_lines = []
            current_len = 0
            sub_chunk_idx = 1
            
            for line in lines:
                # Si l'ajout de la ligne dépasse la limite, on ferme le chunk actuel
                if current_len + len(line) + 1 > max_chars:
                    if current_chunk_lines:
                        chunks.append({
                            "source": f"page_{page_num}_part_{sub_chunk_idx}",
                            "text": "\n".join(current_chunk_lines)
                        })
                        sub_chunk_idx += 1
                    current_chunk_lines = [line]
                    current_len = len(line)
                else:
                    current_chunk_lines.append(line)
                    current_len += len(line) + 1
                    
            # Enregistrement du reliquat éventuel
            if current_chunk_lines:
                chunks.append({
                    "source": f"page_{page_num}_part_{sub_chunk_idx}",
                    "text": "\n".join(current_chunk_lines)
                })
                
    logging.info(f"Chunking terminé. Nombre total de chunks générés : {len(chunks)}")
    return chunks


def process_with_llm(chunk_content: str, source_label: str) -> str:
    """
    Envoie le chunk de texte au modèle command-r:latest via l'API locale d'Ollama.
    
    Args:
        chunk_content (str): Le texte du chunk à structurer.
        source_label (str): Étiquette décrivant la source (ex: page_X) pour le traçage.
        
    Returns:
        str: La réponse brute textuelle du LLM contenant le tableau CSV.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": chunk_content,
        "system": SYSTEM_PROMPT,
        "stream": False,  # Indispensable pour récupérer la réponse complète en une fois
        "options": {
            "temperature": 0.0  # Paramètre critique imposé pour assurer la reproductibilité et limiter l'hallucination
        }
    }
    
    headers = {"Content-Type": "application/json"}
    max_retries = 3
    timeout = 120  # Timeout élevé car le traitement local peut prendre du temps sur CPU/GPU moyen
    
    logging.info(f"Envoi du chunk [{source_label}] à Ollama ({OLLAMA_MODEL}) à temperature=0.0...")
    
    for attempt in range(1, max_retries + 1):
        try:
            start_time = time.time()
            response = requests.post(OLLAMA_GENERATE_URL, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            elapsed = time.time() - start_time
            
            result_json = response.json()
            response_text = result_json.get("response", "").strip()
            
            logging.info(f"Succès pour le chunk [{source_label}] en {elapsed:.2f}s.")
            return response_text
            
        except requests.exceptions.Timeout:
            logging.warning(f"Timeout lors de l'appel Ollama pour [{source_label}] (Tentative {attempt}/{max_retries}).")
        except requests.exceptions.RequestException as e:
            logging.warning(f"Erreur réseau/connexion avec Ollama pour [{source_label}] (Tentative {attempt}/{max_retries}) : {e}")
            
        if attempt < max_retries:
            sleep_duration = 2 ** attempt
            logging.info(f"Attente de {sleep_duration}s avant la prochaine tentative...")
            time.sleep(sleep_duration)
            
    logging.error(f"Échec définitif d'interrogation pour le chunk [{source_label}] après {max_retries} tentatives.")
    # On renvoie une chaîne vide en cas d'échec total d'un chunk pour ne pas bloquer tout le script,
    # tout en notifiant l'utilisateur dans les logs.
    return ""


def clean_and_validate_csv(llm_response: str, source_label: str) -> list:
    """
    Nettoie les réponses du LLM, extrait les lignes CSV et valide l'intégrité de la structure.
    
    Chaîne de vérification de la donnée :
    1. Nettoyage des artefacts Markdown (type bloc de code ```csv ... ```).
    2. Exclusion des lignes purement textuelles ou de bavardage (grâce à la vérification du séparateur ';').
    3. Parsing robuste des lignes avec le module `csv.reader` pour gérer les guillemets et sauts de ligne.
    4. Exclusion de la ligne d'en-tête répétée pour éviter les doublons dans la fusion.
    5. Test de conformité du nombre de colonnes (Arity check de 4 éléments).
    6. Normalisation des valeurs manquantes ou textuellement nulles (None, null) vers 'Non spécifié'.
    
    Args:
        llm_response (str): La réponse textuelle brute du LLM.
        source_label (str): Étiquette décrivant la source pour le logging.
        
    Returns:
        list: Une liste de lignes validées sous forme de listes de 4 éléments : [Substance, P.Comm, Société, Fabricant].
    """
    if not llm_response.strip():
        logging.warning(f"Réponse vide reçue pour le chunk [{source_label}].")
        return []
        
    # 1. Nettoyage des balises Markdown de bloc de code
    cleaned = llm_response.strip()
    cleaned = re.sub(r"^```(?:csv)?\n", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n```$", "", cleaned)
    cleaned = cleaned.replace("```", "").strip()
    
    # 2. Filtrage préventif des lignes de conversation / bruit
    raw_lines = cleaned.splitlines()
    csv_lines = []
    for idx, line in enumerate(raw_lines):
        line = line.strip()
        if not line:
            continue
        # Si la ligne ne contient pas le séparateur obligatoire ';', c'est probablement du bavardage du LLM
        if ";" not in line:
            logging.debug(f"[{source_label}:L{idx+1}] Ligne sans point-virgule ignorée (bruit de bavardage LLM) : '{line}'")
            continue
        csv_lines.append(line)
        
    # Reconstitution d'un flux texte propre pour le parser de CSV standard
    clean_csv_stream = "\n".join(csv_lines)
    parsed_rows = []
    
    try:
        # 3. Utilisation de csv.reader pour un découpage robuste respectant la syntaxe CSV standard (ex: gestion des guillemets)
        reader = csv.reader(io.StringIO(clean_csv_stream), delimiter=';')
        
        for row_idx, row in enumerate(reader):
            if not row:
                continue
                
            # Nettoyage des espaces blancs sur chaque cellule
            row = [cell.strip() for cell in row]
            
            # 4. Détection et exclusion de l'en-tête répété
            row_content_lower = "".join(row).lower()
            if "substance" in row_content_lower and "p.comm" in row_content_lower:
                logging.debug(f"[{source_label}] En-tête détecté et ignoré à la ligne {row_idx+1}.")
                continue
                
            # 5. Chaîne de validation et de correction de structure (Arity check)
            if len(row) == 4:
                # 6. Normalisation des valeurs manquantes/incohérentes vers 'Non spécifié'
                validated_row = [
                    cell if cell and cell.lower() not in ["none", "null", "nan", ""] else "Non spécifié"
                    for cell in row
                ]
                parsed_rows.append(validated_row)
            else:
                # Tentative de récupération ou ajustement en cas de colonnes incohérentes
                if len(row) < 4:
                    logging.warning(
                        f"[{source_label}] Ligne {row_idx+1} incomplète ({len(row)}/4 col). "
                        f"Complétée avec 'Non spécifié' : {row}"
                    )
                    while len(row) < 4:
                        row.append("Non spécifié")
                    parsed_rows.append(row)
                else:
                    logging.warning(
                        f"[{source_label}] Ligne {row_idx+1} surchargée ({len(row)}/4 col). "
                        f"Troncature effectuée : {row}"
                    )
                    parsed_rows.append(row[:4])
                    
    except Exception as parse_err:
        logging.error(f"Erreur de parsing CSV sur la réponse du chunk [{source_label}] : {parse_err}")
        
    return parsed_rows


def save_to_csv(all_records: list, output_path: str):
    """
    Fusionne l'ensemble des données structurées et les exporte dans le fichier CSV final.
    Applique l'encodage 'utf-8-sig' pour assurer la correcte interprétation des caractères accentués
    français dans les logiciels bureautiques comme Microsoft Excel.
    
    Args:
        all_records (list): Liste de listes contenant les données validées.
        output_path (str): Chemin du fichier CSV de sortie.
    """
    logging.info(f"Préparation de l'export des données vers : {output_path}")
    
    # Création automatique du répertoire parent si inexistant
    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
        
    try:
        # Encodage utf-8-sig avec écriture de l'en-tête standardisé
        with open(output_path, mode="w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.writer(csv_file, delimiter=";")
            
            # Écriture de l'en-tête unique
            writer.writerow(CSV_HEADERS)
            
            # Écriture des lignes consolidées
            writer.writerows(all_records)
            
        logging.info(f"[+] Succès : Fichier CSV exporté avec succès ({len(all_records)} lignes de données enregistrées).")
    except Exception as e:
        logging.error(f"Erreur critique lors de l'écriture du fichier CSV '{output_path}' : {e}")


def main():
    logging.info("=== INITIALISATION DU PIPELINE D'EXTRACTION PESTICIDES OLLAMA ===")
    
    # 1. Validation de l'environnement local
    if not os.path.exists(PDF_DIR):
        logging.error(f"Le dossier des PDF '{PDF_DIR}' est introuvable. Veuillez le créer ou ajuster la configuration.")
        sys.exit(1)
        
    # Recherche des fichiers PDF dans le répertoire cible
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")]
    
    if not pdf_files:
        logging.warning(f"Aucun fichier PDF détecté dans le répertoire : {PDF_DIR}")
        sys.exit(0)
        
    logging.info(f"Fichiers PDF à traiter ({len(pdf_files)}) : {pdf_files}")
    
    # Test préliminaire de la connectivité Ollama
    try:
        # Simple test de ping sur le serveur Ollama
        test_resp = requests.get(OLLAMA_HOST, timeout=5)
        test_resp.raise_for_status()
        logging.info(f"Connexion réussie avec Ollama sur {OLLAMA_HOST}.")
    except Exception as ollama_err:
        logging.error(
            f"Impossible de joindre le service Ollama sur {OLLAMA_HOST}.\n"
            f"Veuillez démarrer Ollama et vérifier que le modèle '{OLLAMA_MODEL}' est installé (ex: 'ollama pull {OLLAMA_MODEL}').\n"
            f"Erreur détaillée : {ollama_err}"
        )
        sys.exit(1)
        
    consolidated_records = []
    
    # 2. Traitement itératif des fichiers PDF
    for pdf_filename in pdf_files:
        pdf_path = os.path.join(PDF_DIR, pdf_filename)
        logging.info(f"--- Traitement du fichier : {pdf_filename} ---")
        
        # Étape A : Extraction déterministe
        pages_content = extract_text_from_pdf(pdf_path)
        if not pages_content:
            logging.warning(f"Aucun texte n'a pu être extrait du fichier {pdf_filename}. Fichier ignoré.")
            continue
            
        # Étape B : Chunking intelligent par page / blocs de lignes
        chunks = chunk_text(pages_content)
        
        # Étape C : Requêtage LLM et validation des données pour chaque chunk
        for chunk in chunks:
            source_id = f"{pdf_filename} -> {chunk['source']}"
            
            # Requêtage au LLM local Ollama
            raw_response = process_with_llm(chunk["text"], source_id)
            
            # Structuration, nettoyage et validation de l'intégrité structurelle
            validated_chunk_rows = clean_and_validate_csv(raw_response, source_id)
            
            if validated_chunk_rows:
                logging.info(f"[{source_id}] {len(validated_chunk_rows)} lignes validées extraites.")
                consolidated_records.extend(validated_chunk_rows)
            else:
                logging.warning(f"[{source_id}] Aucune ligne de données extraite ou validée pour ce chunk.")
                
    # 3. Consolidation et exportation finale
    if consolidated_records:
        logging.info(f"Consolidation de {len(consolidated_records)} lignes au total.")
        save_to_csv(consolidated_records, OUTPUT_FILE)
        logging.info("=== FIN DU PIPELINE D'EXTRACTION - TOUT EST OK ===")
    else:
        logging.error("Échec du pipeline : aucune ligne valide n'a pu être extraite de l'ensemble des PDF.")
        sys.exit(1)


if __name__ == "__main__":
    main()
