# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Interconnectée - 1 SUR 3)
# =====================================================================
import sqlite3
import os
import logging
from datetime import datetime
import sys
# 📁 BASE DE DONNÉES DE LA CAISSE LOCALE FIXÉE SUR LE BUREAU



if getattr(sys, 'frozen', False):
    # Si le logiciel tourne en .exe, on cible le vrai dossier de l'exécutable
    DOSSIER_REEL = os.path.dirname(sys.executable)
else:
    # Si on teste dans VS Code, on reste dans le dossier actuel
    DOSSIER_REEL = os.path.dirname(os.path.abspath(__file__))

DB_NAME = os.path.join(DOSSIER_REEL, "gestion_caisse.db")
FICHIER_LOG = os.path.join(DOSSIER_REEL, "kashflow_debug.log")

# Configuration de la traçabilité d'usine
logging.basicConfig(
    filename=FICHIER_LOG,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def initialisation_systeme():
    """Initialise l'architecture SQLite complète pour le fonctionnement Multi-Postes."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    
    # 1. Table des Ventes Temporelles
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
        reference_locale TEXT UNIQUE
    )
    """)

    # Alignement préventif de la colonne réseau
    colonnes_ventes = [ligne[1] for ligne in curseur.execute("PRAGMA table_info(ventes)").fetchall()]
    if "reference_locale" not in colonnes_ventes:
        curseur.execute("ALTER TABLE ventes ADD COLUMN reference_locale TEXT")
        curseur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ventes_reference_locale ON ventes(reference_locale)")

    # File d'attente pour la synchronisation asynchrone des factures
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
    
    # 2. Table des Employés
    curseur.execute("""
    CREATE TABLE IF NOT EXISTS employes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identifiant TEXT UNIQUE NOT NULL,
        mot_de_passe TEXT NOT NULL,
        applique_tva INTEGER DEFAULT 1
    )
    """)
    
    # 3. Table de Configuration (Nom de la boutique)
    curseur.execute("""
    CREATE TABLE IF NOT EXISTS configuration (
        cle TEXT PRIMARY KEY,
        valeur TEXT NOT NULL
    )
    """)
    
    # 4. Table des Stocks Physiques Réels
    curseur.execute("""
    CREATE TABLE IF NOT EXISTS stocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modele TEXT UNIQUE NOT NULL,
        quantite_dispo INTEGER NOT NULL,
        ventes_cumulees INTEGER DEFAULT 0
    )
    """)
    
    # Produits électroniques injectés à l'allumage d'usine
    produits_usine = [
        ("tecno", 10, 0),
        
    ]
    for p in produits_usine:
        curseur.execute("INSERT OR IGNORE INTO stocks (modele, quantite_dispo, ventes_cumulees) VALUES (?, ?, ?)", p)
        
    connexion.commit()
    connexion.close()
# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Interconnectée - 2 SUR 3)
# =====================================================================

def configurer_compte_gerant_sql(code_secret):
    """Grave ou modifie le mot de passe secret de l'administrateur gérant."""
    try:
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("""
        INSERT OR REPLACE INTO employes (id, identifiant, mot_de_passe, applique_tva)
        VALUES (1, 'gerant', ?, 1)
        """, (code_secret.strip(),))
        connexion.commit()
        connexion.close()
        return True
    except Exception:
        return False

def ajouter_nouvel_employe_sql(identifiant, mot_de_passe, applique_tva):
    """Permet au patron d'ajouter un profil caissière avec son régime de TVA attitré."""
    try:
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("""
        INSERT INTO employes (identifiant, mot_de_passe, applique_tva)
        VALUES (?, ?, ?)
        """, (identifiant.strip().lower(), mot_de_passe.strip(), int(applique_tva)))
        connexion.commit()
        connexion.close()
        return True
    except sqlite3.IntegrityError:
        return False

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

def verifier_et_reduire_stock(modele_article, qte_vendue):
    """Vérifie le stock local, applique la baisse et calcule le seuil d'alerte."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT quantite_dispo, ventes_cumulees FROM stocks WHERE modele = ?", (modele_article,))
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
                    (nouveau_stock, nouvelles_ventes, modele_article))
    
    curseur.execute("SELECT MAX(ventes_cumulees) FROM stocks")
    max_v = curseur.fetchone()
    max_val = max_v[0] if max_v and max_v[0] is not None else 0
    
    seuil_dynamique = 10 if nouvelles_ventes == max_val else 5
    alerte_commande = nouveau_stock <= seuil_dynamique
    
    connexion.commit()
    connexion.close()
    return {"autorise": True, "restant": nouveau_stock, "alerte_patron": alerte_commande, "seuil": seuil_dynamique}
# =====================================================================
# MODULE 1 : data_base.py (Version Multi-Postes Interconnectée - 3 SUR 3)
# =====================================================================

def enregistrer_vente_sql(client, article, desc_unique, mnt_ht, tva, ttc, caissiere, reference_locale=None):
    """Enregistre la transaction en local avec horodatage millimétré."""
    try:
        maintenant = datetime.now()
        heure_exacte = maintenant.strftime("%H:%M")
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("""
        INSERT INTO ventes (client, article, description_unique, montant_ht, tva, total_ttc, caissiere, annee, mois, jour, heure, reference_locale)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (client, article, desc_unique, mnt_ht, tva, ttc, caissiere.strip().lower(), maintenant.year, maintenant.month, maintenant.day, heure_exacte, reference_locale))
        num_facture = curseur.lastrowid
        connexion.commit()
        connexion.close()
        return num_facture
    except Exception as e:
        logging.error("Erreur enregistrement vente locale : %s", e)
        return None

def mettre_en_attente_synchronisation(reference_locale, donnees):
    """Conserve une vente localement dans la file d'attente si le Cloud est injoignable."""
    import json
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
    import json
    connexion = sqlite3.connect(DB_NAME)
    lignes = connexion.execute(
        "SELECT id, reference_locale, donnees_json FROM synchronisations_en_attente ORDER BY id"
    ).fetchall()
    connexion.close()
    return [(ligne[0], ligne[1], json.loads(ligne[2])) for ligne in lignes]

def marquer_synchronisation_reussie(id_synchronisation, reference_locale):
    """Supprime la vente de la file d'attente et coche le statut synchro à 1."""
    connexion = sqlite3.connect(DB_NAME)
    connexion.execute("DELETE FROM synchronisations_en_attente WHERE id = ?", (id_synchronisation,))
    connexion.execute("UPDATE ventes SET synchro = 1 WHERE reference_locale = ?", (reference_locale,))
    connexion.commit()
    connexion.close()

def enregistrer_erreur_synchronisation(id_synchronisation, message):
    """Incrémente le compteur d'échecs et enregistre le rapport d'erreur réseau."""
    connexion = sqlite3.connect(DB_NAME)
    connexion.execute("UPDATE synchronisations_en_attente SET tentatives = tentatives + 1, derniere_erreur = ? WHERE id = ?", (str(message)[:500], id_synchronisation),)
    connexion.commit()
    connexion.close()

def extraire_statistiques_avancees(temporalite, valeur_cible):
    """Calcule le CA de la période et extrait l'article le plus vendu en local."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    annee_actuelle = datetime.now().year
    
    if temporalite == "JOUR":
        try:
            j, m, a = map(int, valeur_cible.split("/"))
            critere = "jour = ? AND mois = ? AND annee = ?"
            params_actuels = (j, m, a)
        except Exception:
            connexion.close()
            return {"ca_total": 0.0, "produit_phare": "Format invalide", "message_performance": "Format attendu: J/M/AAAA"}
    elif temporalite == "MOIS":
        m = int(valeur_cible)
        critere = "mois = ? AND annee = ?"
        params_actuels = (m, annee_actuelle)
    else:
        a = int(valeur_cible)
        critere = "annee = ?"
        params_actuels = (a,)

    curseur.execute(f"SELECT SUM(total_ttc) FROM ventes WHERE {critere}", params_actuels)
    r1 = curseur.fetchone()
    ca_actuel = r1[0] if r1 and r1[0] is not None else 0.0
    
    curseur.execute(f"SELECT article, COUNT(id) FROM ventes WHERE {critere} GROUP BY article ORDER BY COUNT(id) DESC LIMIT 1", params_actuels)
    top = curseur.fetchone()
    article_phare = f"{top[0]} ({top[1]} ventes)" if top else "Aucun article"
    connexion.close()
    
    return {
        "ca_total": round(ca_actuel, 2), 
        "produit_phare": article_phare, 
        "message_performance": "📊 Analyse comptable Pro active."
    }

def recuperer_ventes_par_caissiere(nom_caissiere):
    """Extrait l'historique complet d'une vendeuse spécifique sous forme de liste de tuples bruts."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT id, client, article, total_ttc, jour || '/' || mois || '/' || annee, heure FROM ventes WHERE caissiere = ? ORDER BY id DESC", (nom_caissiere.strip().lower(),))
    lignes = curseur.fetchall()
    connexion.close()
    return lignes

def recuper_tout_les_ventes():
    """Renvoie le registre général de toutes les transactions locales du magasin."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT id, client, article, total_ttc, jour || '/' || mois || '/' || annee, caissiere FROM ventes ORDER BY id DESC")
    lignes = curseur.fetchall()
    connexion.close()
    return lignes

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

def recuperer_nom_boutique_sql():
    """Va lire l'identité textuelle enregistrée de la boutique en texte pur."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("SELECT valeur FROM configuration WHERE cle = 'nom_boutique'")
    ligne = curseur.fetchone()
    connexion.close()
    return ligne[0] if ligne else None

def enregistrer_nom_boutique_sql(nom_magasin):
    """Grave définitivement l'en-tête du commerce en configuration."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    curseur.execute("INSERT OR REPLACE INTO configuration (cle, valeur) VALUES ('nom_boutique', ?)", (nom_magasin,))
    connexion.commit()
    connexion.close()

# =====================================================================
# 🟢 EXTENSIONS EXCLUSIVES INTERCONNEXION MULTI-POSTES EN TEMPS RÉEL
# =====================================================================

def obtenir_tous_les_stocks_locaux():
    """Renvoie l'ensemble de la table des stocks avec l'ID pour le ciblage chirurgical multi-caisses."""
    connexion = sqlite3.connect(DB_NAME)
    curseur = connexion.cursor()
    # 🟢 CONSTRUCTEUR : On extrait l'ID en premier pour permettre la suppression et l'ajout sans doublons
    curseur.execute("SELECT id, modele, quantite_dispo, ventes_cumulees FROM stocks ORDER BY id ASC")
    lignes = curseur.fetchall()
    connexion.close()
    return lignes

def forcer_mise_a_jour_stock_local(modele_article, nouvelle_quantite):
    """Écrase la quantité locale en forçant le nom en minuscules pour éviter les doublons de casse."""
    try:
        connexion = sqlite3.connect(DB_NAME)
        curseur = connexion.cursor()
        # 🟢 CONSTRUCTEUR : .strip().lower() sur le modèle empêche la création de doublons
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
