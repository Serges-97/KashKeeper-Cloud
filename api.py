# =====================================================================
# ENGINE CLOUD KASHFLOW - MODULE 3 : api.py (Version Production Manuelle Sécurisée)
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
from fastapi.responses import HTMLResponse


DOSSIER_DU_FICHIER = os.path.dirname(os.path.abspath(__file__))
if DOSSIER_DU_FICHIER not in sys.path:
    sys.path.insert(0, DOSSIER_DU_FICHIER)

import data_base

# Initialisation des structures locales
data_base.initialisation_systeme()

app = FastAPI(
    title="KashFlow Multi-Postes Cloud Engine v6.0",
    description="Moteur réseau centralisé pour l'interconnexion des caisses et le contrôle des licences par code PIN."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# Configuration de la base de données persistante des abonnements cloud
DB_LICENCES_CLOUD = os.path.join(DOSSIER_DU_FICHIER, "registre_licences_cloud.db")

def initialiser_base_licences_permanente():
    """Crée la table des abonnements de manière permanente sur le disque pour éviter le reset de Render."""
    conn = sqlite3.connect(DB_LICENCES_CLOUD)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS abonnements_magasin (
        cle_boutique TEXT PRIMARY KEY,
        date_expiration TEXT NOT NULL,
        statut_reglement TEXT DEFAULT 'actif'
    )
    """)
    conn.commit()
    conn.close()

# Allumage de sécurité du stockage des abonnements
initialiser_base_licences_permanente()

def verifier_cle_api(x_api_key: str | None = Header(default=None)):
    cle_attendue = str(os.environ.get("KASHFLOW_API_KEY", "")).strip()
    if not cle_attendue: return  
    if not x_api_key or not secrets.compare_digest(x_api_key, cle_attendue):
        raise HTTPException(status_code=401, detail="Clé API boutique invalide.")

@app.get("/")
def route_allumage_usine():
    return {"statut": "Opérationnel", "moteur": "KashFlow Multi-Postes Engine v6.0"}

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
    modele: str
    quantite_dispo: int
    prix_achat: float | None = 0.0

@app.post("/ventes/synchroniser", dependencies=[Depends(verifier_cle_api)])
def api_centraliser_vente(donnees: VenteSchemaReseau):
    try:
        donnees.caissiere = donnees.caissiere.strip().lower()
        if donnees.prix_ht <= 0 or not 0 < donnees.quantite <= 1000:
            raise HTTPException(status_code=422, detail="Prix ou quantité invalide.")
        connexion = sqlite3.connect(data_base.DB_NAME)
        deja_sync = connexion.execute("SELECT id FROM ventes WHERE reference_locale = ?", (donnees.reference_locale,)).fetchone()
        connexion.close()
        if deja_sync: return {"statut": "Déjà synchronisé", "facture_id_cloud": deja_sync[0]}
        
        regime_tva = int(donnees.applique_tva_vente) if donnees.applique_tva_vente is not None else data_base.obtenir_regime_tva_employe(donnees.caissiere)
        total_ht = donnees.prix_ht * donnees.quantite
        tva_calculee = total_ht * (19.25 / 100) if regime_tva == 1 else 0.0
        total_ttc = total_ht + tva_calculee
        
        num_facture = data_base.enregistrer_vente_sql(donnees.client, donnees.article, donnees.description_unique, total_ht, tva_calculee, total_ttc, donnees.caissiere, donnees.reference_locale, donnees.quantite)
        return {"statut": "Synchronisé", "facture_id_cloud": num_facture}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/stocks/mettre_a_jour", dependencies=[Depends(verifier_cle_api)])
def api_mettre_a_jour_stock_central(stock: StockSchemaReseau):
    try:
        modele_propre = stock.modele.strip().lower()
        if stock.quantite_dispo <= 0:
            connexion = sqlite3.connect(data_base.DB_NAME)
            connexion.execute("DELETE FROM stocks WHERE lower(modele) = ?", (modele_propre,))
            connexion.commit(); connexion.close()
            return {"statut": "Succès", "message": f"Article '{modele_propre}' supprimé."}
        p_achat = stock.prix_achat if stock.prix_achat is not None else 0.0
        data_base.forcer_mise_a_jour_stock_local_avec_prix(modele_propre, stock.quantite_dispo, p_achat)
        return {"statut": "Succès", "message": f"Stock synchronisé."}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/stocks/etat", dependencies=[Depends(verifier_cle_api)])
def api_consulter_stocks_cloud():
    try:
        lignes = data_base.obtenir_tous_les_stocks_locaux()
        connexion = sqlite3.connect(data_base.DB_NAME)
        max_v_row = connexion.execute("SELECT MAX(ventes_cumulees) FROM stocks").fetchone()
        connexion.close()
        max_v = max_v_row[0] if max_v_row and max_v_row[0] is not None else 0
        rapport_stock = []
        for id_db, modele, quantite, ventes_cumulees in lignes:
            seuil = 10 if ventes_cumulees == max_v else 5
            etat_alerte = "🚨 RUPTURE PROCHE" if quantite <= seuil else "🟢 Stock Confortable"
            rapport_stock.append({"article_modele": str(modele).strip(), "quantite_restante": int(quantite), "ventes_totales": int(ventes_cumulees), "seuil_alerte_applique": seuil, "statut_commande": etat_alerte})
        return {"inventaire_magasin": rapport_stock}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/ventes/statistiques", dependencies=[Depends(verifier_cle_api)])
def api_obtenir_statistiques(temporalite: str, cible: str):
    try:
        analyse = data_base.extraire_statistiques_avancees(temporalite, cible)
        calcul_gains = data_base.extraire_benefice_net_periode(temporalite, cible)
        return {"chiffre_affaires_ttc": f"{calcul_gains['ca_total']:,} FCFA", "benefice_net_reel": f"{calcul_gains['benefice_net']:,} FCFA", "article_le_plus_vendu": str(analyse["produit_phare"]), "comparatif_performance_n_1": analyse["message_performance"]}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/ventes/caissiere/{nom_caissiere}", dependencies=[Depends(verifier_cle_api)])
def api_historique_caissiere(nom_caissiere: str):
    try:
        ventes = data_base.recuperer_ventes_par_caissiere(nom_caissiere.strip().lower())
        liste_formatee = [{"facture_no": v[0], "client": str(v[1]).upper(), "article": str(v[2]).upper(), "montant_ttc": f"{v[3]:,.0f} FCFA" if isinstance(v[3], (int, float)) else str(v[3]), "date": v[4], "heure": v[5]} for v in ventes]
        return {"total_ventes_effectuees": len(liste_formatee), "liste_ventes": liste_formatee}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/employes/liste", dependencies=[Depends(verifier_cle_api)])
def api_liste_des_employes():
    try: return {"employes": [str(emp).strip().lower() for emp in data_base.recuperer_liste_tous_employes()]}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/systeme/mise-a-jour", dependencies=[Depends(verifier_cle_api)])
def api_distribuer_mise_a_jour():
    try:
        chemin_visuel = os.path.join(DOSSIER_DU_FICHIER, "app_visuel.py")
        if not os.path.exists(chemin_visuel): raise HTTPException(status_code=404, detail="Fichier introuvable.")
        with open(chemin_visuel, "r", encoding="utf-8") as f: code_source = f.read()
        return {"statut": "Succès", "version_cloud": "6.0", "code": code_source}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

CAMPAY_USERNAME = os.getenv("CAMPAY_USERNAME")
CAMPAY_PASSWORD = os.getenv("CAMPAY_PASSWORD")
CAMPAY_BASE_URL = "https://campay.net"

def obtenir_token_authentification_campay():
    try:
        reponse = requests.post(f"{CAMPAY_BASE_URL}/token/", json={"username": CAMPAY_USERNAME, "password": CAMPAY_PASSWORD}, timeout=8)
        return reponse.json().get("token") if reponse.status_code == 200 else None
    except Exception: return None

# =====================================================================
# 🛡️ ÉTAPE 9 : CONTRÔLE PERMANENT SUR DISQUE DES 32 JOURS D'ACCÈS
# =====================================================================
@app.get("/licence/statut", dependencies=[Depends(verifier_cle_api)])
def api_verifier_licence_magasin(x_api_key: str = Header(...)):
    """Calcule l'échéance à partir de la table permanente du disque cloud."""
    cle_propre = x_api_key.strip()
    conn = sqlite3.connect(DB_REEL := DB_LICENCES_CLOUD)
    curseur = conn.cursor()
    curseur.execute("SELECT date_expiration FROM abonnements_magasin WHERE cle_boutique = ?", (cle_propre,))
    row = curseur.fetchone()
    
    if not row:
        # Configuration initiale sécurisée du premier mois (30 jours)
        date_initiale = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
        curseur.execute("INSERT INTO abonnements_magasin (cle_boutique, date_expiration) VALUES (?, ?)", (cle_propre, date_initiale))
        conn.commit(); conn.close()
        return {"statut": "actif", "jours_restants": 30}
        
    date_fin_texte = row[0]
    conn.close()
    
    try:
        date_expiration = datetime.strptime(date_fin_texte, "%d/%m/%Y")
        difference = (date_expiration - datetime.now()).days + 1
        if difference >= 0: return {"statut": "actif", "jours_restants": difference}
        elif -2 <= difference < 0: return {"statut": "grace", "jours_restants": (2 + difference)}
        else:
            return {"statut": "expire", "jours_restants": 0}
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# 💳 ÉTAPE 10 : ENCAISSEMENT MANUEL AVEC RETRAIT CODE PIN SYSTEMATIQUE
# =====================================================================
@app.post("/licence/collecter-momo", dependencies=[Depends(verifier_cle_api)])
def api_declencher_collecte_momo(payload: dict, x_api_key: str = Header(...)):
    """Déclenche l'envoi d'un push USSD MoMo ou génère le lien Web crypté pour PaySika/Visa."""
    cle_boutique = x_api_key.strip()
    numero_telephone = payload.get("numero", "").strip()
    
    # 💳 CAS A : INTERCEPTATION BANCAIRE INTERNATIONALE (PaySika / Cartes)
    if numero_telephone == "CARTE_BANCAIRE":
        token_campay = obtenir_token_authentification_campay()
        if not token_campay: 
            raise HTTPException(status_code=500, detail="Erreur d'authentification token.")
        try:
            reponse_lien = requests.post(
                f"{CAMPAY_BASE_URL}/collect-web-link/", 
                json={"amount": "14000", "currency": "XAF", "description": f"Abonnement - {cle_boutique[:8]}", "external_reference": cle_boutique}, 
                headers={"Authorization": f"Token {token_campay}", "Content-Type": "application/json"}, 
                timeout=10
            )
            if reponse_lien.status_code in [200 , 201]: 
                return {"statut": "SUCCESS_CARD", "lien_web": reponse_lien.json().get("link")}
            raise HTTPException(status_code=400, detail="Lien PaySika/CamPay impossible à générer.")
        except Exception as e: 
            raise HTTPException(status_code=500, detail=str(e))

    # 📱 CAS B : INTERCEPTATION MOBILE MONEY CAMEROUN (CamPay - CODE PIN SYSTÉMATIQUE)
    if not numero_telephone or len(numero_telephone) < 9: 
        raise HTTPException(status_code=422, detail="Numéro Mobile Money invalide à 9 chiffres.")
    if not numero_telephone.startswith("+"): 
        numero_telephone = f"+{numero_telephone}" if numero_telephone.startswith("237") else f"+237{numero_telephone}"

    token_campay = obtenir_token_authentification_campay()
    if not token_campay: 
        raise HTTPException(status_code=500, detail="Erreur de liaison avec la passerelle.")
    try:
        reponse = requests.post(
            f"{CAMPAY_BASE_URL}/collect/", 
            json={"amount": "14000", "currency": "XAF", "from": numero_telephone, "description": f"Abonnement - {cle_boutique[:8]}", "external_reference": cle_boutique}, 
            headers={"Authorization": f"Token {token_campay}", "Content-Type": "application/json"}, 
            timeout=10
        )
        if reponse.status_code in [200 , 201]: 
            return {"statut": "SUCCESS", "message": "Demande envoyée ! Veuillez taper votre CODE PIN secret sur votre téléphone pour valider l'accès."}
        raise HTTPException(status_code=400, detail="La passerelle monétique est saturée. Réessayez.")
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/licence/notification-paiement")
def api_reception_webhook_campay(payload: dict):
    """Webhook automatique sécurisé appelé par CamPay dès la réussite matérielle de la saisie du code PIN."""
    cle_boutique = payload.get("external_reference")
    if payload.get("status") == "SUCCESSFUL" and cle_boutique:
        conn = sqlite3.connect(DB_LICENCES_CLOUD)
        curseur = conn.cursor()
        curseur.execute("SELECT date_expiration FROM abonnements_magasin WHERE cle_boutique = ?", (cle_boutique,))
        row = curseur.fetchone()
        date_actuelle = row[0] if row else (datetime.now()).strftime("%d/%m/%Y")
        
        try: 
            date_base = datetime.strptime(date_actuelle, "%d/%m/%Y")
        except Exception: 
            date_base = datetime.now()
            
        if date_base < datetime.now(): 
            date_base = datetime.now()
        
        # Le paiement ajoute 30 jours nets d'accès cumulables
        nouvelle_echeance = (date_base + timedelta(days=30)).strftime("%d/%m/%Y")
        curseur.execute("INSERT OR REPLACE INTO abonnements_magasin (cle_boutique, date_expiration) VALUES (?, ?)", (cle_boutique, nouvelle_echeance))
        conn.commit()
        conn.close()
        return {"status": "Mis à jour"}
    return {"status": "Ignoré"}

@app.get("/serge/generateur", response_class=HTMLResponse)
def page_generateur_visuel_en_dur(cle_client: str = None, mois: int = None, annee: int = None):
    """Génère l'interface web mobile et calcule la clé d'activation EN DUR en Python pur."""
    import hashlib
    import datetime
    
    maintenant = datetime.datetime.now()
    mois_par_defaut = mois if mois is not None else maintenant.month
    annee_par_defaut = annee if annee is not None else maintenant.year
    cle_par_defaut = cle_client.strip() if cle_client else "SERGE_TECH_998877"
    
    code_genere_html = ""
    
    # 🟢 CALCUL EN DUR : Si les données sont soumises, Python calcule directement la clé
    if cle_client and mois and annee:
        sel_secret = f"{cle_client.strip()}-{mois}-{annee}-KASHKEEPER-SERGE"
        signature_unitaire = hashlib.md5(sel_secret.encode("utf-8")).hexdigest().upper()[:8]
        code_final = f"KASH-{signature_unitaire[:4]}-{signature_unitaire[4:]}"
        
        code_genere_html = f"""
        <div style="margin-top: 20px; padding: 12px; background-color: #0f172a; border: 2px dashed #10b981; border-radius: 6px;">
            <div style="font-size: 0.75rem; color: #10b981; font-weight: bold; margin-bottom: 5px;">🔑 CODE WHATSAPP À ENVOYER :</div>
            <div style="font-size: 1.4rem; color: #ffffff; font-weight: bold; letter-spacing: 1px; font-family: monospace;">{code_final}</div>
        </div>
        """

    # Génération des options du menu déroulant des mois
    options_mois = ""
    for i in range(1, 13):
        selected = "selected" if i == int(mois_par_defaut) else ""
        options_mois += f'<option value="{i}" {selected}>{str(i).zfill(2)}</option>'

    # Génération des options du menu déroulant des années
    options_annees = ""
    for a in range (2026,2035): 
        selected = "selected" if a == int(annee_par_defaut) else ""
        options_annees += f'<option value="{a}" {selected}>{a}</option>'

    html_content = f""" 
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🛠️ KashKeeper - Support VIP</title>
        <style>
            body {{
                font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
                background-color: #0f172a;
                color: #cbd5e1;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                padding: 10px;
                box-sizing: border-box;
            }}
            .card {{
                background-color: #1e293b;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.5);
                width: 100%;
                max-width: 360px;
                text-align: center;
            }}
            h2 {{ color: #f59e0b; margin-top: 0; font-size: 1.3rem; letter-spacing: 0.5px; }}
            p {{ color: #94a3b8; font-size: 0.85rem; margin-bottom: 20px; }}
            .form-group {{ text-align: left; margin-bottom: 15px; }}
            label {{ display: block; font-size: 0.8rem; font-weight: bold; margin-bottom: 5px; color: #cbd5e1; }}
            input, select {{
                width: 100%;
                padding: 10px;
                background-color: #0f172a;
                border: 1px solid #475569;
                border-radius: 6px;
                color: white;
                font-size: 0.95rem;
                font-weight: bold;
                box-sizing: border-box;
                text-align: center;
            }}
            .btn {{
                width: 100%;
                padding: 12px;
                background-color: #f59e0b;
                border: none;
                border-radius: 6px;
                color: #0f172a;
                font-size: 1rem;
                font-weight: bold;
                cursor: pointer;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>KASHKEEPER MANAGER</h2>
            <p>Générateur d'Activation Manuelle SaaS</p>
            
            <!-- Formulier d'action natif qui recharge la page en dur -->
            <form action="/serge/generateur" method="get">
                <div class="form-group">
                    <label>ID OU CLÉ DU CLIENT :</label>
                    <input type="text" name="cle_client" value="{cle_par_defaut}" required>
                </div>
                
                <div class="form-group">
                    <label>MOIS DE CIBLE :</label>
                    <select name="mois">
                        {options_mois}
                    </select>
                </div>
                
                <div class="form-group">
                    <label>ANNÉE :</label>
                    <select name="annee">
                        {options_annees}
                    </select>
                </div>
                
                <button type="submit" class="btn">⚡ GÉNÉRER LA CLÉ SAAS</button>
            </form>
            
            {code_genere_html}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

