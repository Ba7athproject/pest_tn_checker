# -*- coding: utf-8 -*-
"""
Pipeline d'extraction OSINT et de structuration documentaire des pays d'origine des pesticides.
Ce script utilise pdfplumber pour lire de manière déterministe les fichiers PDF,
découpe le texte en chunks par page, puis interroge le modèle local qwen2.5:latest
via l'API Ollama pour structurer le texte brut en un tableau CSV contenant le pays d'origine.
Si le pays n'est pas spécifié dans le tableau, le modèle le déduit du fabricant ou de la société.
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

# Force le vidage du tampon (flush) à chaque ligne pour éviter la mise en mémoire tampon des logs (buffering)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

# --- CONFIGURATION DU LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# --- CONFIGURATION DU SYSTEME ET DES CHEMINS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Chargement du fichier .env à la racine du projet
from dotenv import load_dotenv
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(ENV_PATH):
    load_dotenv(dotenv_path=ENV_PATH)
    logging.info(f"Fichier .env chargé avec succès : {ENV_PATH}")
else:
    logging.warning(f"Fichier .env absent à l'adresse : {ENV_PATH}")

# Dossiers par défaut
PDF_DIR = os.path.join(PROJECT_ROOT, "pdf")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "input")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "pesticides_pays_cr.csv")

# Paramètres Ollama
OLLAMA_HOST = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip('/')
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")

# En-têtes CSV cibles
CSV_HEADERS = ["P.Comm", "Société", "Fabricant", "Pays d'origine"]

# --- PROMPT SYSTEME INTÉGRÉ ---
SYSTEM_PROMPT = (
    "Vous êtes un agent d'extraction de données documentaire et d'OSINT spécialisé dans les pesticides.\n"
    "Votre rôle est d'extraire des informations structurées à partir du texte brut fourni, qui provient de listes officielles de pesticides.\n\n"
    "Vous devez générer UNIQUEMENT un tableau au format CSV (délimiteur point-virgule ';') contenant exactement les 6 colonnes suivantes :\n"
    "Substance active;P.Comm;N.H.;Société;Fabricant;Pays d'origine\n\n"
    "Consignes strictes de formatage et d'extraction :\n"
    "1. Ne renvoyez AUCUN texte explicatif, d'introduction ou de conclusion. Pas de balises de code Markdown (pas de ```csv ni ```). Renvoyez uniquement les lignes de données brutes.\n"
    "2. La toute première ligne de votre réponse doit être l'en-tête exact : Substance active;P.Comm;N.H.;Société;Fabricant;Pays d'origine\n"
    "3. Pour chaque produit commercial identifié dans le texte, extrayez la substance active, le nom commercial (P.Comm), le numéro d'homologation (N.H.), la société distributrice (Société), le fabricant (Fabricant), et le pays d'origine du produit ou du fabricant (Pays d'origine).\n"
    "4. Régle importante de déduction du Pays d'origine :\n"
    "   - Si le pays d'origine n'est pas explicitement mentionné, vous devez impérativement le déduire de la cellule Fabricant ou Société si elle contient une indication géographique (ex: 'SIPCAM INAGRA Espagne' -> Pays d'origine: 'Espagne'; 'BASF ALLEMAGNE' -> Pays d'origine: 'Allemagne'; 'T. STANES &Co.Ltd. INDE' -> Pays d'origine: 'Inde', etc.).\n"
    "   - Si aucun pays ne peut être extrait ou raisonnablement déduit, inscrivez 'Non spécifié'.\n"
    "5. Si un champ (comme le fabricant ou le numéro d'homologation) est absent ou inconnu, écrivez obligatoirement 'Non spécifié'. Ne laissez jamais de colonne vide ou manquante dans une ligne.\n"
    "6. N'incluez JAMAIS les détails d'usages, de cibles (comme Tomate, Melon, Teigne, Mildiou) ou de doses (comme l/ha, cc/hl, kg/ha, Volume de bouillie) dans vos colonnes. Ces informations doivent être complètement ignorées.\n"
    "7. S'il n'y a aucun produit identifiable dans le texte, renvoyez uniquement la ligne d'en-tête.\n"
    "8. Conservez l'orthographe exacte et la casse des termes originaux pour Substance active, P.Comm, N.H., Société et Fabricant."
)

def extract_text_from_pdf(pdf_path: str) -> list:
    logging.info(f"Début de l'extraction textuelle pour : {os.path.basename(pdf_path)}")
    pages_data = []
    try:
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
    logging.info("Démarrage du chunking intelligent...")
    chunks = []
    for page_info in pages_data:
        page_num = page_info["page"]
        text = page_info["text"]
        if len(text) <= max_chars:
            chunks.append({
                "source": f"page_{page_num}",
                "text": text
            })
        else:
            logging.info(f"Page {page_num} trop volumineuse ({len(text)} caractères). Découpage par sous-blocs de lignes...")
            lines = text.split("\n")
            current_chunk_lines = []
            current_len = 0
            sub_chunk_idx = 1
            for line in lines:
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
            if current_chunk_lines:
                chunks.append({
                    "source": f"page_{page_num}_part_{sub_chunk_idx}",
                    "text": "\n".join(current_chunk_lines)
                })
    logging.info(f"Chunking terminé. Nombre total de chunks générés : {len(chunks)}")
    return chunks

def process_with_llm(chunk_content: str, source_label: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": chunk_content,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 1000
        }
    }
    headers = {"Content-Type": "application/json"}
    max_retries = 3
    timeout = 600

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
    return ""

def map_row_to_target_columns(row: list) -> list:
    """
    Mappe de manière robuste une ligne de longueur N (généralement 6 colonnes issues du LLM)
    vers les 4 colonnes cibles : [P.Comm, Société, Fabricant, Pays d'origine]
    """
    row = [cell.strip() for cell in row]
    if len(row) < 4:
        while len(row) < 4:
            row.append("Non spécifié")
        return row

    # Le pays d'origine est toujours la dernière colonne
    pays = row[-1]

    if len(row) == 6:
        # Structure attendue : Substance active;P.Comm;N.H.;Société;Fabricant;Pays d'origine
        p_comm = row[1]
        societe = row[3]
        fabricant = row[4]
    elif len(row) == 5:
        # Cas 5 colonnes : N.H. ou Substance active ou Fabricant manquant
        if re.search(r'[A-Z0-9\.\-\/]{3,}', row[2], re.IGNORECASE):
            # Le troisième élément ressemble à un numéro d'homologation (ex: I.010-19)
            # Structure : Substance;P.Comm;N.H.;Société;Pays
            p_comm = row[1]
            societe = row[3]
            fabricant = "Non spécifié"
        else:
            # Pas de N.H. détecté, structure probable : Substance;P.Comm;Société;Fabricant;Pays
            p_comm = row[1]
            societe = row[2]
            fabricant = row[3]
    elif len(row) >= 7:
        # Plus de 6 colonnes (bruit/usages inclus par erreur dans les colonnes intermédiaires)
        p_comm = row[1]
        societe = row[3]
        fabricant = row[4]
    else:
        # Exactement 4 colonnes
        p_comm = row[0]
        societe = row[1]
        fabricant = row[2]

    # Mots-clés indiquant des détails de doses, cibles ou usages à écarter
    usage_keywords = [
        "l/ha", "cc/hl", "g/hl", "dose", "volume de", "kg/ha", "teigne", 
        "mildiou", "thrips", "mineuse", "puceron", "acariens", "tuta absoluta", 
        "traitement", "applications", "pulvérisation", "cultures"
    ]

    def clean_cell(cell):
        if not cell or cell.lower() in ["none", "null", "nan", "non spécifié", ""]:
            return "Non spécifié"
        cell_lower = cell.lower()
        if any(kw in cell_lower for kw in usage_keywords):
            return "Non spécifié"
        return cell

    return [
        clean_cell(p_comm),
        clean_cell(societe),
        clean_cell(fabricant),
        clean_cell(pays)
    ]

def clean_and_validate_csv(llm_response: str, source_label: str) -> list:
    if not llm_response.strip():
        logging.warning(f"Réponse vide reçue pour le chunk [{source_label}].")
        return []
        
    cleaned = llm_response.strip()
    cleaned = re.sub(r"^```(?:csv)?\n", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n```$", "", cleaned)
    cleaned = cleaned.replace("```", "").strip()
    
    raw_lines = cleaned.splitlines()
    csv_lines = []
    for idx, line in enumerate(raw_lines):
        line = line.strip()
        if not line:
            continue
        if ";" not in line:
            logging.debug(f"[{source_label}:L{idx+1}] Ligne sans point-virgule ignorée (bruit de bavardage LLM) : '{line}'")
            continue
        csv_lines.append(line)
        
    clean_csv_stream = "\n".join(csv_lines)
    parsed_rows = []
    
    try:
        reader = csv.reader(io.StringIO(clean_csv_stream), delimiter=';')
        for row_idx, row in enumerate(reader):
            if not row:
                continue
            row = [cell.strip() for cell in row]
            
            # Détection et exclusion de l'en-tête répété
            row_content_lower = "".join(row).lower()
            if "p.comm" in row_content_lower or "fabricant" in row_content_lower or "pays" in row_content_lower or "substance" in row_content_lower:
                logging.debug(f"[{source_label}] En-tête détecté et ignoré à la ligne {row_idx+1}.")
                continue
                
            # Mappage robuste de la ligne brute de longueur variable vers les 4 colonnes cibles
            validated_row = map_row_to_target_columns(row)
            parsed_rows.append(validated_row)
    except Exception as parse_err:
        logging.error(f"Erreur de parsing CSV sur la réponse du chunk [{source_label}] : {parse_err}")
    return parsed_rows

def save_to_csv(all_records: list, output_path: str):
    logging.info(f"Préparation de l'export des données vers : {output_path}")
    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    try:
        with open(output_path, mode="w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.writer(csv_file, delimiter=";")
            writer.writerow(CSV_HEADERS)
            writer.writerows(all_records)
        logging.info(f"[+] Succès : Fichier CSV exporté avec succès ({len(all_records)} lignes de données enregistrées).")
    except Exception as e:
        logging.error(f"Erreur critique lors de l'écriture du fichier CSV '{output_path}' : {e}")

def main():
    logging.info("=== INITIALISATION DU PIPELINE D'EXTRACTION PAYS OLLAMA ===")
    
    if not os.path.exists(PDF_DIR):
        logging.error(f"Le dossier des PDF '{PDF_DIR}' est introuvable.")
        sys.exit(1)
        
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")]
    if not pdf_files:
        logging.warning(f"Aucun fichier PDF détecté dans le répertoire : {PDF_DIR}")
        sys.exit(0)
        
    logging.info(f"Fichiers PDF à traiter ({len(pdf_files)}) : {pdf_files}")
    
    try:
        test_resp = requests.get(OLLAMA_HOST, timeout=5)
        test_resp.raise_for_status()
        logging.info(f"Connexion réussie avec Ollama sur {OLLAMA_HOST}.")
    except Exception as ollama_err:
        logging.error(
            f"Impossible de joindre le service Ollama sur {OLLAMA_HOST}.\n"
            f"Veuillez démarrer Ollama et vérifier que le modèle '{OLLAMA_MODEL}' est installé.\n"
            f"Erreur détaillée : {ollama_err}"
        )
        sys.exit(1)
        
    consolidated_records = []
    
    # Pour accélérer le test, on va traiter les fichiers PDF
    for pdf_filename in pdf_files:
        pdf_path = os.path.join(PDF_DIR, pdf_filename)
        logging.info(f"--- Traitement du fichier : {pdf_filename} ---")
        
        pages_content = extract_text_from_pdf(pdf_path)
        if not pages_content:
            logging.warning(f"Aucun texte n'a pu être extrait du fichier {pdf_filename}. Fichier ignoré.")
            continue
            
        chunks = chunk_text(pages_content)
        
        # Pour éviter de faire trop d'appels longs si c'est volumineux,
        # le script traitera l'ensemble du PDF ou un échantillon.
        # Mais le pipeline complet doit tout traiter.
        for chunk in chunks:
            source_id = f"{pdf_filename} -> {chunk['source']}"
            raw_response = process_with_llm(chunk["text"], source_id)
            validated_chunk_rows = clean_and_validate_csv(raw_response, source_id)
            
            if validated_chunk_rows:
                logging.info(f"[{source_id}] {len(validated_chunk_rows)} lignes validées extraites.")
                consolidated_records.extend(validated_chunk_rows)
            else:
                logging.warning(f"[{source_id}] Aucune ligne de données extraite ou validée pour ce chunk.")
                
    if consolidated_records:
        logging.info(f"Consolidation de {len(consolidated_records)} lignes au total.")
        save_to_csv(consolidated_records, OUTPUT_FILE)
        logging.info("=== FIN DU PIPELINE D'EXTRACTION PAYS - TOUT EST OK ===")
    else:
        logging.error("Échec du pipeline : aucune ligne valide n'a pu être extraite.")
        sys.exit(1)

if __name__ == "__main__":
    main()
