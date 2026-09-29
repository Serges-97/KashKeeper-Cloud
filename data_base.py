# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Pro - ÉTAPE 1 SUR 7)
# =====================================================================
import sqlite3
import os
import logging
from datetime import datetime
import sys
import json

# 📁 GESTION DYNAMIQUE DU CHEMIN DE LA BASE DE DONNÉES ET DES LOGS
if getattr(sys, 'frozen', False):
    # Si le logiciel tourne en .exe, on cible le vrai dossier de l'exécutable
    DOSSIER_REEL = os.path.dirname(sys.executable)
else:
    # Si on teste dans VS Code, on reste dans le dossier actuel
    DOSSIER_REEL = os.path.dirname(os.path.abspath(__file__))

DB_NAME = os.path.join(DOSSIER_REEL, "gestion_caisse.db")
FICHIER_LOG = os.path.join(DOSSIER_REEL, "kashflow_debug.log")

# Configuration de la traçabilité d'usine pour le débogage
logging.basicConfig(
    filename=FICHIER_LOG,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Pro - ÉTAPE 2 SUR 7)
# =====================================================================
def initialisation_systeme():
    """Initialise l'architecture SQLite complète avec les structures multi-articles et les RH."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    
    # 1. Table des Ventes (Mise à jour d'usine pour supporter les factures multi-articles)
    curseur.execute("""
    CREATE TABLE IF NOT EXISTS ventes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT NOT NULL,
        article TEXT NOT NULL,
        description_unique TEXT NOT NULL,
        montant_ht REAL NOT NULL,
        tva REAL NOT NULL,
        total_ttc REAL NOT NULL,
        caissiere TEXT NOT NULL,
        annee INTEGER NOT NULL,
        mois INTEGER NOT NULL,
        jour INTEGER NOT NULL,
        heure TEXT NOT NULL,
        synchro INTEGER DEFAULT 0,
        reference_locale TEXT UNIQUE,
        quantite INTEGER DEFAULT 1
    )
    """)

    # Alignement structurel préventif de la table ventes
    infos_table = connexion.execute("PRAGMA table_info(ventes)").fetchall()
    colonnes_ventes = [ligne[1] for ligne in infos_table]
    
    if "reference_locale" not in colonnes_ventes:
        curseur.execute("ALTER TABLE ventes ADD COLUMN reference_locale TEXT")
        curseur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ventes_reference_locale ON ventes(reference_locale)")
        
    if "quantite" not in colonnes_ventes:
        curseur.execute("ALTER TABLE ventes ADD COLUMN quantite INTEGER DEFAULT 1")

    # 2. File d'attente pour la synchronisation asynchrone Cloud
    curseur.execute("""
    CREATE TABLE IF NOT EXISTS synchronisations_en_attente (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference_locale TEXT UNIQUE NOT NULL,
        donnees_json TEXT NOT NULL,
        derniere_erreur TEXT,
        tentatives INTEGER DEFAULT 0,
        cree_le TEXT NOT NULL
    )
    """)
    
    # 3. Table des Employés (Intègre d'office la colonne salaire)
    curseur.execute("""
    CREATE TABLE IF NOT EXISTS employes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identifiant TEXT UNIQUE NOT NULL,
        mot_de_passe TEXT NOT NULL,
        applique_tva INTEGER DEFAULT 1,
        salaire REAL DEFAULT 0
    )
    """)

    # Alignement structurel préventif de la table employes
    infos_emp = connexion.execute("PRAGMA table_info(employes)").fetchall()
    colonnes_emp = [ligne[1] for ligne in infos_emp]
    if "salaire" not in colonnes_emp:
        curseur.execute("ALTER TABLE employes ADD COLUMN salaire REAL DEFAULT 0")
    
    # 4. Table de Configuration (Nom de la boutique)
    curseur.execute("""
    CREATE TABLE IF NOT EXISTS configuration (
        cle TEXT PRIMARY KEY,
        valeur TEXT NOT NULL
    )
    """)
    
    # 5. Table des Stocks Physiques Réels
    curseur.execute("""
    CREATE TABLE IF NOT EXISTS stocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modele TEXT UNIQUE NOT NULL,
        quantite_dispo INTEGER NOT NULL,
        prix_achat REAL DEFAULT 0,
        ventes_cumulees INTEGER DEFAULT 0
    )
    """)
    
    # Injection du produit d'allumage par défaut
    curseur.execute("INSERT OR IGNORE INTO stocks (modele, quantite_dispo, ventes_cumulees) VALUES ('tecno', 10, 0)")
    
    # 🟢 SÉCURITÉ CONSTRUCTEUR : Injection d'office du code d'usine serge2026
    curseur.execute("SELECT * FROM employes WHERE identifiant = 'gerant'")
    if curseur.fetchone() is None:
        curseur.execute("""
        INSERT INTO employes (id, identifiant, mot_de_passe, applique_tva, salaire)
        VALUES (1, 'gerant', 'serge2026', 1, 0)
        """)
        
    connexion.commit()
    connexion.close()
# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Pro - ÉTAPE 3 SUR 7)
# =====================================================================
def configurer_compte_gerant_sql(code_secret):
    """Grave ou modifie le mot de passe secret de l'administrateur gérant."""
    try:
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("""
        INSERT OR REPLACE INTO employes (id, identifiant, mot_de_passe, applique_tva, salaire)
        VALUES (1, 'gerant', ?, 1, 0)
        """, (code_secret.strip(),))
        connexion.commit()
        connexion.close()
        return True
    except Exception:
        return False

def ajouter_nouvel_employe_sql(identifiant, mot_de_passe, applique_tva, salaire=0.0):
    """Permet au patron d'ajouter un profil caissière avec son régime de TVA et son salaire."""
    try:
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("""
        INSERT INTO employes (identifiant, mot_de_passe, applique_tva, salaire)
        VALUES (?, ?, ?, ?)
        """, (identifiant.strip().lower(), mot_de_passe.strip(), int(applique_tva), float(salaire)))
        connexion.commit()
        connexion.close()
        return True
    except sqlite3.IntegrityError:
        return False

def modifier_salaire_employe_sql(id_employe, nouveau_salaire):
    """Met à jour de manière définitive le salaire d'un employé."""
    import sqlite3
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("UPDATE employes SET salaire = ? WHERE id = ?", (float(nouveau_salaire), int(id_employe)))
    connexion.commit()
    connexion.close()

def verifier_identifiants_sql(utilisateur, code_secret):
    """Vérifie la validité des accès saisis à l'écran de login."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT * FROM employes WHERE identifiant = ? AND mot_de_passe = ?", 
                    (utilisateur.strip().lower(), code_secret.strip()))
    trouve = curseur.fetchone()
    connexion.close()
    return trouve is not None

def obtenir_regime_tva_employe(utilisateur):
    """Renvoie 1 si l'employé connecté applique la TVA, 0 sinon."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT applique_tva FROM employes WHERE identifiant = ?", (utilisateur.strip().lower(),))
    res = curseur.fetchone()
    connexion.close()
    return res[0] if res else 1

def recuperer_liste_tous_employes():
    """Génère la liste textuelle propre pour alimenter le Combobox du gérant."""
    try:
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("SELECT identifiant FROM employes WHERE identifiant != 'gerant' ORDER BY identifiant ASC")
        lignes = curseur.fetchall()
        connexion.close()
        return [str(ligne[0]).strip().upper() for ligne in lignes if ligne and str(ligne[0]).strip()]
    except Exception:
        return []

def obtenir_tous_les_employes_complets():
    """Renvoie l'ensemble du personnel avec le salaire pour le tableau d'administration gérant."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT id, identifiant, 'CAISSIER' as role, salaire FROM employes WHERE identifiant != 'gerant' ORDER BY id ASC")
    lignes = curseur.fetchall()
    connexion.close()
    return lignes
# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Pro - ÉTAPE 4 SUR 7)
# =====================================================================
def obtenir_tous_les_stocks_locaux():
    """Renvoie la table des stocks pour l'interconnexion descendante des caissières."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT id, modele, quantite_dispo, ventes_cumulees FROM stocks ORDER BY id ASC")
    lignes = curseur.fetchall()
    connexion.close()
    return lignes

def obtenir_tous_les_stocks_locaux_complets():
    """Renvoie l'inventaire complet avec le prix d'achat secret réservé au gérant."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT id, modele, quantite_dispo, prix_achat FROM stocks ORDER BY id ASC")
    lignes = curseur.fetchall()
    connexion.close()
    return lignes

def forcer_mise_a_jour_stock_local(modele_article, nouvelle_quantite):
    """Écrase la quantité locale lors des rafraîchissements réseau caissière."""
    try:
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        nom_normalise = str(modele_article).strip().lower()
        curseur.execute("""
        INSERT INTO stocks (modele, quantite_dispo, ventes_cumulees)
        VALUES (?, ?, 0)
        ON CONFLICT(modele) DO UPDATE SET quantite_dispo = ?
        """, (nom_normalise, int(nouvelle_quantite), int(nouvelle_quantite)))
        connexion.commit()
        connexion.close()
        return True
    except Exception as e:
        logging.error("Erreur forçage stock local : %s", e)
        return False

def forcer_mise_a_jour_stock_local_avec_prix(modele, quantite, prix_achat=0):
    """Met à jour l'inventaire en intégrant le coût d'achat secret (Console Gérant)."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("""
        INSERT INTO stocks (modele, quantite_dispo, prix_achat) VALUES (?, ?, ?)
        ON CONFLICT(modele) DO UPDATE SET quantite_dispo = ?, prix_achat = ?
    """, (str(modele).strip().lower(), int(quantite), float(prix_achat), int(quantite), float(prix_achat)))
    connexion.commit()
    connexion.close()

def verifier_et_reduire_stock(modele_article, qte_vendue):
    """Vérifie le stock local, applique la baisse et calcule l'état de rupture."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT quantite_dispo, ventes_cumulees FROM stocks WHERE modele = ?", (str(modele_article).strip().lower(),))
    res = curseur.fetchone()
    
    if res is None:
        connexion.close()
        return {"autorise": False, "reason": "Article non répertorié."}
        
    stock_actuel, ventes_cumulees = res
    if stock_actuel < qte_vendue:
        connexion.close()
        return {"autorise": False, "reason": f"Stock insuffisant ! Il ne reste que {stock_actuel} pièces."}
        
    nouveau_stock = stock_actuel - qte_vendue
    nouvelles_ventes = ventes_cumulees + qte_vendue
    
    curseur.execute("UPDATE stocks SET quantite_dispo = ?, ventes_cumulees = ? WHERE modele = ?", 
                    (nouveau_stock, nouvelles_ventes, str(modele_article).strip().lower()))
    
    curseur.execute("SELECT MAX(ventes_cumulees) FROM stocks")
    max_v = curseur.fetchone()
    max_val = max_v[0] if max_v and max_v[0] is not None else 0
    
    seuil_dynamique = 10 if nouvelles_ventes == max_val else 5
    alerte_commande = nouveau_stock <= seuil_dynamique
    
    connexion.commit()
    connexion.close()
    return {"autorise": True, "restant": nouveau_stock, "alerte_patron": alerte_commande, "seuil": seuil_dynamique}
# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Pro - ÉTAPE 5 SUR 7)
# =====================================================================
def enregistrer_vente_sql(client, article, desc_unique, mnt_ht, tva, ttc, caissiere, reference_locale=None, quantite=1):
    """Enregistre la transaction (ligne unique ou bloc groupé multi-articles) en local."""
    try:
        maintenant = datetime.now()
        heure_exacte = maintenant.strftime("%H:%M")
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("""
        INSERT INTO ventes (client, article, description_unique, montant_ht, tva, total_ttc, caissiere, annee, mois, jour, heure, reference_locale, quantite)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (client, article, desc_unique, mnt_ht, tva, ttc, caissiere.strip().lower(), maintenant.year, maintenant.month, maintenant.day, heure_exacte, reference_locale, int(quantite)))
        num_facture = curseur.lastrowid
        connexion.commit()
        connexion.close()
        return num_facture
    except Exception as e:
        logging.error("Erreur enregistrement vente locale : %s", e)
        return None

def recuperer_ventes_par_caissiere(nom_caissiere):
    """Extrait l'historique complet des encaissements d'un agent."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT id, client, article, total_ttc, jour || '/' || mois || '/' || annee, heure FROM ventes WHERE caissiere = ? ORDER BY id DESC", (nom_caissiere.strip().lower(),))
    lignes = curseur.fetchall()
    connexion.close()
    return lignes

def recuper_tout_les_ventes():
    """Renvoie le registre général de toutes les transactions du magasin."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT id, client, article, total_ttc, jour || '/' || mois || '/' || annee, caissiere FROM ventes ORDER BY id DESC")
    lignes = curseur.fetchall()
    connexion.close()
    return lignes

def obtenir_registre_ventes_brutes():
    """Extrait le registre des ventes formaté pour l'exportation vers le tableur."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("""
        SELECT id, client, article, description_unique, montant_ht, tva, total_ttc, 
               caissiere, jour || '/' || mois || '/' || annee, heure, 
               CASE WHEN synchro = 1 THEN 'OUI' ELSE 'NON' END 
        FROM ventes ORDER BY id DESC
    """)
    lignes = curseur.fetchall()
    connexion.close()
    return lignes
# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Pro - ÉTAPE 6 SUR 7)
# =====================================================================
def mettre_en_attente_synchronisation(reference_locale, donnees):
    """Conserve une vente localement si Internet ou le serveur Render est indisponible."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute(
        """INSERT OR IGNORE INTO synchronisations_en_attente
        (reference_locale, donnees_json, cree_le) VALUES (?, ?, ?)""",
        (reference_locale, json.dumps(donnees, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
    )
    connexion.commit()
    connexion.close()

def recuperer_synchronisations_en_attente():
    """Récupère toutes les transactions bloquées en local pour tentative de renvoi."""
    connexion = sqlite3.connect(DB_NAME)
    lignes = connexion.execute(
        "SELECT id, reference_locale, donnees_json FROM synchronisations_en_attente ORDER BY id"
    ).fetchall()
    connexion.close()
    return [(ligne[0], ligne[1], json.loads(ligne[2])) for ligne in lignes]

def marquer_synchronisation_reussie(id_synchronisation, reference_locale):
    """Supprime la vente de la file d'attente et valide le statut synchro sur l'historique."""
    connexion = sqlite3.connect(DB_NAME)
    connexion.execute("DELETE FROM synchronisations_en_attente WHERE id = ?", (id_synchronisation,))
    connexion.execute("UPDATE ventes SET synchro = 1 WHERE reference_locale = ?", (reference_locale,))
    connexion.commit()
    connexion.close()

def enregistrer_erreur_synchronisation(id_synchronisation, message):
    """Incrémente le compteur d'échecs réseau d'une transaction."""
    connexion = sqlite3.connect(DB_NAME)
    connexion.execute("UPDATE synchronisations_en_attente SET tentatives = tentatives + 1, derniere_erreur = ? WHERE id = ?", (str(message)[:500], id_synchronisation),)
    connexion.commit()
    connexion.close()

def recuperer_nom_boutique_sql():
    """Va lire le nom officiel enregistré de l'entreprise."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT valeur FROM configuration WHERE cle = 'nom_boutique'")
    ligne = curseur.fetchone()
    connexion.close()
    return ligne[0] if ligne else None

def enregistrer_nom_boutique_sql(nom_magasin):
    """Grave définitivement l'en-tête commerciale de la boutique."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("INSERT OR REPLACE INTO configuration (cle, valeur) VALUES ('nom_boutique', ?)", (nom_magasin,))
    connexion.commit()
    connexion.close()
# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Pro - ÉTAPE 7 SUR 7)
# =====================================================================
def extraire_statistiques_avancees(temporalite, valeur_cible):
    """Analyse les tendances de ventes et extrait le produit phare (Zéro crash de conversion)."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    produit_phare = "Aucun"
    message_perf = "Aucune transaction enregistrée sur cette période."
    
    try:
        if temporalite == "ANNEE":
            curseur.execute("SELECT article, SUM(quantite) FROM ventes WHERE annee = ? GROUP BY article ORDER BY SUM(quantite) DESC LIMIT 1", (str(valeur_cible).strip(),))
        elif temporalite == "MOIS":
            m_propre = str(valeur_cible).strip().split("/")[0] if "/" in str(valeur_cible) else valeur_cible
            curseur.execute("SELECT article, SUM(quantite) FROM ventes WHERE mois = ? GROUP BY article ORDER BY SUM(quantite) DESC LIMIT 1", (str(m_propre).strip(),))
        else:
            p = str(valeur_cible).strip().split("/")
            if len(p) == 3:
                curseur.execute("SELECT article, SUM(quantite) FROM ventes WHERE jour = ? AND mois = ? AND annee = ? GROUP BY article ORDER BY SUM(quantite) DESC LIMIT 1", (str(p[0]), str(p[1]), str(p[2])))
            else:
                curseur.execute("SELECT article, SUM(quantite) FROM ventes WHERE jour = ? GROUP BY article ORDER BY SUM(quantite) DESC LIMIT 1", (str(valeur_cible).strip(),))
                
        ligne = curseur.fetchone()
        if ligne:
            produit_phare = str(ligne[0]).upper()
            message_perf = f"Activité optimale constatée. Le produit phare est {produit_phare}."
    except Exception as e:
        produit_phare = "Erreur"
        message_perf = f"Anomalie de traitement : {e}"
        
    connexion.close()
    return {"produit_phare": produit_phare, "message_performance": message_perf}


def extraire_benefice_net_periode(temporalite, cible):
    """Calcule le CA, extrait le coût d'achat du stock et soustrait les salaires RH."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    ca_total = 0.0
    total_cout_achat = 0.0
    ventes_filtrees = []
    
    try:
        if temporalite == "ANNEE":
            curseur.execute("SELECT article, quantite, total_ttc FROM ventes WHERE annee = ?", (str(cible).strip(),))
        elif temporalite == "MOIS":
            m_p = str(cible).strip().split("/")[0] if "/" in str(cible) else cible
            curseur.execute("SELECT article, quantite, total_ttc FROM ventes WHERE mois = ?", (str(m_p).strip(),))
        else:
            p = str(cible).strip().split("/")
            if len(p) == 3:
                curseur.execute("SELECT article, quantite, total_ttc FROM ventes WHERE jour = ? AND mois = ? AND annee = ?", (str(p[0]), str(p[1]), str(p[2])))
            else:
                curseur.execute("SELECT article, quantite, total_ttc FROM ventes WHERE jour = ?", (str(cible).strip(),))
        ventes_filtrees = curseur.fetchall()
    except Exception:
        ventes_filtrees = []
    
    for article, qte, ttc in ventes_filtrees:
        curseur.execute("SELECT prix_achat FROM stocks WHERE lower(modele) = ?", (str(article).lower().strip(),))
        row = curseur.fetchone()
        p_achat = float(row[0]) if (row and row[0] is not None) else 0.0
        ca_total += float(ttc)
        total_cout_achat += (p_achat * int(qte))
        
    # Extraction de la masse salariale mensuelle globale
    curseur.execute("SELECT SUM(salaire) FROM employes WHERE identifiant != 'gerant'")
    row_sal = curseur.fetchone()
    total_salaires = float(row_sal[0]) if (row_sal and row_sal[0] is not None) else 0.0

    if temporalite == "ANNEE":
        charges_personnel = total_salaires * 12
    elif temporalite == "JOUR":
        charges_personnel = round(total_salaires / 30, 2)
    else:
        charges_personnel = total_salaires

    benefice_net = ca_total - total_cout_achat - charges_personnel
    connexion.close()
    
    return {"ca_total": ca_total, "benefice_net": benefice_net, "frais_achat": total_cout_achat, "charges_salaires": charges_personnel}
