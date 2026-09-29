# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 1 SUR 10)
# =====================================================================
import sqlite3
import os
import secrets
import sys
import json
import requests
from datetime import datetime, timedelta
from pydantic import BaseModel
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 🔑 SÉCURITÉ CONSTRUCTEUR : Forcer Render à cibler le bon dossier physique
DOSSIER_DU_FICHIER = os.path.dirname(os.path.abspath(__file__))
if DOSSIER_DU_FICHIER not in sys.path:
    sys.path.insert(0, DOSSIER_DU_FICHIER)

import data_base

# Initialisation des structures de données centrales locales/cloud au démarrage
data_base.initialisation_systeme()

app = FastAPI(
    title="KashFlow Multi-Postes Cloud Engine v6.0",
    description="Moteur réseau centralisé pour l'interconnexion en temps réel des caisses et la gestion des abonnements."
)
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 2 SUR 10)
# =====================================================================
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

def verifier_cle_api(x_api_key: str | None = Header(default=None)):
    """Vérifie la clé d'accès de la boutique avant d'autoriser les échanges de caisse."""
    cle_attendue = str(os.environ.get("KASHFLOW_API_KEY", "")).strip()
    if not cle_attendue:
        return  
    if not x_api_key or not secrets.compare_digest(x_api_key, cle_attendue):
        raise HTTPException(status_code=401, detail="Clé API boutique invalide.")

@app.get("/")
def route_allumage_usine():
    """Adresse racine épurée. Indique que le réseau cloud de Serge est fonctionnel."""
    return JSONResponse(
        status_code=200,
        content={
            "statut": "Opérationnel",
            "moteur": "KashFlow Multi-Postes Engine v6.0",
            "message": "Le serveur Cloud est prêt. Liaison caisses locales active."
        }
    )
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 3 SUR 10)
# =====================================================================
class VenteSchemaReseau(BaseModel):
    """Modèle de réception des ventes supportant l'alignement multi-articles."""
    reference_locale: str
    client: str
    article: str
    description_unique: str
    prix_ht: float
    quantite: int
    caissiere: str
    applique_tva_vente: int | None = None

class StockSchemaReseau(BaseModel):
    """Modèle réseau exclusif gérant pour injecter et propager les approvisionnements avec prix d'achat."""
    modele: str
    quantite_dispo: int
    prix_achat: float | None = 0.0
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 4 SUR 10)
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
            reference_locale=donnees.reference_locale,
            quantite=donnees.quantite
        )
        return {"statut": "Synchronisé", "facture_id_cloud": num_facture}
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 5 SUR 10)
# =====================================================================
@app.post("/stocks/mettre_a_jour", dependencies=[Depends(verifier_cle_api)])
def api_mettre_a_jour_stock_central(stock: StockSchemaReseau):
    """Reçoit la mise à jour des stocks du gérant et la grave avec le prix d'achat."""
    try:
        modele_propre = stock.modele.strip().lower()
        if stock.quantite_dispo <= 0:
            connexion = sqlite3.connect(data_base.DB_NAME)
            connexion.execute("DELETE FROM stocks WHERE lower(modele) = ?", (modele_propre,))
            connexion.commit()
            connexion.close()
            return {"statut": "Succès", "message": f"Article '{modele_propre}' supprimé."}
            
        p_achat = stock.prix_achat if stock.prix_achat is not None else 0.0
        data_base.forcer_mise_a_jour_stock_local_avec_prix(modele_propre, stock.quantite_dispo, p_achat)
        return {"statut": "Succès", "message": f"Stock et prix de '{modele_propre}' synchronisés."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stocks/etat", dependencies=[Depends(verifier_cle_api)])
def api_consulter_stocks_cloud():
    """Diffuse l'état des stocks à l'ensemble des caisses connectées avec seuil d'alerte."""
    try:
        lignes = data_base.obtenir_tous_les_stocks_locaux()
        
        connexion = sqlite3.connect(data_base.DB_NAME)
        max_v_row = connexion.execute("SELECT MAX(ventes_cumulees) FROM stocks").fetchone()
        connexion.close()
        max_v = max_v_row[0] if max_v_row and max_v_row[0] is not None else 0

        rapport_stock = []
        for l in lignes:
            id_db, modele, quantite, ventes_cumulees = l
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
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 6 SUR 10)
# =====================================================================
@app.get("/ventes/statistiques", dependencies=[Depends(verifier_cle_api)])
def api_obtenir_statistiques(temporalite: str, cible: str):
    """Analyse les performances financières et le produit phare pour le gérant."""
    try:
        analyse = data_base.extraire_statistiques_avancees(temporalite, cible)
        calcul_gains = data_base.extraire_benefice_net_periode(temporalite, cible)
        return {
            "chiffre_affaires_ttc": f"{calcul_gains['ca_total']:,} FCFA",
            "benefice_net_reel": f"{calcul_gains['benefice_net']:,} FCFA",
            "article_le_plus_vendu": str(analyse["produit_phare"]),
            "comparatif_performance_n_1": analyse["message_performance"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ventes/caissiere/{nom_caissiere}", dependencies=[Depends(verifier_cle_api)])
def api_historique_caissiere(nom_caissiere: str):
    """Permet le contrôle et l'interconnexion de l'historique des caisses."""
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
        return {"total_ventes_effectuees": len(liste_formatee), "liste_ventes": list(liste_formatee)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/employes/liste", dependencies=[Depends(verifier_cle_api)])
def api_liste_des_employes():
    """Extrait la liste propre du personnel actif du magasin."""
    try:
        liste_employes = data_base.recuperer_liste_tous_employes()
        return {"employes": [str(emp).strip().lower() for emp in liste_employes]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 7 SUR 10)
# =====================================================================
@app.get("/systeme/mise-a-jour", dependencies=[Depends(verifier_cle_api)])
def api_distribuer_mise_a_jour():
    """Permet aux applications de caisse clientes de télécharger à distance la dernière version de app_visuel.py."""
    try:
        chemin_visuel = os.path.join(DOSSIER_DU_FICHIER, "app_visuel.py")
        if not os.path.exists(chemin_visuel):
            raise HTTPException(status_code=404, detail="Fichier de mise à jour introuvable sur le serveur.")
            
        with open(chemin_visuel, "r", encoding="utf-8") as f:
            code_source = f.read()
            
        return {
            "statut": "Succès",
            "version_cloud": "6.0",
            "code": code_source
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 8 SUR 10)
# =====================================================================
# Lecture sécurisée des clés réelles depuis ton tableau de bord Render Settings
CAMPAY_USERNAME = os.getenv("CAMPAY_USERNAME")
CAMPAY_PASSWORD = os.getenv("CAMPAY_PASSWORD")

# ADRESSE FINANCIÈRE DE PRODUCTION RÉELLE
CAMPAY_BASE_URL = "https://campay.net"

# Base de données centrale des licences stockée en mémoire volatile
BASE_LICENCES_CLOUD = {}

def obtenir_token_authentification_campay():
    """Demande un jeton d'accès temporaire de sécurité (Token) à l'API Campay Live."""
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
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 9 SUR 10)
# =====================================================================
@app.get("/licence/statut", dependencies=[Depends(verifier_cle_api)])
def api_verifier_licence_magasin(x_api_key: str = Header(...)):
    """🛡️ LOGIQUE SÉCURITÉ PRODUCTION : Calcule l'abonnement et la grâce de 3 jours."""
    cle_propre = x_api_key.strip()
    date_fin_texte = BASE_LICENCES_CLOUD.get(cle_propre)
    
    if not date_fin_texte:
        date_initiale = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
        BASE_LICENCES_CLOUD[cle_propre] = date_initiale
        return {"statut": "actif", "jours_restants": 30, "message": "Période initiale active."}
        
    try:
        date_expiration = datetime.strptime(date_fin_texte, "%d/%m/%Y")
        difference = (date_expiration - datetime.now()).days + 1
        
        if difference >= 0:
            return {"statut": "actif", "jours_restants": difference}
        elif -3 <= difference < 0:
            return {"statut": "grace", "jours_restants": (3 + difference)}
        else:
            return {"statut": "expire", "jours_restants": 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Multi-Postes Pro - ÉTAPE 10 SUR 10)
# =====================================================================
@app.post("/licence/collecter-momo", dependencies=[Depends(verifier_cle_api)])
def api_declencher_collecte_momo(payload: dict, x_api_key: str = Header(...)):
    """Déclenche le prélèvement MoMo ou génère le lien de paiement pour Carte Visa/Mastercard."""
    cle_boutique = x_api_key.strip()
    numero_telephone = payload.get("numero", "").strip()
    
    # 🟢 INTERCEPTATION BANCAIRE INTERNATIONALE
    if numero_telephone == "CARTE_BANCAIRE":
        token_campay = obtenir_token_authentification_campay()
        if not token_campay: raise HTTPException(status_code=500, detail="Erreur token.")
            
        url_lien = f"{CAMPAY_BASE_URL}/collect-web-link/"
        entetes = {"Authorization": f"Token {token_campay}", "Content-Type": "application/json"}
        payload_lien = {
            "amount": "14000", "currency": "XAF",
            "description": f"Abonnement International Visa/MC - Boutique {cle_boutique[:8]}",
            "external_reference": cle_boutique
        }
        try:
            reponse_lien = requests.post(url_lien, json=payload_lien, headers=entetes, timeout=10)
            if reponse_lien.status_code in [200, 201]:
                return {"statut": "SUCCESS_CARD", "lien_web": reponse_lien.json().get("link")}
            raise HTTPException(status_code=400, detail="Lien impossible.")
        except Exception as e: raise HTTPException(status_code=500, detail=str(e))

    if not numero_telephone or len(numero_telephone) < 9:
        raise HTTPException(status_code=422, detail="Numéro Mobile Money invalide à 9 chiffres.")
    if not numero_telephone.startswith("+"):
        numero_telephone = f"+{numero_telephone}" if numero_telephone.startswith("237") else f"+237{numero_telephone}"

    token_campay = obtenir_token_authentification_campay()
    if not token_campay: raise HTTPException(status_code=500, detail="Erreur d'authentification.")

    url_collecte = f"{CAMPAY_BASE_URL}/collect/"
    entetes = {"Authorization": f"Token {token_campay}", "Content-Type": "application/json"}
    donnees_collecte = {"amount": "14000", "currency": "XAF", "from": numero_telephone, "description": f"Abonnement Mensuel - Boutique {cle_boutique[:8]}", "external_reference": cle_boutique}

    try:
        reponse = requests.post(url_collecte, json=donnees_collecte, headers=entetes, timeout=10)
        if reponse.status_code in [200, 201]:
            return {"statut": "SUCCESS", "message": "Demande envoyée ! Tapez votre code PIN sur votre téléphone."}
        raise HTTPException(status_code=400, detail="La passerelle a refusé la transaction.")
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/licence/notification-paiement")
def api_reception_webhook_campay(payload: dict):
    """Webhook automatique appelé par CamPay dès la réussite du code PIN."""
    cle_boutique = payload.get("external_reference")
    if payload.get("status") == "SUCCESSFUL" and cle_boutique:
        date_actuelle_db = BASE_LICENCES_CLOUD.get(cle_boutique)
        try: date_base = datetime.strptime(date_actuelle_db, "%d/%m/%Y")
        except Exception: date_base = datetime.now()
        if date_base < datetime.now(): date_base = datetime.now()
        nouvelle_echeance = (date_base + timedelta(days=30)).strftime("%d/%m/%Y")
        BASE_LICENCES_CLOUD[cle_boutique] = nouvelle_echeance
        return {"status": "Mis à jour"}
    return {"status": "Ignoré"}
# =====================================================================
# FIN ABSOLUE DU CODE DU SERVEUR CLOUD RENDER - KASHFLOW ENGINE v6.0
# =====================================================================
