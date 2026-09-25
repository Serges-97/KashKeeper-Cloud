# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - 1 SUR 2)
# =====================================================================
import sqlite3
import os
import secrets
import sys
import json
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from datetime import datetime, timedelta
from fastapi import Header, HTTPException, Depends

# 🔑 SÉCURITÉ CONSTRUCTEUR : Forcer Render à cibler le bon dossier physique
DOSSIER_DU_FICHIER = os.path.dirname(os.path.abspath(__file__))
if DOSSIER_DU_FICHIER not in sys.path:
    sys.path.insert(0, DOSSIER_DU_FICHIER)

import data_base

# Initialisation des structures de données centrales au démarrage
data_base.initialisation_systeme()

app = FastAPI(
    title="KashFlow Multi-Postes Cloud Engine v5.5",
    description="Moteur réseau centralisé pour l'interconnexion en temps réel des caisses du magasin."
)

# Configuration de la sécurité réseau CORS pour toutes les caisses clientes
origines_autorisees = [
    origine.strip()
    for origine in os.environ.get("KASHFLOW_CORS_ORIGINS", "").split(",")
    if origine.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not origines_autorisees else origines_autorisees,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# --- SCHÉMAS RESEAU PYDANTIC COMMERCIAUX ---
class VenteSchemaReseau(BaseModel):
    reference_locale: str
    client: str
    article: str
    description_unique: str
    prix_ht: float
    quantite: int
    caissiere: str
    applique_tva_vente: int | None = None

class StockSchemaReseau(BaseModel):
    """Modèle réseau exclusif gérant pour injecter et propager les approvisionnements."""
    modele: str
    quantite_dispo: int


def verifier_cle_api(x_api_key: str | None = Header(default=None)):
    """Vérifie la clé d'accès de la boutique avant d'autoriser les échanges de caisse."""
    cle_attendue = str(os.environ.get("KASHFLOW_API_KEY", "")).strip()
    if not cle_attendue:
        return  
    if not x_api_key or not secrets.compare_digest(x_api_key, cle_attendue):
        raise HTTPException(status_code=401, detail="Clé API boutique invalide.")


@app.get("/")
def route_allumage_usine():
    """Adresse racine épurée de l'ancien code téléphone. Indique que le réseau est fonctionnel."""
    return JSONResponse(
        status_code=200,
        content={
            "statut": "Opérationnel",
            "moteur": "KashFlow Multi-Postes Engine v5.5",
            "message": "Le serveur Cloud est prêt. Liaison caisses locales active."
        }
    )
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - 2 SUR 2)
# =====================================================================

@app.post("/ventes/synchroniser", dependencies=[Depends(verifier_cle_api)])
def api_centraliser_vente(donnees: VenteSchemaReseau):
    """Centralise et traite informatiquement les transactions transmises par les caisses."""
    try:
        donnees.caissiere = donnees.caissiere.strip().lower()
        if donnees.prix_ht <= 0 or not 0 < donnees.quantite <= 1000:
            raise HTTPException(status_code=422, detail="Prix ou quantité invalide.")
            
        connexion = sqlite3.connect(data_base.DB_NAME)
        deja_sync = connexion.execute("SELECT id FROM ventes WHERE reference_locale = ?", (donnees.reference_locale,)).fetchone()
        connexion.close()
        if deja_sync:
            return {"statut": "Déjà synchronisé", "facture_id_cloud": deja_sync[0]}
            
        regime_tva = int(donnees.applique_tva_vente) if donnees.applique_tva_vente is not None else data_base.obtenir_regime_tva_employe(donnees.caissiere)

        total_ht = donnees.prix_ht * donnees.quantite
        tva_calculee = total_ht * (19.25 / 100) if regime_tva == 1 else 0.0
        total_ttc = total_ht + tva_calculee
        
        num_facture = data_base.enregistrer_vente_sql(
            client=donnees.client, 
            article=donnees.article, 
            desc_unique=donnees.description_unique, 
            mnt_ht=total_ht, 
            tva=tva_calculee, 
            ttc=total_ttc, 
            caissiere=donnees.caissiere, 
            reference_locale=donnees.reference_locale
        )
        return {"statut": "Synchronisé", "facture_id_cloud": num_facture}
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stocks/mettre_a_jour", dependencies=[Depends(verifier_cle_api)])
def api_mettre_a_jour_stock_central(stock: StockSchemaReseau):
    """
    📥 RÉCEPTEUR MULTI-POSTES :
    Enregistre l'approvisionnement ou l'effacement (quantité à 0) sur le Cloud PostgreSQL.
    """
    try:
        modele_propre = stock.modele.strip().lower()
        
        # 🟢 CONSTRUCTEUR : Si la quantité envoyée est 0, c'est que le gérant a supprimé l'article !
        if stock.quantite_dispo <= 0:
            connexion = sqlite3.connect(data_base.DB_NAME)
            connexion.execute("DELETE FROM stocks WHERE lower(modele) = ?", (modele_propre,))
            connexion.commit()
            connexion.close()
            return {"statut": "Succès", "message": f"Article '{modele_propre}' supprimé du Cloud."}
            
        # Sinon, on applique la mise à jour classique de l'approvisionnement
        data_base.forcer_mise_a_jour_stock_local(modele_propre, stock.quantite_dispo)
        return {"statut": "Succès", "message": f"Stock de '{modele_propre}' synchronisé."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stocks/etat", dependencies=[Depends(verifier_cle_api)])
def api_consulter_stocks_cloud():
    """
    📡 DIFFUSEUR INTERCONNEXION MULTI-POSTES :
    Renvoie l'inventaire en temps réel à l'ensemble des postes de caisse employés.
    """
    try:
        lignes = data_base.obtenir_tous_les_stocks_locaux()
        
        connexion = sqlite3.connect(data_base.DB_NAME)
        max_v_row = connexion.execute("SELECT MAX(ventes_cumulees) FROM stocks").fetchone()
        connexion.close()
        max_v = max_v_row[0] if max_v_row and max_v_row[0] is not None else 0

        rapport_stock = []
        for l in lignes:
            modele, quantite, ventes_cumulees = l
            seuil = 10 if ventes_cumulees == max_v else 5
            etat_alerte = "🚨 RUPTURE PROCHE" if quantite <= seuil else "🟢 Stock Confortable"
            
            rapport_stock.append({
                "article_modele": str(modele).strip(),
                "quantite_restante": int(quantite),
                "ventes_totales": int(ventes_cumulees),
                "seuil_alerte_applique": seuil,
                "statut_commande": etat_alerte,
            })
        return {"inventaire_magasin": rapport_stock}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ventes/statistiques", dependencies=[Depends(verifier_cle_api)])
def api_obtenir_statistiques(temporalite: str, cible: str):
    """Extrait l'analyse du chiffre d'affaires du Cloud pour la console gérant."""
    try:
        analyse = data_base.extraire_statistiques_avancees(temporalite, cible)
        return {
            "chiffre_affaires_ttc": f"{analyse['ca_total']:,} FCFA",
            "article_le_plus_vendu": str(analyse["produit_phare"]),
            "comparatif_performance_n_1": analyse["message_performance"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ventes/caissiere/{nom_caissiere}", dependencies=[Depends(verifier_cle_api)])
def api_historique_caissiere(nom_caissiere: str):
    """Renvoie les factures d'un agent pour contrôle financier inter-machines."""
    try:
        nom_caissiere = nom_caissiere.strip().lower()
        ventes = data_base.recuperer_ventes_par_caissiere(nom_caissiere)
        if not ventes:
            return {"total_ventes_effectuees": 0, "liste_ventes": []}
            
        liste_formatee = []
        for v in ventes:
            liste_formatee.append({
                "facture_no": v[0],
                "client": str(v[1]).upper(),
                "article": str(v[2]).upper(),
                "montant_ttc": f"{v[3]:,.0f} FCFA" if isinstance(v[3], (int, float)) else str(v[3]),
                "date": v[4],
                "heure": v[5],
            })
        return {
            "total_ventes_effectuees": len(liste_formatee),
            "liste_ventes": list(liste_formatee),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/employes/liste", dependencies=[Depends(verifier_cle_api)])
def api_liste_des_employes():
    """Extrait la liste textuelle propre du personnel du magasin."""
    try:
        liste_employes = data_base.recuperer_liste_tous_employes()
        return {"employes": [str(emp).strip().lower() for emp in liste_employes]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/systeme/mise-a-jour", dependencies=[Depends(verifier_cle_api)])
def api_distribuer_mise_a_jour():
    """
    📡 DISTRIBUTEUR DE CODE SOURCE :
    Permet aux applications de caisse de télécharger à distance la dernière version de app_visuel.py.
    """
    try:
        chemin_visuel = os.path.join(DOSSIER_DU_FICHIER, "app_visuel.py")
        if not os.path.exists(chemin_visuel):
            raise HTTPException(status_code=404, detail="Fichier de mise à jour introuvable sur le serveur.")
            
        # On lit le fichier de l'interface graphique en texte pur pour l'envoyer par le réseau
        with open(chemin_visuel, "r", encoding="utf-8") as f:
            code_source = f.read()
            
        return {
            "statut": "Succès",
            "version_cloud": "5.6",  # Tu pourras augmenter ce numéro quand tu feras des modifs
            "code": code_source
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# =====================================================================
# ENGINE CLOUD KASHKEEPER - MODULE PASSERELLE DE PAIEMENT AUTOMATIQUE
# =====================================================================

# 🟢 CONFIGURATION DE TES CLÉS CLOUD (Conservées à l'identique)
CAMPAY_USERNAME = os.getenv("CAMPAY_USERNAME", "fuA8YJK5y7w_iZPCKSWAVxWfGUGDRqLIeBdRt5zU-y6vzEAM9HC69h5p47A-ZboUUl6uyp55nhelsGIkU6fTpQ")
CAMPAY_PASSWORD = os.getenv("CAMPAY_PASSWORD", "Azmz4whioMs_GSVjHQvgApuu5S5-dKmz6_JSKZ66KKmyLoXmsIT4wQMuir78FGcz0UcP9RZgPQGMRAoNR0W_FA")

# 🟢 FIXATION CONSTRUCTEUR : Redirection stricte sur l'API Démo de la Sandbox
CAMPAY_BASE_URL = "https://campay.net"

# Dictionnaire de suivi des licences (Clé API de la boutique -> Date de fin)
BASE_LICENCES_CLOUD = {
    "SERGE_TECH_998877": "01/01/2026"
}

def obtenir_token_authentification_campay():
    """Demande un jeton d'accès temporaire (Token) à l'API Campay."""
    url = f"{CAMPAY_BASE_URL}/token/"
    payload = {
        "username": CAMPAY_USERNAME,
        "password": CAMPAY_PASSWORD
    }
    try:
        reponse = requests.post(url, json=payload, timeout=8)
        if reponse.status_code == 200:
            return reponse.json().get("token")
        return None
    except Exception:
        return None

@app.post("/licence/collecter-momo", dependencies=[Depends(verifier_cle_api)])
def api_declencher_collecte_momo(payload: dict, x_api_key: str = Header(...)):
    """📲 SIMULATEUR D'USINE CAMPAIGN : Force la réussite instantanée pour le test de Serge."""
    cle_boutique = x_api_key.strip()
    numero_telephone = payload.get("numero", "").strip()
    
    if not numero_telephone or len(numero_telephone) < 7:
        raise HTTPException(status_code=422, detail="Numéro Mobile Money de test invalide.")

    # 🟢 VECTEUR DE SIMULATION AUTOMATIQUE :
    # Si le numéro de test SUCCESS (237677777777 ou 677777777) est saisi, on valide directement !
    if "677777777" in numero_telephone or "699999999" in numero_telephone:
        date_actuelle_db = BASE_LICENCES_CLOUD.get(cle_boutique)
        try:
            date_base = datetime.strptime(date_actuelle_db, "%d/%m/%Y")
            if date_base < datetime.now():
                date_base = datetime.now()
        except Exception:
            date_base = datetime.now()
            
        # Le serveur calcule et prolonge automatiquement l'accès de la boutique de 30 jours
        nouvelle_echeance = (date_base + timedelta(days=30)).strftime("%d/%m/%Y")
        BASE_LICENCES_CLOUD[cle_boutique] = nouvelle_echeance
        
        return {
            "statut": "SUCCESS", 
            "reference_transaction": "MOMO-SIMU-2026-OK",
            "message": f"Félicitations ! Votre paiement de 1 FCFA a été validé par simulation.\nNouvelle échéance : {nouvelle_echeance}"
        }
    else:
        raise HTTPException(status_code=400, detail="Numéro de test invalide. Utilisez 237677777777 pour le succès.")
