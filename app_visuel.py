# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 1 SUR 15)
# =====================================================================
import tkinter as tk
from tkinter import messagebox, simpledialog, Toplevel, ttk
import sqlite3
import logging
import os
import threading
import uuid
import requests
import data_base
import operation
import json 
import win32print
import win32ui
import webbrowser
from datetime import datetime, time, timedelta

# Lancement des configurations SQLite d'usine au démarrage du logiciel
data_base.initialisation_systeme()

# Variables globales de contrôle des privilèges et sécurité constructeur
SESSION_UTILISATEUR = "caissier"
NOM_CAISSIERE_ACTIVE = "Anonyme"
NOM_BOUTIQUE_FIXE = "KASHKEEPER"
CLE_MASTER_SERGE = "Je suis simple"

URL_API_KASHFLOW = ""
CLE_API_KASHFLOW = ""


# Variable globale pour stocker le panier multi-articles en cours de facturation
PANIER_FACTURE_EN_COURS = []
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 2 SUR 15)
# =====================================================================

def lancer_thread_synchronisation_asynchrone():
    """Démarre le moteur de synchronisation en arrière-plan sans bloquer la caissière."""
    def boucle_synchro_hybride():
        while True:
            try:
                # 1. Lire les ventes locales en attente (synchro = 0)
                conn = sqlite3.connect(data_base.DB_NAME)
                ventes_locales = conn.execute(
                    "SELECT reference_locale, client, article, description_unique, montant_ht, tva, total_ttc, caissiere, quantite FROM ventes WHERE synchro = 0"
                ).fetchall()
                conn.close()

                if ventes_locales and URL_API_KASHFLOW and CLE_API_KASHFLOW:
                    # 2. Envoyer le paquet global au serveur Render Cloud
                    for v in ventes_locales:
                        payload = {
                            "reference_locale": v[0],
                            "client": v[1],
                            "article": v[2],
                            "description_unique": v[3],
                            "prix_ht": v[4] / v[8] if v[8] > 0 else v[4], # Prix unitaire HT
                            "quantite": v[8],
                            "caissiere": v[7],
                            "applique_tva_vente": 1 if v[5] > 0 else 0
                        }
                        try:
                            reponse = requests.post(
                                f"{URL_API_KASHFLOW}/ventes/synchroniser",
                                json=payload,
                                headers={"X-API-Key": CLE_API_KASHFLOW},
                                timeout=15
                            )
                            if reponse.status_code == 200:
                                # 3. Si Render PostgreSQL a enregistré, on valide localement (synchro = 1)
                                conn_up = sqlite3.connect(data_base.DB_NAME)
                                conn_up.execute("UPDATE ventes SET synchro = 1 WHERE reference_locale = ?", (v[0],))
                                conn_up.commit()
                                conn_up.close()
                        except Exception:
                            continue # Si une transaction échoue, on continue la boucle
            except Exception as error_db:
                logging.warning("Moteur hybride asynchrone hors-ligne - Attente connexion : %s", error_db)
            
            # Vérification toutes les 30 secondes
            import time as time_system; time_system.sleep(30) 

    thread_sync = threading.Thread(target=boucle_synchro_hybride, daemon=True)
    thread_sync.start()

def imprimer_ticket_thermique_direct(client, liste_articles, total_ttc, caissiere):
    """Pilote physiquement les bobines de l'imprimante thermique détectée sur le port USB Windows."""
    try:
        nom_boutique = data_base.recuperer_nom_boutique_sql() or "KASHKEEPER BOUTIQUE"
        nom_boutique = str(nom_boutique).upper()
        
        # Sélection automatique de l'imprimante thermique par son nom de pilote
        nom_imprimante = win32print.GetDefaultPrinter()
        liste_imprimantes = [imp[2] for imp in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
        
        for imp in liste_imprimantes:
            if any(mot in imp.lower() for mot in ["thermal", "pos", "58", "80", "xp-"]):
                nom_imprimante = imp
                break

        date_heure = datetime.now().strftime("%d/%m/%Y  %H:%M")
        separateur = "--------------------------------"
        
        # Construction de l'en-tête du ticket
        ticket_texte = (
            f"{nom_boutique}\n"
            f"{separateur}\n"
            f"Date : {date_heure}\n"
            f"Caissiere : {str(caissiere).upper()}\n"
            f"Client : {str(client).upper()}\n"
            f"{separateur}\n"
            f"DÉSIGNATION       QTE    TOTAL\n"
        )
        
        # Ajout dynamique de chaque ligne d'article du panier
        for art in liste_articles:
            nom_art = str(art["article"]).upper()[:16]
            qte_art = art["quantite"]
            ttc_art = art["total_ttc"]
            ticket_texte += f"{nom_art:<17} {qte_art:<6} {ttc_art} F\n"
            
        # Pied de page du ticket
        ticket_texte += (
            f"{separateur}\n"
            f"TOTAL NET : {total_ttc} FCFA\n"
            f"{separateur}\n"
            f"Merci pour votre confiance !\n"
            f"A bientot.\n\n\n\n\n" # Sauts de ligne d'usine pour la découpe physique
        )

        hPrinter = win32print.OpenPrinter(nom_imprimante)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("KashKeeper_Ticket", None, "TEXT"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, ticket_texte.encode("utf-8"))
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        logging.warning("Erreur physique impression thermique directe : %s", e)
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 3 SUR 15)
# =====================================================================
def charger_configuration_externe():
    """Lit dynamiquement la configuration réseau du client (config.txt) à la racine de l'exécutable."""
    global URL_API_KASHFLOW, CLE_API_KASHFLOW
    
    # 🟢 AJUSTEMENT DE PRODUCTION : Détection universelle du dossier réel sous Windows (.exe ou .py)
    import sys
    if getattr(sys, 'frozen', False):
        dossier_prog = os.path.dirname(os.path.abspath(sys.executable))
    else:
        dossier_prog = os.path.dirname(os.path.abspath(__file__))
        
    fichier_config = os.path.join(dossier_prog, "config.txt")
    
    if not os.path.exists(fichier_config):
        with open(fichier_config, "w", encoding="utf-8") as f:
            f.write("# CONFIGURATION RESEAU KASHFLOW MANAGER \n")
            f.write("URL_API - https://kashkeeper-cloud.onrender.com \n")
            f.write("CLE_API - KASHFLOW_KEY_DEFAUT\n")
        return

    try:
        with open(fichier_config, "r", encoding="utf-8") as f:
            for ligne in f:
                ligne_propre = ligne.strip()
                if ligne_propre.startswith("#") or not ligne_propre:
                    continue
                
                separateur = "-" if "-" in ligne_propre else "="
                if separateur in ligne_propre:
                    cle, valeur = ligne_propre.split(separateur, 1)
                    cle_net = cle.strip()
                    valeur_net = valeur.strip()
                    
                    if cle_net == "URL_API":
                        URL_API_KASHFLOW = valeur_net.rstrip("/")
                    elif cle_net == "CLE_API":
                        CLE_API_KASHFLOW = valeur_net
    except Exception as e:
        print(f"[ERREUR CONFIG CONFIG.TXT] : {e}")

# Exécution immédiate du chargeur au démarrage de la caisse
charger_configuration_externe()

def normaliser_nom_caissiere(valeur):
    """Normalise un identifiant de caissière pour éviter les erreurs de typage ou d'espaces."""
    if valeur is None:
        return "anonyme"
    return str(valeur).strip().lower()
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 4 SUR 15)
# =====================================================================
def synchroniser_vente_cloud(reference_locale, donnees):
    """Envoie une vente au Cloud ou la conserve dans la file locale en cas de coupure."""
    donnees_alignees = {
        "reference_locale": reference_locale,
        "client": donnees["client"],
        "article": donnees["article"],
        "description_unique": donnees["description_unique"],
        "prix_ht": donnees["prix_ht"],
        "quantite": donnees["quantite"],
        "caissiere": donnees["caissiere"],
        "applique_tva_vente": donnees.get("applique_tva_vente", 1)
    }
    data_base.mettre_en_attente_synchronisation(reference_locale, donnees_alignees)
    synchroniser_file_cloud()

def synchroniser_file_cloud():
    """Réessaie les ventes en attente sans bloquer l'interface graphique Tkinter."""
    if not URL_API_KASHFLOW or not CLE_API_KASHFLOW:
        return

    for id_synchronisation, reference_locale, donnees in data_base.recuperer_synchronisations_en_attente():
        try:
            payload = donnees if isinstance(donnees, dict) else json.loads(donnees)
            reponse = requests.post(
                f"{URL_API_KASHFLOW}/ventes/synchroniser",
                json=payload,
                headers={"X-API-Key": CLE_API_KASHFLOW},
                timeout=8,
            )
            reponse.raise_for_status()
            data_base.marquer_synchronisation_reussie(id_synchronisation, reference_locale)
            logging.info("Vente synchronisée dans le Cloud: %s", reference_locale)
        except Exception as erreur:
            data_base.enregistrer_erreur_synchronisation(id_synchronisation, str(erreur))
            logging.warning("Synchronisation différée: %s", erreur)
            break
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 5 SUR 15)
# =====================================================================
def ouvrir_panneau_stock():
    """Interface d'inventaire moderne avec barre de défilement, boutons d'origine restaurés et prix d'achat secret."""
    if SESSION_UTILISATEUR != "gerant":
        messagebox.showerror("Accès Interdit", "Seul le gérant peut modifier l'inventaire.")
        return

    global entree_modele, entree_qte_stock, entree_prix_achat_stock

    def pushing_stock_cloud_complet(modele, quantite, prix_achat):
        if not URL_API_KASHFLOW or not CLE_API_KASHFLOW: return
        payload = {"modele": str(modele).strip().lower(), "quantite_dispo": int(quantite), "prix_achat": float(prix_achat)}
        threading.Thread(target=lambda: requests.post(f"{URL_API_KASHFLOW}/stocks/mettre_a_jour", json=payload, headers={"X-API-Key": CLE_API_KASHFLOW}, timeout=6), daemon=True).start()

    def action_ajouter_quantite(id_stock_cible, nom_article_cible):
        qte_a_ajouter = simpledialog.askinteger("Réapprovisionnement", f"Quantité à ajouter pour « {str(nom_article_cible).upper()} » :", parent=admin_stock, minvalue=1)
        if qte_a_ajouter is None: return

        id_propre = id_stock_cible[0] if isinstance(id_stock_cible, (list, tuple)) else id_stock_cible

        connexion = sqlite3.connect(data_base.DB_NAME)
        # 1. On applique l'ajout en local
        connexion.execute("UPDATE stocks SET quantite_dispo = quantite_dispo + ? WHERE id = ?", (qte_a_ajouter, id_propre))
        # 2. On récupère la nouvelle quantité cumulée totale
        row = connexion.execute("SELECT quantite_dispo, prix_achat FROM stocks WHERE id = ?", (id_propre,)).fetchone()
        qte_totale = row[0] if row else qte_a_ajouter
        p_achat = row[1] if row else 0.0
        connexion.commit()
        connexion.close()
        
        # 3. 🟢 ON ENVOIE LA QUANTITÉ TOTALE MIROIR SUR LE CLOUD
        if URL_API_KASHFLOW and CLE_API_KASHFLOW:
            payload = {"modele": str(nom_article_cible).strip().lower(), "quantite_dispo": int(qte_totale), "prix_achat": float(p_achat)}
            threading.Thread(target=lambda: requests.post(f"{URL_API_KASHFLOW}/stocks/mettre_a_jour", json=payload, headers={"X-API-Key": CLE_API_KASHFLOW}, timeout=10), daemon=True).start()
            
        rafraichir_tableau()
        messagebox.showinfo("Inventaire mis à jour", f"Le stock total a été augmenté à {qte_totale} pcs et synchronisé !")

    def rafraichir_tableau():
        for i in tableau_stocks.get_children():
            tableau_stocks.delete(i)
        lignes = data_base.obtenir_tous_les_stocks_locaux_complets()
        for id_db, modele, quantite, p_achat in lignes:
            tableau_stocks.insert("", tk.END, iid=str(id_db), values=(str(modele).strip().upper(), f"{quantite} pcs", f"{p_achat:,} FCFA"))

    def action_ajouter_quantite(id_stock_cible, nom_article_cible):
        qte = simpledialog.askinteger("Réapprovisionnement", f"Quantité à ajouter pour « {str(nom_article_cible).upper()} » :", parent=admin_stock, minvalue=1)
        if qte is None: return

        # 🟢 CORRIGÉ : Extraction propre de la variable ID
        id_propre = id_stock_cible[0] if isinstance(id_stock_cible, (list, tuple)) else id_stock_cible

        connexion = sqlite3.connect(data_base.DB_NAME)
        connexion.execute("UPDATE stocks SET quantite_dispo = quantite_dispo + ? WHERE id = ?", (qte, id_propre))
        row = connexion.execute("SELECT quantite_dispo, prix_achat FROM stocks WHERE id = ?", (id_propre,)).fetchone()
        qte_totale = row[0] if row else qte
        p_achat = row[1] if row else 0.0
        connexion.commit()
        connexion.close()
        
        pushing_stock_cloud_complet(str(nom_article_cible).strip().lower(), qte_totale, p_achat)
        rafraichir_tableau()
        messagebox.showinfo("Inventaire mis à jour", "Stock augmenté avec succès.")

    def action_ajouter_modele():
        modele = entree_modele.get().strip().lower()
        qte_texte = entree_qte_stock.get().strip()
        p_achat_txt = entree_prix_achat_stock.get().strip()
            
        if not all([modele, qte_texte, p_achat_txt]):
            messagebox.showwarning("Champs vides", "Veuillez remplir le modèle, la quantité et le prix d'achat.")
            return
                
        try:
            qte = int(qte_texte)
            p_achat = float(p_achat_txt)
            if qte <= 0 or p_achat < 0: raise ValueError
                
            # 🟢 ÉTAPE 1 : Écriture immédiate dans la base SQLite locale (Priorité terrain)
            connexion = sqlite3.connect(data_base.DB_NAME)
            curseur = connexion.cursor()
            curseur.execute("""
            INSERT INTO stocks (modele, quantite_dispo, prix_achat, ventes_cumulees) VALUES (?, ?, ?, 0)
            ON CONFLICT(modele) DO UPDATE SET quantite_dispo = quantite_dispo + ?, prix_achat = ?
            """, (modele, qte, p_achat, qte, p_achat))
            connexion.commit()
            connexion.close()
            
            # Étape 2 : Rafraîchissement visuel instantané du tableau à l'écran
            rafraichir_tableau()
            messagebox.showinfo("Inventaire Mis à jour", f"L'article '{modele.upper()}' a été enregistré localement avec succès !")
            entree_modele.delete(0, tk.END); entree_qte_stock.delete(0, tk.END); entree_prix_achat_stock.delete(0, tk.END)
            entree_modele.focus()

            # 🟢 ÉTAPE 3 : Propulsion Cloud synchrone au format de l'objet Pydantic StockSchemaReseau
            if URL_API_KASHFLOW and CLE_API_KASHFLOW:
                payload_produit = {
                    "modele": modele,
                    "quantite_dispo": qte,
                    "prix_achat": p_achat
                }
                def envoi_cloud_securise():
                    try:
                        reponse = requests.post(
                            f"{URL_API_KASHFLOW}/stocks/mettre_a_jour", 
                            json=payload_produit, 
                            headers={"X-API-Key": CLE_API_KASHFLOW}, 
                            timeout=15
                        )
                        if reponse.status_code == 200:
                            print(f"📡 [CLOUD] Synchronisation d'inventaire réussie pour {modele.upper()}")
                        else:
                            print(f"⚠️ [CLOUD] Échec d'authentification ou de routage, code : {reponse.status_code}")
                    except Exception as e:
                        print(f"📡 [CLOUD] Mode asynchrone - Écrit en local uniquement : {e}")
                
                # Exécution asynchrone pour ne pas faire geler l'interface graphique de la caisse
                threading.Thread(target=envoi_cloud_securise, daemon=True).start()

        except ValueError:
            messagebox.showerror("Erreur", "Données numériques invalides.")



# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 6 SUR 15)
# =====================================================================
    def action_supprimer_modele():
        selection = tableau_stocks.selection()
        if not selection:
            messagebox.showwarning("Sélection manquante", "Sélectionnez une ligne dans le tableau à supprimer.")
            return
            
        id_unique_ligne = selection[0]
        item = tableau_stocks.item(id_unique_ligne)
        valeurs = item["values"]
        nom_article = valeurs[0] if valeurs else "article"

        if not messagebox.askyesno("Suppression Définitive", f"🚨 ATTENTION :\nVoulez-vous supprimer définitivement « {nom_article} » ?"): 
            return

        # Suppression locale SQLite
        connexion = sqlite3.connect(data_base.DB_NAME)
        connexion.execute("DELETE FROM stocks WHERE id = ?", (id_unique_ligne,))
        connexion.commit()
        connexion.close()

        # 🟢 APPEL DE LA ROUTE DE SUPPRESSION DÉFINITIVE SUR RENDER
        if URL_API_KASHFLOW and CLE_API_KASHFLOW:
            payload_suppr = {"modele": str(nom_article).lower()}
            threading.Thread(target=lambda: requests.post(f"{URL_API_KASHFLOW}/stocks/supprimer_definitif", json=payload_suppr, headers={"X-API-Key": CLE_API_KASHFLOW}, timeout=10), daemon=True).start()

        messagebox.showinfo("Succès", "L'article a été supprimé définitivement !")
        rafraichir_tableau()

        connexion = sqlite3.connect(data_base.DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("DELETE FROM stocks WHERE id = ?", (id_unique_ligne,))
        article_supprime = curseur.rowcount > 0
        connexion.commit()
        connexion.close()

        if article_supprime:
            pushing_stock_cloud_complet(str(nom_article).lower(), 0, 0)
            messagebox.showinfo("Succès", "d'article retirée avec succès.")
            rafraichir_tableau()

    def action_clic_bouton_quantite():
        selection = tableau_stocks.selection()
        if not selection:
            messagebox.showwarning("Sélection manquante", "Veuillez cliquer sur une ligne du tableau d'abord.")
            return
        id_cible = selection
        nom_article = tableau_stocks.item(id_cible)["values"]
        action_ajouter_quantite(id_cible, nom_article)

    admin_stock = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    admin_stock.title("📦 Gestion des Stocks - Sécurisée par ID")
    admin_stock.geometry("560x580")
    admin_stock.configure(bg="#f8fafc")
    admin_stock.resizable(False, False)
    admin_stock.grab_set()

    tk.Label(admin_stock, text="INVENTAIRE DES PRODUITS EN STOCK", font=("Helvetica", 11, "bold"), bg="#0f766e", fg="white", pady=8).pack(fill=tk.X)
    cadre_conteneur = tk.Frame(admin_stock, bg="#f8fafc")
    cadre_conteneur.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    tableau_stocks = ttk.Treeview(cadre_conteneur, columns=("Article", "Quantite", "PrixAchat"), show="headings", height=10)
    tableau_stocks.heading("Article", text="DÉSIGNATION DE L'ARTICLE")
    tableau_stocks.heading("Quantite", text="STOCK DISPONIBLE")
    tableau_stocks.heading("PrixAchat", text="PRIX D'ACHAT UNITAIRE")
    tableau_stocks.column("Article", width=240, anchor=tk.W)
    tableau_stocks.column("Quantite", width=110, anchor=tk.CENTER)
    tableau_stocks.column("PrixAchat", width=160, anchor=tk.CENTER)

    defilement = ttk.Scrollbar(cadre_conteneur, orient="vertical", command=tableau_stocks.yview)
    tableau_stocks.configure(yscrollcommand=defilement.set)
    tableau_stocks.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    defilement.pack(side=tk.RIGHT, fill=tk.Y)

    tk.Button(admin_stock, text="➕ AJOUTER QUANTITÉ AU PRODUIT SÉLECTIONNÉ", font=("Helvetica", 9, "bold"), bg="#0f766e", fg="white", command=action_clic_bouton_quantite).pack(fill=tk.X, padx=15, pady=2)

    cadre_ajout = tk.LabelFrame(admin_stock, text="Créer ou Approvisionner un Article", font=("Helvetica", 9, "bold"), bg="#f8fafc", padx=10, pady=6)
    cadre_ajout.pack(fill=tk.X, padx=15, pady=10)

    tk.Label(cadre_ajout, text="Nom de l'article :", bg="#f8fafc").pack(anchor=tk.W)
    entree_modele = tk.Entry(cadre_ajout, font=("Helvetica", 10))
    entree_modele.pack(fill=tk.X, pady=2)

    tk.Label(cadre_ajout, text="Quantité reçue :", bg="#f8fafc").pack(anchor=tk.W)
    entree_qte_stock = tk.Entry(cadre_ajout, font=("Helvetica", 10))
    entree_qte_stock.pack(fill=tk.X, pady=2)

    tk.Label(cadre_ajout, text="Prix d'Achat Unitaire secret (FCFA) :", bg="#f8fafc").pack(anchor=tk.W)
    entree_prix_achat_stock = tk.Entry(cadre_ajout, font=("Helvetica", 10))
    entree_prix_achat_stock.pack(fill=tk.X, pady=2)

    # Liens clavier Entrée pour le formulaire d'inventaire
    entree_modele.bind("<Return>", lambda event: entree_qte_stock.focus())
    entree_qte_stock.bind("<Return>", lambda event: entree_prix_achat_stock.focus())
    entree_prix_achat_stock.bind("<Return>", lambda event: action_ajouter_modele())

    cadre_actions = tk.Frame(cadre_ajout, bg="#f8fafc")
    cadre_actions.pack(fill=tk.X, pady=6)
    tk.Button(cadre_actions, text="📥 ENREGISTRER / FUSIONNER", bg="#10b981", fg="white", font=("Helvetica", 9, "bold"), command=action_ajouter_modele).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    tk.Button(cadre_actions, text="🗑 SUPPRIMER LIGNE SÉLECTIONNÉE", bg="#dc2626", fg="white", font=("Helvetica", 9, "bold"), command=action_supprimer_modele).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

    rafraichir_tableau()
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 7 SUR 15)
# =====================================================================
def ouvrir_panneau_historique():
    """Tableau de bord d'analyse du Chiffre d'Affaires et du Bénéfice Net déduisant les salaires."""
    if SESSION_UTILISATEUR != "gerant":
        messagebox.showerror("Accès Interdit", "Seul le gérant a accès aux rapports financiers.")
        return

    def action_exporter_registre_excel():
        """Génère un rapport d'audit CSV d'usine détaillé en éclatant chaque article des factures de gros sur une ligne unique."""
        import csv
        import re
        dossier_actuel = os.path.dirname(os.path.abspath(__file__))
        horodatage = datetime.now().strftime("%d_%m_%Y_%H%M")
        nom_fichier_csv = os.path.join(dossier_actuel, f"KashKeeper_Rapport_Ventes_{horodatage}.csv")
        
        try:
            ventes_brutes = data_base.obtenir_registre_ventes_brutes()
            if not ventes_brutes:
                messagebox.showwarning("Registre vide", "Aucune transaction enregistrée.")
                return
                
            with open(nom_fichier_csv, mode="w", newline="", encoding="utf-8-sig") as f:
                ecrivain = csv.writer(f, delimiter=";")
                # En-tête professionnelle réajustée
                ecrivain.writerow([
                    "N° FACTURE", "CLIENT", "ARTICLE / MODELE", "QUANTITÉ", 
                    "MONTANT TOTAL TTC (FCFA)", "CAISSIERE EMETTEUR", "DATE FACTURATION", "HEURE", "SYNCHRONISÉ CLOUD"
                ])
                
                for ligne in ventes_brutes:
                    num_facture = ligne[0]
                    client = ligne[1]
                    article_brut = ligne[2]
                    total_ttc = ligne[6]
                    caissiere = ligne[7]
                    date_f = ligne[8]
                    heure_f = ligne[9]
                    synchro = ligne[10]
                    
                    # Éclatement de la cellule si elle contient plusieurs marchandises (Vente en gros)
                    lignes_articles = article_brut.split(", ")
                    for art_ligne in lignes_articles:
                        # On extrait proprement le nom pur du modèle et sa quantité
                        match_nom = re.match(r"^(.*?)\s*\(X\d+\)", art_ligne, re.IGNORECASE)
                        nom_pur = match_nom.group(1).strip().upper() if match_nom else art_ligne.strip().upper()
                        
                        match_qte = re.search(r"\(X(\d+)\)", art_ligne, re.IGNORECASE)
                        qte_pure = int(match_qte.group(1)) if match_qte else 1
                        
                        # Écriture d'une ligne dédiée et aérée pour cet article spécifique dans le tableur Excel
                        ecrivain.writerow([
                            num_facture, client, nom_pur, qte_pure, 
                            total_ttc, caissiere, date_f, heure_f, synchro
                        ])
                    
            messagebox.showinfo("Exportation Réussie", f" Bars RAPPORT COMPTABLE GÉNÉRÉ !\n\nChaque article a été listé ligne par ligne avec succès :\n« {nom_fichier_csv} »")
        except Exception as e:
            messagebox.showerror("Erreur d'écriture", f"Impossible d'exporter le fichier Excel :\n{e}")


    def action_charger_statistiques():
        tempo = select_tempo.get()
        cible = entree_cible.get().strip()
        
        if not cible:
            messagebox.showwarning("Critère manquant", "Veuillez entrer une valeur cible (ex: 29/09/2026, 09/2026, 2026).")
            return
            
        try:
            statistiques = data_base.extraire_statistiques_avancees(tempo, cible)
            calcul_gains = data_base.extraire_benefice_net_periode(tempo, cible)
            
            # 🟢 AFFICHAGE COMPTABLE NET COHÉRENT
            # 🟢 CORRIGÉ : Affichage unifié du Chiffre d'Affaires global
            label_ca.config(
                text=f"📊 CHIFFRE D'AFFAIRES GLOBAL TTC : {calcul_gains['ca_total']:,} FCFA", 
                bg="#0f766e", 
                fg="white",
                font=("Helvetica", 11, "bold")
            )
            
            # 🟢 CORRIGÉ : Injection du BÉNÉFICE NET RÉEL calculé sur la période ciblée
            label_top.config(
                text=f"🔥 Produit Phare : {statistiques['produit_phare']} | 💸 BÉNÉFICE NET RÉEL : {calcul_gains['benefice_net']:,} FCFA\n"
                     f"📦 Coût d'achat stock : {calcul_gains['frais_achat']:,} FCFA | 👥 Charges salariales : {calcul_gains['charges_salaires']:,} FCFA",
                font=("Helvetica", 9, "bold")
            )

            label_perf.config(text=statistiques['message_performance'])
            
            # 🟢 SYNCHRONISATION SYNCHRONISÉE : On force la grille du bas à se caler immédiatement sur la même cible
            action_afficher_tout_historique()
        except Exception as e:
            messagebox.showerror("Erreur d'analyse", f"Impossible de charger les données financières :\n{e}")

            
            
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 8 SUR 15)
# =====================================================================

    # =====================================================================
    # 🟢 POP-UP DE DOUBLE-CLIC : Affiche le détail complet d'une facture de gros
    # =====================================================================
    def action_double_clic_detail_facture(event):
        """Ouvre une mini-fenêtre propre affichant la liste complète des articles sans aucune coupure textuelle."""
        selection = grille_audit.selection()
        if not selection: return
        
        ligne_id = selection[0]
        valeurs = grille_audit.item(ligne_id)["values"]
        
        num_facture = valeurs[0]
        client_nom = valeurs[1]
        # 🟢 RECONSTRUCTION DU TEXTE : On récupère la description complète stockée en cache caché ou reconstruite
        articles_complets = valeurs[2]
        net_ttc = valeurs[3]
        date_v = valeurs[4]
        caissiere_v = valeurs[5]
        
        pop_detail = Toplevel(audit)
        pop_detail.title(f"📄 Détail Facture de Gros #{str(num_facture).zfill(4)}")
        pop_detail.geometry("460x280")
        pop_detail.configure(bg="#f8fafc")
        pop_detail.grab_set()
        
        tk.Label(pop_detail, text=f"FACTURE #{str(num_facture).zfill(4)} - {client_nom}", font=("Helvetica", 10, "bold"), bg="#1e293b", fg="white", pady=6).pack(fill=tk.X)
        
        cadre_corps = tk.Frame(pop_detail, bg="#f8fafc", padx=15, pady=10)
        cadre_corps.pack(fill=tk.BOTH, expand=True)
        
        texte_details = tk.Text(cadre_corps, font=("Helvetica", 10), bg="white", bd=2, wrap=tk.WORD)
        texte_details.pack(fill=tk.BOTH, expand=True)
        
        # Récupération de la chaîne brute stockée dans l'élément d'origine pour afficher l'article masqué (TECNO)
        id_item_selectionne = grille_audit.selection()[0]
        for v_origin in data_base.recuper_tout_les_ventes():
            if isinstance(v_origin, (tuple, list)) and str(v_origin[0]) == str(num_facture):
                articles_complets = str(v_origin[2]).upper()
                break
                
        contenu_affichage = f"📅 DATE DE LA VENTE : {date_v}\n" \
                            f"👥 CAISSIÈRE ÉMETTRICE : {caissiere_v}\n" \
                            f"💳 NET TTC À PAYER : {net_ttc}\n" \
                            f"----------------------------------------\n" \
                            f"📦 LISTE DES MARCHANDISES COMPLÈTE :\n{articles_complets.replace(', ', '\n')}"
                            
        texte_details.insert(tk.END, contenu_affichage)
        texte_details.config(state=tk.DISABLED)
        
        tk.Button(pop_detail, text="❌ FERMER", bg="#dc2626", fg="white", font=("Helvetica", 9, "bold"), command=pop_detail.destroy).pack(fill=tk.X, pady=5)

    def action_filtrer_par_vendeuse():
        """Filtre l'historique global du gérant en combinant la caissière sélectionnée et les critères temporels stricts."""
        nom_vendeuse = normaliser_nom_caissiere(select_vendeuse.get())
        if not nom_vendeuse or nom_vendeuse == "anonyme": return
            
        for i in grille_audit.get_children(): 
            grille_audit.delete(i)
            
        ventes_filtrees = data_base.recuperer_ventes_par_caissiere(nom_vendeuse)
        
        # Récupération des critères temporels du gérant
        valeur_temporelle = entree_cible.get().strip()
        periode_choisie = select_tempo.get() # "JOUR", "MOIS" ou "ANNEE"
        
        total_ca_cible = 0.0

        for index, v in enumerate(ventes_filtrees, start=1):
            if isinstance(v, (tuple, list)) and len(v) >= 4:
                num_id = v[0]
                client_nom = str(v[1]).upper()
                articles_bruts = str(v[2]).upper()
                net_ttc_total = f"{float(v[6]):,} FCFA" if len(v) > 6 else f"{float(v[3]):,} FCFA"
                
                # Extraction de la vraie date DD/MM/YYYY
                date_facture = str(v[8]).strip() if len(v) > 8 else (str(v[4]).strip() if len(v) > 4 else "29/09/2026")
                caissiere_emetteur = str(v[7]).upper() if len(v) > 7 else (str(v[5]).upper() if len(v) > 5 else nom_vendeuse.upper())
                
                # 🟢 APPLICATION DU FILTRAGE TEMPOREL ULTRA-STRICT DEMANDÉ
                if valeur_temporelle:
                    garder_ligne = False
                    if periode_choisie == "JOUR" and date_facture == valeur_temporelle:
                        garder_ligne = True
                    elif periode_choisie == "MOIS" and date_facture.endswith(valeur_temporelle if valeur_temporelle.startswith("/") else f"/{valeur_temporelle}"):
                        garder_ligne = True
                    elif periode_choisie == "ANNEE" and date_facture.endswith(valeur_temporelle):
                        garder_ligne = True
                        
                    if not garder_ligne:
                        continue

                articles_visuels = articles_bruts if len(articles_bruts) < 32 else articles_bruts[:30] + "..."
                grille_audit.insert("", tk.END, values=(num_id, client_nom, articles_visuels, net_ttc_total, date_facture, caissiere_emetteur))
                
                try:
                    prix_brut = float(v[6]) if len(v) > 6 else float(v[3])
                    total_ca_cible += prix_brut
                except Exception:
                    pass
            else:
                num_id = str(index)
                client_nom = "CLIENT UNIQUE"
                articles_bruts = str(v).upper()
                articles_visuels = articles_bruts if len(articles_bruts) < 32 else articles_bruts[:30] + "..."
                grille_audit.insert("", tk.END, values=(num_id, client_nom, articles_visuels, "Voir reçu", "29/09/2026", nom_vendeuse.upper()))

        # Mise à jour du CA dynamique correspondant strictement à la cible filtrée de la caissière
        label_ca.config(text=f"📊 CA FILTRÉ ({nom_vendeuse.upper()}) : {total_ca_cible:,} FCFA", bg="#0284c7", fg="white")

    def action_afficher_tout_historique():
        """Affiche l'intégralité des ventes de la boutique et applique le filtrage temporel strict sur le CA global du gérant."""
        for i in grille_audit.get_children(): 
            grille_audit.delete(i)
            
        toutes_les_ventes = data_base.recuper_tout_les_ventes()
        
        valeur_temporelle = entree_cible.get().strip()
        periode_choisie = select_tempo.get()
        
        total_ca_cible = 0.0

        for index, v in enumerate(toutes_les_ventes, start=1):
            if isinstance(v, (tuple, list)) and len(v) >= 4:
                num_id = v[0]
                client_nom = str(v[1]).upper()
                articles_bruts = str(v[2]).upper()
                net_ttc_total = f"{float(v[6]):,} FCFA" if len(v) > 6 else f"{float(v[3]):,} FCFA"
                
                date_facture = str(v[8]).strip() if len(v) > 8 else (str(v[4]).strip() if len(v) > 4 else "29/09/2026")
                caissiere_emetteur = str(v[7]).upper() if len(v) > 7 else (str(v[5]).upper() if len(v) > 5 else "ENTREPRISE")
                
                # 🟢 APPLICATION DU FILTRAGE TEMPOREL ULTRA-STRICT DEMANDÉ
                if valeur_temporelle:
                    garder_ligne = False
                    if periode_choisie == "JOUR" and date_facture == valeur_temporelle:
                        garder_ligne = True
                    elif periode_choisie == "MOIS" and date_facture.endswith(valeur_temporelle if valeur_temporelle.startswith("/") else f"/{valeur_temporelle}"):
                        garder_ligne = True
                    elif periode_choisie == "ANNEE" and date_facture.endswith(valeur_temporelle):
                        garder_ligne = True
                        
                    if not garder_ligne:
                        continue

                articles_visuels = articles_bruts if len(articles_bruts) < 32 else articles_bruts[:30] + "..."
                grille_audit.insert("", tk.END, values=(num_id, client_nom, articles_visuels, net_ttc_total, date_facture, caissiere_emetteur))
                
                try:
                    prix_brut = float(v[6]) if len(v) > 6 else float(v[3])
                    total_ca_cible += prix_brut
                except Exception:
                    pass
            else:
                num_id = str(index)
                client_nom = "ACHAT GLOBAL"
                articles_bruts = str(v).upper()
                articles_visuels = articles_bruts if len(articles_bruts) < 32 else articles_bruts[:30] + "..."
                grille_audit.insert("", tk.END, values=(num_id, client_nom, articles_visuels, "N/A", "29/09/2026", "CAISSE"))

        # Si une analyse statistique globale a déjà été lancée par le bouton ANALYSER, on ne force pas l'écrasement du bandeau vert principal
        if valeur_temporelle:
            label_ca.config(text=f"📊 CHIFFRE D'AFFAIRES SUR LA CIBLE FILTRÉE : {total_ca_cible:,} FCFA", bg="#0f766e", fg="white")

    audit = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    audit.title("📊 Tableau de Bord Économique")
    audit.geometry("750x650")
    audit.configure(bg="#f8fafc")
    audit.grab_set()

    tk.Label(audit, text="RAPPORT D'AUDIT COMPTABLE ANALYTIQUE", font=("Helvetica", 11, "bold"), bg="#1e293b", fg="white", pady=8).pack(fill=tk.X)

    cadre_stat = tk.LabelFrame(audit, text="Analyse Temporelle Comparative (CA vs Masse Salariale)", bg="#f8fafc", padx=10, pady=8)
    cadre_stat.pack(fill=tk.X, padx=15, pady=10)

    tk.Label(cadre_stat, text="Période :", bg="#f8fafc").grid(row=0, column=0, padx=5, sticky=tk.W)
    select_tempo = ttk.Combobox(cadre_stat, values=["JOUR", "MOIS", "ANNEE"], width=10, state="readonly")
    select_tempo.grid(row=0, column=1, padx=5); select_tempo.current(0)

    tk.Label(cadre_stat, text="Cible :", bg="#f8fafc").grid(row=0, column=2, padx=5, sticky=tk.W)
    entree_cible = tk.Entry(cadre_stat, width=12, font=("Helvetica", 10), bd=2)
    entree_cible.grid(row=0, column=3, padx=5)
    entree_cible.bind("<Return>", lambda event: action_charger_statistiques())

    tk.Button(cadre_stat, text="🔍 ANALYSER", font=("Helvetica", 9, "bold"), bg="#1e293b", fg="white", command=action_charger_statistiques).grid(row=0, column=4, padx=10)

    label_ca = tk.Label(cadre_stat, text="CHIFFRE D'AFFAIRES TTC : 0.00 FCFA | Gain Net : 0.00 FCFA", font=("Helvetica", 11, "bold"), bg="#e2e8f0", fg="#1e293b", pady=6)
    label_ca.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=6)
    
    label_top = tk.Label(cadre_stat, text="🔥 Produit Phare : Aucun", font=("Helvetica", 10), bg="#f8fafc", fg="#0f766e", anchor=tk.W)
    label_top.grid(row=2, column=0, columnspan=5, sticky=tk.EW, pady=2)
    
    label_perf = tk.Label(cadre_stat, text="📈 En attente d'analyse...", font=("Helvetica", 10, "italic"), bg="#f8fafc", fg="#475569", anchor=tk.W)
    label_perf.grid(row=3, column=0, columnspan=5, sticky=tk.EW, pady=2)

    cadre_grille = tk.LabelFrame(audit, text="Registre des transactions (Double-cliquez sur une ligne pour voir le détail complet)", bg="#f8fafc", padx=10, pady=8)
    cadre_grille.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

    cadre_filtre_nom = tk.Frame(cadre_grille, bg="#f8fafc")
    cadre_filtre_nom.pack(fill=tk.X, pady=4)
    
    tk.Label(cadre_filtre_nom, text="Caissière :", bg="#f8fafc").pack(side=tk.LEFT, padx=2)
    liste_caissieres = data_base.recuperer_liste_tous_employes()
    select_vendeuse = ttk.Combobox(cadre_filtre_nom, values=liste_caissieres, width=18, state="readonly")
    if liste_caissieres: select_vendeuse.current(0)
    select_vendeuse.pack(side=tk.LEFT, padx=4)
    
    tk.Button(cadre_filtre_nom, text="🎯 Filtrer", bg="#475569", fg="white", font=("Helvetica", 8, "bold"), command=action_filtrer_par_vendeuse).pack(side=tk.LEFT, padx=4)
    tk.Button(cadre_filtre_nom, text="📋 Afficher Tout", bg="#0284c7", fg="white", font=("Helvetica", 8, "bold"), command=action_afficher_tout_historique).pack(side=tk.RIGHT, padx=4)
    tk.Button(cadre_filtre_nom, text="📥 EXPORTER SUR EXCEL", bg="#10b981", fg="white", font=("Helvetica", 8, "bold"), command=action_exporter_registre_excel).pack(side=tk.RIGHT, padx=8)

    grille_audit = ttk.Treeview(cadre_grille, columns=("ID", "Client", "Article", "Total TTC", "Date/Heure", "Émetteur"), show="headings", height=8)
    grille_audit.heading("ID", text="N°"); grille_audit.heading("Client", text="CLIENT"); grille_audit.heading("Article", text="ARTICLE"); grille_audit.heading("Total TTC", text="NET TTC"); grille_audit.heading("Date/Heure", text="TEMPOREL"); grille_audit.heading("Émetteur", text="CAISSIÈRE")
    grille_audit.column("ID", width=40, anchor=tk.CENTER); grille_audit.column("Client", width=110, anchor=tk.W); grille_audit.column("Article", width=140, anchor=tk.W); grille_audit.column("Total TTC", width=110, anchor=tk.CENTER); grille_audit.column("Date/Heure", width=120, anchor=tk.CENTER); grille_audit.column("Émetteur", width=80, anchor=tk.CENTER)
    
    # 🟢 ANCRAGE ÉVÉNEMENT DU DOUBLE-CLIC SUR LA GRILLE
    grille_audit.bind("<Double-1>", action_double_clic_detail_facture)

    defilement_audit = ttk.Scrollbar(cadre_grille, orient="vertical", command=grille_audit.yview)
    grille_audit.configure(yscrollcommand=defilement_audit.set)
    grille_audit.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    defilement_audit.pack(side=tk.RIGHT, fill=tk.Y)

    action_afficher_tout_historique()

    
    
    
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 9 SUR 15)
# =====================================================================
def ouvrir_panneau_employes():
    """Interface d'administration de la liste des employés et de configuration de leurs salaires et régimes fiscaux."""
    if SESSION_UTILISATEUR != "gerant":
        messagebox.showerror("Accès Interdit", "Espace réservé au gérant de la boutique.")
        return

    def rafraichir_liste_employes():
        for i in tableau_emp.get_children(): tableau_emp.delete(i)
        lignes = data_base.obtenir_tous_les_employes_complets()
        for id_db, identifiant, role, salaire in lignes:
            # 🟢 NOTE : On garde l'affichage standard du salaire
            tableau_emp.insert("", tk.END, iid=str(id_db), values=(str(identifiant).upper(), str(role).upper(), f"{salaire:,} FCFA"))

    def action_definir_salaire():
        selection = tableau_emp.selection()
        if not selection:
            messagebox.showwarning("Sélection manquante", "Veuillez sélectionner un employé dans la grille.")
            return
        id_emp = selection[0]
        nom_emp = tableau_emp.item(id_emp)["values"][0]
        
        nouveau_salaire = simpledialog.askfloat("RH - Masse Salariale", f"Définir le salaire mensuel fixe pour {nom_emp} (FCFA) :", minvalue=0, parent=fenetre_emp)
        if nouveau_salaire is not None:
            data_base.modifier_salaire_employe_sql(id_emp, nouveau_salaire)
            messagebox.showinfo("Succès", f"Fiche de paie de {nom_emp} mise à jour.")
            rafraichir_liste_employes()

    def action_creer_employe_grille():
        nom = entree_emp_nom.get().strip().lower()
        mdp = entree_emp_mdp.get().strip()
        sal_txt = entree_emp_sal.get().strip()
        # 🟢 RÉCUPÉRATION DU CHOIX TVA : 1 si coché, 0 si décoché
        tva_statut = 1 if var_applique_tva_rh.get() else 0
        
        if not all([nom, mdp, sal_txt]):
            messagebox.showwarning("Champs vides", "Veuillez remplir le nom, le mot de passe et le salaire.")
            return
        try:
            salaire = float(sal_txt)
            # 🟢 CORRIGÉ : On passe dynamiquement tva_statut au moteur SQL d'origine
            if data_base.ajouter_nouvel_employe_sql(nom, mdp, tva_statut, salaire):
                messagebox.showinfo("Succès", f"L'employé '{nom.upper()}' a été ajouté avec succès.")
                entree_emp_nom.delete(0, tk.END); entree_emp_mdp.delete(0, tk.END); entree_emp_sal.delete(0, tk.END)
                var_applique_tva_rh.set(True) # Réinitialisation de la case à cocher
                rafraichir_liste_employes()
                entree_emp_nom.focus()
            else: messagebox.showerror("Erreur", "Cet identifiant existe déjà.")
        except ValueError: messagebox.showerror("Erreur", "Le salaire doit être un nombre valide.")

    def action_supprimer_employe_grille():
        selection = tableau_emp.selection()
        if not selection:
            messagebox.showwarning("Sélection manquante", "Sélectionnez un employé à supprimer.")
            return
        id_emp = selection[0]
        nom_emp = tableau_emp.item(id_emp)["values"][0]
        if messagebox.askyesno("Confirmation", f"Voulez-vous licencier définitivement l'employé « {nom_emp} » ?"):
            connexion = sqlite3.connect(data_base.DB_NAME)
            connexion.execute("DELETE FROM employes WHERE id = ?", (id_emp,))
            connexion.commit(); connexion.close()
            messagebox.showinfo("Succès", "Employé retiré du registre.")
            rafraichir_liste_employes()

    fenetre_emp = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    fenetre_emp.title("👥 Administration des RH - Registre du Personnel")
    fenetre_emp.geometry("560x620") # Augmentation légère de la hauteur pour accueillir proprement la case TVA
    fenetre_emp.configure(bg="#f8fafc")
    fenetre_emp.resizable(False, False); fenetre_emp.grab_set()

    tk.Label(fenetre_emp, text="REGISTRE DU PERSONNEL & CHARGES SALARIALES", font=("Helvetica", 11, "bold"), bg="#1e3a8a", fg="white", pady=8).pack(fill=tk.X)
    cadre_table = tk.Frame(fenetre_emp, bg="#f8fafc")
    cadre_table.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    tableau_emp = ttk.Treeview(cadre_table, columns=("Nom", "Role", "Salaire"), show="headings", height=6)
    tableau_emp.heading("Nom", text="IDENTIFIANT EMPLOYÉ"); tableau_emp.heading("Role", text="PRIVILÈGE ACCÈS"); tableau_emp.heading("Salaire", text="SALAIRE MENSUEL")
    tableau_emp.column("Nom", width=200, anchor=tk.W); tableau_emp.column("Role", width=120, anchor=tk.CENTER); tableau_emp.column("Salaire", width=160, anchor=tk.CENTER)
    
    defilement_emp = ttk.Scrollbar(cadre_table, orient="vertical", command=tableau_emp.yview)
    tableau_emp.configure(yscrollcommand=defilement_emp.set)
    tableau_emp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    defilement_emp.pack(side=tk.RIGHT, fill=tk.Y)

    tk.Button(fenetre_emp, text="💳 AJOUTER / AJUSTER LE SALAIRE DE L'EMPLOYÉ SÉLECTIONNÉ", font=("Helvetica", 9, "bold"), bg="#10b981", fg="white", command=action_definir_salaire).pack(fill=tk.X, padx=15, pady=2)

    cadre_form = tk.LabelFrame(fenetre_emp, text="Créer un Nouveau Contrat Employé", font=("Helvetica", 9, "bold"), bg="#f8fafc", padx=10, pady=6)
    cadre_form.pack(fill=tk.X, padx=15, pady=10)

    tk.Label(cadre_form, text="Identifiant / Nom de connexion :", bg="#f8fafc").pack(anchor=tk.W)
    entree_emp_nom = tk.Entry(cadre_form, font=("Helvetica", 10))
    entree_emp_nom.pack(fill=tk.X, pady=2)

    tk.Label(cadre_form, text="Mot de passe initial :", bg="#f8fafc").pack(anchor=tk.W)
    entree_emp_mdp = tk.Entry(cadre_form, font=("Helvetica", 10))
    entree_emp_mdp.pack(fill=tk.X, pady=2)

    tk.Label(cadre_form, text="Salaire mensuel de base (FCFA) :", bg="#f8fafc").pack(anchor=tk.W)
    entree_emp_sal = tk.Entry(cadre_form, font=("Helvetica", 10))
    entree_emp_sal.pack(fill=tk.X, pady=2)

    # 🟢 INTEGRATION CHIRURGICALE DE LA CASE A COCHER TVA DANS LE FORMULAIRE RH
    var_applique_tva_rh = tk.BooleanVar(value=True)
    case_tva_rh = tk.Checkbutton(
        cadre_form, 
        text="Appliquer la TVA (19.25%) sur les factures de cet employé", 
        variable=var_applique_tva_rh, 
        bg="#f8fafc", 
        font=("Helvetica", 9, "bold"), 
        fg="#1e3a8a"
    )
    case_tva_rh.pack(anchor=tk.W, pady=4)

    # Configuration des liens de focalisation par la touche Entrée clavier
    entree_emp_nom.bind("<Return>", lambda event: entree_emp_mdp.focus())
    entree_emp_mdp.bind("<Return>", lambda event: entree_emp_sal.focus())
    entree_emp_sal.bind("<Return>", lambda event: action_creer_employe_grille())

    cadre_act_rh = tk.Frame(cadre_form, bg="#f8fafc")
    cadre_act_rh.pack(fill=tk.X, pady=6)
    tk.Button(cadre_act_rh, text="👥 CRÉER COMPTE COMPTOIR", bg="#3b82f6", fg="white", font=("Helvetica", 9, "bold"), command=action_creer_employe_grille).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    tk.Button(cadre_act_rh, text="🗑️ RETIRER DU REGISTRE PERSONNEL", bg="#dc2626", fg="white", font=("Helvetica", 9, "bold"), command=action_supprimer_employe_grille).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

    rafraichir_liste_employes()



# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 10 SUR 15)
# =====================================================================
def ouvrir_panneau_administration():
    """Ancienne fenêtre d'ajout basique caissière conservée à l'identique pour la configuration fiscale."""
    if SESSION_UTILISATEUR != "gerant":
        messagebox.showerror("Accès Interdit", "Seul le gérant configure le personnel.")
        return

    def action_ajouter_caissier():
        nom = entree_nouveau_nom.get().strip()
        code = entree_nouveau_code.get().strip()
        tva_choix = select_tva_personnel.get()
        applique_tva = 1 if tva_choix == "Oui (Grande Entreprise)" else 0
        
        if not nom or not code:
            messagebox.showwarning("Champs vides", "Remplissez toutes les cases.")
            return
        if data_base.ajouter_nouvel_employe_sql(nom, code, applique_tva, 0):
            messagebox.showinfo("Succès", f"Régime fiscal configuré pour '{nom.upper()}' !")
            entree_nouveau_nom.delete(0, tk.END); entree_nouveau_code.delete(0, tk.END)
        else: messagebox.showerror("Erreur", "Identifiant déjà pris.")

    admin = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    admin.title("⚙️ Configuration Fiscale Personnel")
    admin.geometry("400x320")
    admin.configure(bg="#f8fafc"); admin.grab_set()

    tk.Label(admin, text="AJOUTER UNE NOUVELLE CAISSIÈRE", font=("Helvetica", 11, "bold"), bg="#475569", fg="white", pady=6).pack(fill=tk.X)
    cadre = tk.Frame(admin, bg="#f8fafc", padx=15, pady=15)
    cadre.pack(fill=tk.BOTH, expand=True)

    tk.Label(cadre, text="Identifiant de la caissière :", bg="#f8fafc").pack(anchor=tk.W)
    entree_nouveau_nom = tk.Entry(cadre, font=("Helvetica", 10))
    entree_nouveau_nom.pack(fill=tk.X, pady=4)

    tk.Label(cadre, text="Mot de passe caissière :", bg="#f8fafc").pack(anchor=tk.W)
    entree_nouveau_code = tk.Entry(cadre, font=("Helvetica", 10), show="*")
    entree_nouveau_code.pack(fill=tk.X, pady=4)

    tk.Label(cadre, text="Appliquer la TVA sur ses ventes ?", bg="#f8fafc").pack(anchor=tk.W, pady=2)
    select_tva_personnel = ttk.Combobox(cadre, values=["Oui (Grande Entreprise)", "Non (Petite Boutique)"], state="readonly")
    select_tva_personnel.pack(fill=tk.X, pady=4); select_tva_personnel.current(0)

    tk.Button(cadre, text="➕ CRÉER LE COMPTE SÉCURISÉ", bg="#475569", fg="white", font=("Helvetica", 9, "bold"), command=action_ajouter_caissier, pady=6).pack(fill=tk.X, pady=15)
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 11 SUR 15)
# =====================================================================
def ouvrir_comptoir_facturation():
    """Interface de vente principale prenant en charge les paniers multi-articles en gros et le défilement."""
    global SESSION_UTILISATEUR, NOM_CAISSIERE_ACTIVE, NOM_BOUTIQUE_FIXE, PANIER_FACTURE_EN_COURS

    nom_boutique_fixe = (data_base.recuperer_nom_boutique_sql() or NOM_BOUTIQUE_FIXE).upper()
    NOM_BOUTIQUE_FIXE = nom_boutique_fixe
    PANIER_FACTURE_EN_COURS = [] # Réinitialisation à l'ouverture du tiroir

    comptoir = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    comptoir.title(f"💳 KASHFLOW Comptoir - Session {NOM_CAISSIERE_ACTIVE.upper()}")
    comptoir.geometry("540x780") # Largeur élargie pour accueillir la grille du panier en gros
    comptoir.configure(bg="#f8fafc")

    def rafraichir_stocks_depuis_cloud():
        if not URL_API_KASHFLOW or not CLE_API_KASHFLOW: return
        try:
            # 🟢 1. Appel sécurisé avec le X-API-Key (Ce que tu viens de faire)
            reponse = requests.get(f"{URL_API_KASHFLOW}/boutique/telecharger-stocks", headers={"X-API-Key": CLE_API_KASHFLOW}, timeout=15)
            if reponse.status_code == 200:
                articles = reponse.json().get("articles", [])
                conn = sqlite3.connect(data_base.DB_NAME)
                
                # 🟢 2. CORRIGÉ : On vide la table 'stocks' (Pas 'produits')
                conn.execute("DELETE FROM stocks") 
                for item in articles:
                    art = item[0] if isinstance(item, list) else item.get("article")
                    desc = item[1] if isinstance(item, list) else item.get("description_unique")
                    p_ht = item[2] if isinstance(item, list) else item.get("prix_ht")
                    qte = item[3] if isinstance(item, list) else item.get("quantite")
                    
                    # 🟢 3. CORRIGÉ : On insère dans la structure d'origine de ton data_base.py
                    conn.execute("""
                        INSERT INTO stocks (modele, quantite_dispo, prix_achat, ventes_cumulees) 
                        VALUES (?, ?, ?, 0)
                    """, (art, qte, p_ht))
                conn.commit()
                conn.close()
                actualiser_liste_deroulante_smartphones()
        except Exception as e: 
            logging.warning("Erreur rafraîchissement stocks : %s", e)


    def actualiser_liste_deroulante_smartphones():
        try:
            connexion = sqlite3.connect(data_base.DB_NAME)
            curseur = connexion.cursor()
            curseur.execute("SELECT modele FROM stocks WHERE quantite_dispo > 0")
            modeles = [str(row[0]).strip().upper() for row in curseur.fetchall()]
            connexion.close()
            liste_smartphones["values"] = modeles
            if modeles and not liste_smartphones.get(): liste_smartphones.current(0)
        except Exception: pass

    def planifier_synchronisation_et_ecoute():
        if comptoir.winfo_exists():
            threading.Thread(target=synchroniser_file_cloud, daemon=True).start()
            threading.Thread(target=rafraichir_stocks_depuis_cloud, daemon=True).start()
            # 🟢 AUGMENTATION D'USINE : Vérification toutes les 2 minutes pour éviter d'être banni par Render
            comptoir.after(30000, planifier_synchronisation_et_ecoute)

    threading.Thread(target=synchroniser_file_cloud, daemon=True).start()
    threading.Thread(target=rafraichir_stocks_depuis_cloud, daemon=True).start()
    comptoir.after(30000, planifier_synchronisation_et_ecoute)

    tk.Label(comptoir, text=f"{nom_boutique_fixe} - COMPTOIR DE FACTURATION", font=("Helvetica", 12, "bold"), bg="#0f766e", fg="white", pady=8).pack(fill=tk.X)
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 12 SUR 15)
# =====================================================================
    def verifier_connexion_cloud():
        try:
            reponse = requests.get(URL_API_KASHFLOW, timeout=4)
            if reponse.status_code == 200: label_statut_cloud.config(text="CONNECTÉ 🟢", fg="#10b981")
            else: label_statut_cloud.config(text="📡 SERVEUR EN LIGNE 🟡", fg="#f59e0b")
        except Exception: label_statut_cloud.config(text=" DÉCONNECTÉ 🔴", fg="#dc2626")

    def forcer_test_reseau():
        label_statut_cloud.config(text="🔄 Connexion en cours...", fg="#94a3b8")
        comptoir.update_idletasks()
        try:
            reponse = requests.get(URL_API_KASHFLOW, timeout=4)
            if reponse.status_code == 200:
                label_statut_cloud.config(text="📡 CLOUD CONNECTÉ : EN DIRECT 🟢", fg="#10b981")
                threading.Thread(target=rafraichir_stocks_depuis_cloud, daemon=True).start()
                messagebox.showinfo("Réseau OK", "Liaisons d'antennes d'usine synchronisées !")
            else: label_statut_cloud.config(text="📡 SERVEUR EN LIGNE 🟡", fg="#f59e0b")
        except Exception:
            label_statut_cloud.config(text="📡 CLOUD DÉCONNECTÉ 🔴", fg="#dc2626")
            messagebox.showwarning("Réseau Coupé", "Fonctionnement local asynchrone activé.")

    label_statut_cloud = tk.Label(comptoir, text="📡 VÉRIFICATION DU STATUT RÉSEAU...", font=("Helvetica", 10, "bold"), bg="#1e3a8a", fg="white")
    label_statut_cloud.pack(pady=2)
    
    btn_test_reseau = tk.Button(comptoir, text="🔄 Tester la liaison Cloud", font=("Helvetica", 8, "bold"), bg="#1e293b", fg="white", command=forcer_test_reseau)
    btn_test_reseau.pack(pady=2)
    comptoir.after(1000, verifier_connexion_cloud)

    # Cadre de saisie principal du comptoir
    cadre = tk.Frame(comptoir, bg="#f8fafc", padx=15, pady=5)
    cadre.pack(fill=tk.X)

    tk.Label(cadre, text="Client :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    entree_client = tk.Entry(cadre, font=("Helvetica", 11), bd=2)
    entree_client.pack(fill=tk.X, pady=2)

    tk.Label(cadre, text="Sélectionner l'Article :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    liste_smartphones = ttk.Combobox(cadre, state="readonly", font=("Helvetica", 10))
    actualiser_liste_deroulante_smartphones()
    liste_smartphones.pack(fill=tk.X, pady=2)

    tk.Label(cadre, text="Description unique (N° IMEI, Série, SAV) :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    entree_desc = tk.Entry(cadre, font=("Helvetica", 11), bd=2)
    entree_desc.pack(fill=tk.X, pady=2)

    tk.Label(cadre, text="Prix Unitaire HT (FCFA) :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    entree_prix = tk.Entry(cadre, font=("Helvetica", 11), bd=2)
    entree_prix.pack(fill=tk.X, pady=2)

    tk.Label(cadre, text="Quantité :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    entree_quantite = tk.Entry(cadre, font=("Helvetica", 11), bd=2)
    entree_quantite.pack(fill=tk.X, pady=2)

    var_tva_directe = tk.BooleanVar(value=True)
    if SESSION_UTILISATEUR == "gerant":
        case_tva = tk.Checkbutton(cadre, text="Facturer la TVA (19.25%) sur cette vente", variable=var_tva_directe, bg="#f8fafc", font=("Helvetica", 10, "bold"), fg="#1e3a8a")
        case_tva.pack(anchor=tk.W, pady=4)
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - ÉTAPE 13 SUR 15)
# =====================================================================
    # 🟢 CADRE GRILLE : Panier multi-articles défilant (Vente en gros)
    cadre_panier = tk.LabelFrame(comptoir, text="Panier de la Facture Unique (Vente en Gros)", font=("Helvetica", 9, "bold"), bg="#f8fafc", padx=10, pady=5)
    cadre_panier.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    grille_panier = ttk.Treeview(cadre_panier, columns=("Article", "PU_HT", "Qte", "Mnt_HT", "Mnt_TVA", "Net_TTC"), show="headings", height=5)
    grille_panier.heading("Article", text="ARTICLE"); grille_panier.heading("PU_HT", text="P.U HT"); grille_panier.heading("Qte", text="QTE"); grille_panier.heading("Mnt_HT", text="TOT HT"); grille_panier.heading("Mnt_TVA", text="TVA"); grille_panier.heading("Net_TTC", text="NET TTC")
    
    grille_panier.column("Article", width=140, anchor=tk.W); grille_panier.column("PU_HT", width=70, anchor=tk.CENTER); grille_panier.column("Qte", width=40, anchor=tk.CENTER); grille_panier.column("Mnt_HT", width=70, anchor=tk.CENTER); grille_panier.column("Mnt_TVA", width=70, anchor=tk.CENTER); grille_panier.column("Net_TTC", width=80, anchor=tk.CENTER)
    
    scroll_panier = ttk.Scrollbar(cadre_panier, orient="vertical", command=grille_panier.yview)
    grille_panier.configure(yscrollcommand=scroll_panier.set)
    grille_panier.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll_panier.pack(side=tk.RIGHT, fill=tk.Y)

    def actualiser_affichage_grille_panier():
        for i in grille_panier.get_children(): grille_panier.delete(i)
        for idx, p in enumerate(PANIER_FACTURE_EN_COURS):
            grille_panier.insert("", tk.END, iid=str(idx), values=(p["article"].upper(), f"{p['prix_unitaire']:,}", p["quantite"], f"{p['total_ht']:,}", f"{p['total_tva']:,}", f"{p['total_ttc']:,}"))

    def action_ajouter_panier_souris():
        """Bouton exclusif souris : MOTEUR DE GROS. Ajoute une ligne d'article uniquement dans le panier virtuel."""
        caissiere_nom = str(NOM_CAISSIERE_ACTIVE).strip().lower()
        smartphone = liste_smartphones.get().strip().lower()
        desc = entree_desc.get().strip()
        prix_txt = entree_prix.get().strip()
        qte_txt = entree_quantite.get().strip()

        if not all([smartphone, prix_txt, qte_txt]):
            messagebox.showwarning("Incomplet", "Sélectionnez un article, un prix et une quantité valide.")
            return
        try:
            prix = float(prix_txt)
            qte = int(qte_txt)
            if prix <= 0 or qte <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Erreur", "Données numériques invalides.")
            return

        applique_tva = 1 if (SESSION_UTILISATEUR == "gerant" and var_tva_directe.get()) or (SESSION_UTILISATEUR != "gerant" and data_base.obtenir_regime_tva_employe(caissiere_nom) == 1) else 0
        calcul = operation.calculer_facture_dynamique(prix, qte, applique_tva)
        
        # 🟢 STOCKAGE MÉMOIRE EXCLUSIF : Zéro écriture en base de données ici
        PANIER_FACTURE_EN_COURS.append({
            "article": smartphone, 
            "description_unique": desc if desc else "AUCUN SPECI.", 
            "prix_unitaire": prix, 
            "quantite": qte,
            "total_ht": calcul["montant_ht"], 
            "total_tva": calcul["valeur_tva"], 
            "total_ttc": calcul["total_ttc"], 
            "tva_appliquee": applique_tva
        })

        actualiser_affichage_grille_panier()
        entree_desc.delete(0, tk.END)
        entree_prix.delete(0, tk.END)
        entree_quantite.delete(0, tk.END)
        liste_smartphones.focus()

    def action_cloturer_la_facture_souris():
        """Bouton exclusif souris : Valide l'encaissement et trie (Article Unique VS Facture de Gros)."""
        caissiere_nom = str(NOM_CAISSIERE_ACTIVE).strip().lower()
        nom_client = entree_client.get().strip()
        nom_boutique = data_base.recuperer_nom_boutique_sql() or "DS STOR"
        
        if not nom_client:
            messagebox.showwarning("Client manquant", "Veuillez renseigner le nom du client acheteur.")
            return

        reference_locale = str(uuid.uuid4())

        # =====================================================================
        # 📄 CAS N°1 : LE PANIER EST VIDE ➔ CLIENT CLASSIQUE (ARTICLE UNIQUE)
        # =====================================================================
        if not PANIER_FACTURE_EN_COURS:
            smartphone = liste_smartphones.get().strip().lower()
            desc = entree_desc.get().strip()
            prix_txt = entree_prix.get().strip()
            qte_txt = entree_quantite.get().strip()
            
            if not all([smartphone, prix_txt, qte_txt]):
                messagebox.showwarning("Panier vide", "Veuillez ajouter des articles au panier ou remplir les champs pour une vente directe.")
                return
                
            try:
                prix = float(prix_txt)
                qte = int(qte_txt)
                if prix <= 0 or qte <= 0: raise ValueError
            except ValueError:
                messagebox.showerror("Erreur", "Données numériques invalides dans les champs de vente.")
                return
                
            verif = data_base.verifier_et_reduire_stock(smartphone, qte)
            if not verif["autorise"]:
                messagebox.showerror("Stock insuffisant", f"Action annulée : {verif['reason']}")
                return
                
            applique_tva = 1 if (SESSION_UTILISATEUR == "gerant" and var_tva_directe.get()) or (SESSION_UTILISATEUR != "gerant" and data_base.obtenir_regime_tva_employe(caissiere_nom) == 1) else 0
            calcul = operation.calculer_facture_dynamique(prix, qte, applique_tva)
            
            string_articles = f"{smartphone.upper()} (x{qte})"
            string_desc = desc if desc else "AUCUN SPECI."
            
            num_facture = data_base.enregistrer_vente_sql(
                nom_client, string_articles, string_desc, 
                calcul["montant_ht"], calcul["valeur_tva"], calcul["total_ttc"], 
                caissiere_nom, reference_locale
            )

            if num_facture:
                panier_virtuel_unique = [{
                    "article": smartphone,
                    "description_unique": string_desc,
                    "quantite": qte,
                    "montant_ht": calcul["montant_ht"],
                    "total_ttc": calcul["total_ttc"]
                }]

                operation.generer_recu_pdf_industriel(
                    nom_boutique, num_facture, nom_client, "SANS_TEL", 
                    panier_virtuel_unique, caissiere_nom, 
                    calcul["montant_ht"], calcul["valeur_tva"], calcul["total_ttc"]
                )
                
                # 🟢 CAS N°1 : ARTICLE UNIQUE - IMPRESSION THERMIQUE DIRECTE SÉCURISÉE
                try:
                    # Extraction robuste du nom de l'imprimante (Indice -1 pour cibler le nom brut du pilote Windows)
                    liste_imp = [str(imp[-1]).lower() for imp in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
                    if any(mot in name for mot in ["thermal", "pos", "58", "80", "xp-"] for name in liste_imp):
                        imprimer_ticket_thermique_direct(nom_client, panier_virtuel_unique, calcul["total_ttc"], caissiere_nom)
                except Exception as err_imp:
                    logging.warning("Échec envoi impression direct article unique : %s", err_imp)


                donnees_cloud = {"client": nom_client, "article": string_articles, "description_unique": string_desc, "prix_ht": calcul["montant_ht"], "quantite": qte, "caissiere": caissiere_nom, "applique_tva_vente": applique_tva}
                threading.Thread(target=synchroniser_vente_cloud, args=(reference_locale, donnees_cloud), daemon=True).start()

                if verif.get("alerte_patron"):
                    messagebox.showwarning("Alerte Stock", f"⚠️ Attention, il ne reste que : {verif['restant']} pcs")

                messagebox.showinfo("Facturation Clôturée", f"✅ Vente directe #{str(num_facture).zfill(4)} émise avec succès !")

        # =====================================================================
        # 🗂️ CAS N°2 : LE PANIER EST PLEIN ➔ FACTURE DE GROS (MULTI-LIGNES)
        # =====================================================================
        else:
            try:
                general_ht = sum(p["total_ht"] for p in PANIER_FACTURE_EN_COURS)
                general_tva = sum(p["total_tva"] for p in PANIER_FACTURE_EN_COURS)
                general_ttc = sum(p["total_ttc"] for p in PANIER_FACTURE_EN_COURS)
                
                string_articles = ", ".join([f"{p['article'].upper()} (X{p['quantite']})" for p in PANIER_FACTURE_EN_COURS])
                string_desc = " | ".join([f"{p['article'].upper()}: {p['description_unique']}" for p in PANIER_FACTURE_EN_COURS])
                
                num_facture = data_base.enregistrer_vente_sql(
                    nom_client, string_articles, string_desc, 
                    general_ht, general_tva, general_ttc, 
                    caissiere_nom, reference_locale
                )

                if num_facture:
                    operation.generer_facture_gros_pdf_industriel(
                        nom_boutique, num_facture, nom_client, 
                        PANIER_FACTURE_EN_COURS, caissiere_nom, 
                        general_ht, general_tva, general_ttc
                    )

                    # 🟢 CAS N°2 : FACTURE DE GROS - IMPRESSION THERMIQUE DIRECTE SÉCURISÉE
                    try:
                        liste_imp = [str(imp[-1]).lower() for imp in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
                        if any(mot in name for mot in ["thermal", "pos", "58", "80", "xp-"] for name in liste_imp):
                            imprimer_ticket_thermique_direct(nom_client, PANIER_FACTURE_EN_COURS, general_ttc, caissiere_nom)
                    except Exception as err_imp:
                        logging.warning("Échec envoi impression direct facture de gros : %s", err_imp)


                    donnees_cloud = {"client": nom_client, "article": string_articles, "description_unique": string_desc, "prix_ht": general_ht, "quantite": 1, "caissiere": caissiere_nom, "applique_tva_vente": 1}
                    threading.Thread(target=synchroniser_vente_cloud, args=(reference_locale, donnees_cloud), daemon=True).start()

                    messagebox.showinfo("Facturation Clôturée", f"✅ Facture de Gros #{str(num_facture).zfill(4)} émise avec succès !\nNet à payer : {general_ttc:,} FCFA")

            except Exception as e:
                messagebox.showerror("Erreur système", f"Échec de validation de la facture de gros : {e}")

        # Nettoyage
        PANIER_FACTURE_EN_COURS.clear()
        actualiser_affichage_grille_panier()
        entree_client.delete(0, tk.END)
        entree_desc.delete(0, tk.END)
        entree_prix.delete(0, tk.END)
        entree_quantite.delete(0, tk.END)
        actualiser_liste_deroulante_smartphones()
        entree_client.focus()


    # 🟢 ASSIGNATION CLAVIER EXCLUSIVE : Enchaînement fluide des cases and ajout au panier par la touche Entrée
    entree_client.bind("<Return>", lambda event: liste_smartphones.focus())
    liste_smartphones.bind("<Return>", lambda event: entree_desc.focus())
    entree_desc.bind("<Return>", lambda event: entree_prix.focus())
    entree_prix.bind("<Return>", lambda event: entree_quantite.focus())
    entree_quantite.bind("<Return>", lambda event: action_ajouter_panier_souris())

    # Zone des deux gros boutons d'action d'usine (Sélection exclusive Souris)
    cadre_boutons_gros = tk.Frame(comptoir, bg="#f8fafc")
    cadre_boutons_gros.pack(fill=tk.X, padx=15, pady=5)
    
    tk.Button(
        cadre_boutons_gros, 
        text="➕ AJOUTER À LA FACTURE", 
        font=("Helvetica", 10, "bold"), 
        bg="#3b82f6", 
        fg="white", 
        command=action_ajouter_panier_souris, 
        pady=8
    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    
    tk.Button(
        cadre_boutons_gros, 
        text="🛒 VALIDER LA VENTE GLOBALE", 
        font=("Helvetica", 10, "bold"), 
        bg="#10b981", 
        fg="white", 
        command=action_cloturer_la_facture_souris, 
        pady=8
    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

    tk.Label(comptoir, text="PANNEAU DE CONTROLE SÉCURISÉ", font=("Helvetica", 10, "bold"), bg="#e2e8f0", fg="#1e293b", pady=4).pack(fill=tk.X)
    cadre_menu = tk.Frame(comptoir, bg="#e2e8f0", padx=10, pady=8)
    cadre_menu.pack(fill=tk.X)


    # =====================================================================
    # 🟢 ROUTAGE ÉTANCHE DES PRIVILÈGES DU PANNEAU DE CONTRÔLE BAS
    # =====================================================================
    if SESSION_UTILISATEUR == "gerant":
        tk.Button(cadre_menu, text="📦 Stocks", bg="#0284c7", fg="white", font=("Helvetica", 9, "bold"), command=ouvrir_panneau_stock).pack(side=tk.LEFT, padx=3)
        tk.Button(cadre_menu, text="📊 Analyse", bg="#7c3aed", fg="white", font=("Helvetica", 9, "bold"), command=ouvrir_panneau_historique).pack(side=tk.LEFT, padx=3)
        tk.Button(cadre_menu, text="👥 gestion des employés", bg="#ea580c", fg="white", font=("Helvetica", 9, "bold"), command=ouvrir_panneau_employes).pack(side=tk.LEFT, padx=3)
    else:
        tk.Button(
            cadre_menu, 
            text="📊 HISTORIQUE DE VENTES", 
            bg="#f59e0b", 
            fg="white", 
            font=("Helvetica", 9, "bold"), 
            command=ouvrir_historique_caissiere
        ).pack(side=tk.LEFT, padx=5)

# =====================================================================
# 🟢 COLLER LA FONCTION ICI (ALIGNÉE TOUT À FAIT À GAUCHE DU FICHIER)
# =====================================================================
    def deconnecter():
        """Ferme la session active du comptoir et réactive l'écran d'authentification racine."""
        comptoir.destroy()
        FENETRE_PRINCIPALE_LOGIN.deiconify()
        entree_user.delete(0, tk.END)
        entree_password.delete(0, tk.END)
        entree_user.insert(0, "gerant")
        entree_user.focus()

    # Le bouton Quitter qui appelle deconnecter (garder son emplacement actuel d'origine)
    tk.Button(cadre_menu, text="🚪 Quitter", bg="#64748b", fg="white", font=("Helvetica", 9, "bold"), command=deconnecter).pack(side=tk.RIGHT, padx=3)
    tk.Button(cadre_menu, text="🔑 Modifier mon passe", bg="#CE0707", fg="white", font=("Helvetica", 9, "bold"), command=ouvrir_fenetre_modification_mdp_caissiere).pack(side=tk.LEFT, padx=3)

# =====================================================================
# 🟢 ÉTAPE EXTRA-EXTÉRIEURE : FONCTION PLACÉE TOUT À FAIT À GAUCHE DU FICHIER
# =====================================================================
def ouvrir_historique_caissiere():
    """Fenêtre d'historique personnelle des ventes de la caissière active avec affichage initial automatique, scrollbar et double-clic d'audit."""
    caissiere_nom = str(NOM_CAISSIERE_ACTIVE).strip().lower()

    # =====================================================================
    # 📄 POP-UP DE DOUBLE-CLIC CAISSIÈRE (RE-CALIBRÉE À 100% SANS COUPURE)
    # =====================================================================
    def action_double_clic_detail_caissiere(event):
        """Ouvre une fenêtre d'audit propre en allant chercher la liste complète des marchandises en BD."""
        selection = arbre_historique.selection()
        if not selection: return
        
        ligne_id = selection[0]
        valeurs = arbre_historique.item(ligne_id)["values"]
        
        num_facture = valeurs[0]
        client_nom = valeurs[1]
        net_ttc = valeurs[3]
        date_v = valeurs[4]
        caissiere_v = valeurs[5]
        
        # Interrogation directe de la BD locale pour extraire le texte d'origine complet (Évite le texte tronqué)
        try:
            connexion = sqlite3.connect(data_base.DB_NAME)
            curseur = connexion.cursor()
            curseur.execute("SELECT article, description_unique FROM ventes WHERE id = ?", (int(num_facture),))
            ligne_bd = curseur.fetchone()
            connexion.close()
            
            if ligne_bd:
                articles_complets_bd = str(ligne_bd[0]).upper()
                imei_complets_bd = str(ligne_bd[1]).upper()
            else:
                articles_complets_bd = str(valeurs[2]).upper()
                imei_complets_bd = "AUCUNE SPÉCIFICATION TECHNIQUE ACCESSIBLE"
        except Exception:
            articles_complets_bd = str(valeurs[2]).upper()
            imei_complets_bd = "ERREUR DE LECTURE DU REGISTRE LOCAL"

        # Fenêtre pop-up graphique d'audit caissière
        pop_detail = Toplevel(historique)
        pop_detail.title(f"📄 Détail Vente Multi-Lignes #{str(num_facture).zfill(4)}")
        pop_detail.geometry("480x340")
        pop_detail.configure(bg="#f8fafc")
        pop_detail.grab_set()
        
        tk.Label(pop_detail, text=f"FACTURE #{str(num_facture).zfill(4)} - {client_nom}", font=("Helvetica", 10, "bold"), bg="#1e293b", fg="white", pady=6).pack(fill=tk.X)
        
        cadre_corps = tk.Frame(pop_detail, bg="#f8fafc", padx=15, pady=10)
        cadre_corps.pack(fill=tk.BOTH, expand=True)
        
        texte_details = tk.Text(cadre_corps, font=("Helvetica", 10), bg="white", bd=2, wrap=tk.WORD)
        texte_details.pack(fill=tk.BOTH, expand=True)
        
        contenu_affichage = f"📅 DATE DE LA VENTE  : {date_v}\n" \
                            f"👥 CAISSIÈRE ÉMETTRICE : {caissiere_v}\n" \
                            f"💳 NET TTC ENCAISSÉ    : {net_ttc}\n" \
                            f"--------------------------------------------------\n" \
                            f"📦 MARCHANDISES ACHETÉES :\n{articles_complets_bd.replace(', ', '\n')}\n\n" \
                            f"🔍 IMEI / SPÉCIFICATIONS TECHNIQUES :\n{imei_complets_bd.replace(' | ', '\n')}"
                            
        texte_details.insert(tk.END, contenu_affichage)
        texte_details.config(state=tk.DISABLED)
        
        tk.Button(pop_detail, text="❌ FERMER", bg="#dc2626", fg="white", font=("Helvetica", 9, "bold"), command=pop_detail.destroy).pack(fill=tk.X, pady=5)

    # =====================================================================
    # 📊 MOTEUR DE RECHARGE DU TIROIR-CAISSE PERSONNEL (AVEC SÉCURITÉ TUPLE)
    # =====================================================================
    def rafraichir_historique_caissiere_local(filtrer=False):
        valeur = entree_cible_historique.get().strip()
        periode_choisie = select_tempo.get() # "JOUR", "MOIS" ou "ANNEE"

        if filtrer and not valeur:
            messagebox.showwarning("Critère manquant", "Veuillez saisir une valeur cible pour lancer le filtrage.")
            return

        # Vidage propre de la grille avant rechargement
        for item in arbre_historique.get_children(): 
            arbre_historique.delete(item)
            
        ventes = data_base.recuperer_ventes_par_caissiere(caissiere_nom)
        total_ttc = 0.0

        for index, v in enumerate(ventes, start=1):
            if isinstance(v, (tuple, list)) and len(v) >= 4:
                num_id = v[0]
                client_nom = str(v[1]).upper()
                articles_bruts = str(v[2]).upper()
                net_ttc_total = f"{float(v[6]):,} FCFA" if len(v) > 6 else f"{float(v[3]):,} FCFA"
                
                # 🟢 EXTRACTION SÉCURISÉE DE LA VRAIE DATE DE VENTE (Format stocké: DD/MM/YYYY)
                date_facture = str(v[8]).strip() if len(v) > 8 else (str(v[4]).strip() if len(v) > 4 else "")
                
                if not date_facture:
                    continue

                # =====================================================================
                # 🔍 LE COEUR DU FILTRAGE CHIRURGICAL ET STRICT DEMANDÉ
                # =====================================================================
                if filtrer:
                    garder_ligne = False
                    
                    # Cas 1 : JOUR -> On attend un format strict DD/MM/YYYY (ex: 29/09/2026)
                    if periode_choisie == "JOUR":
                        if date_facture == valeur:
                            garder_ligne = True
                            
                    # Cas 2 : MOIS -> On attend un format strict MM/YYYY (ex: 09/2026)
                    elif periode_choisie == "MOIS":
                        # On vérifie si la date de la facture se termine par le bloc recherché (ex: /09/2026)
                        valeur_mois_propre = valeur if valeur.startswith("/") else f"/{valeur}"
                        if date_facture.endswith(valeur_mois_propre):
                            garder_ligne = True
                            
                    # Cas 3 : ANNEE -> On attend un format strict YYYY (ex: 2026)
                    elif periode_choisie == "ANNEE":
                        if date_facture.endswith(valeur):
                            garder_ligne = True
                    
                    # Si la ligne ne correspond pas au critère, on passe immédiatement à la suivante
                    if not garder_ligne:
                        continue

                # Insertion propre dans le tableau de la caissière
                articles_visuels = articles_bruts if len(articles_bruts) < 32 else articles_bruts[:30] + "..."
                arbre_historique.insert("", tk.END, values=(num_id, client_nom, articles_visuels, net_ttc_total, date_facture, caissiere_nom.upper()))
                
                try:
                    prix_extraction = float(v[6]) if len(v) > 6 else float(v[3])
                    total_ttc += prix_extraction
                except Exception:
                    pass
            else:
                # Sécurité de secours si la base contient une ancienne ligne plate
                if filtrer: continue
                arbre_historique.insert("", tk.END, values=(str(index), "ACHAT UNIQUE", str(v).upper()[:30], "Voir Reçu", "29/09/2026", caissiere_nom.upper()))

        # Mise à jour instantanée du grand bandeau vert des calculs cumulés
        label_total.config(text=f"MON TOTAL COMPTABLE CUMULÉ : {total_ttc:,} FCFA")


    # Interface Graphique de l'historique
    historique = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    historique.title(f"📊 Mon Historique Commercial - Session {caissiere_nom.upper()}")
    historique.geometry("750x620")
    historique.configure(bg="#f8fafc")
    historique.grab_set()

    tk.Label(historique, text=f"HISTORIQUE DES VENTES PERSONNEL - {caissiere_nom.upper()}", font=("Helvetica", 11, "bold"), bg="#1e293b", fg="white", pady=8).pack(fill=tk.X)

    cadre_stat = tk.LabelFrame(historique, text="Suivi Temporel de mon Tiroir-Caisse", bg="#f8fafc", padx=10, pady=8)
    cadre_stat.pack(fill=tk.X, padx=15, pady=10)

    tk.Label(cadre_stat, text="Période :", bg="#f8fafc").grid(row=0, column=0, padx=5, sticky=tk.W)
    select_tempo = ttk.Combobox(cadre_stat, values=["JOUR", "MOIS", "ANNEE"], width=10, state="readonly")
    select_tempo.grid(row=0, column=1, padx=5); select_tempo.current(0)

    tk.Label(cadre_stat, text="Cible (ex: 29/09/2026) :", bg="#f8fafc").grid(row=0, column=2, padx=5, sticky=tk.W)
    entree_cible_historique = tk.Entry(cadre_stat, width=15, font=("Helvetica", 10), bd=2)
    entree_cible_historique.grid(row=0, column=3, padx=5)
    entree_cible_historique.bind("<Return>", lambda event: rafraichir_historique_caissiere_local(filtrer=True))

    tk.Button(cadre_stat, text="🔍 FILTRER", bg="#1e293b", fg="white", font=("Helvetica", 9, "bold"), command=lambda: rafraichir_historique_caissiere_local(filtrer=True)).grid(row=0, column=4, padx=5)
    tk.Button(cadre_stat, text="📋 TOUT AFFICHER", bg="#0284c7", fg="white", font=("Helvetica", 9, "bold"), command=lambda: rafraichir_historique_caissiere_local(filtrer=False)).grid(row=0, column=5, padx=5)

    label_total = tk.Label(historique, text="MON TOTAL COMPTABLE CUMULÉ : 0.00 FCFA", font=("Helvetica", 11, "bold"), bg="#d1fae5", fg="#065f46", pady=6)
    label_total.pack(fill=tk.X, padx=15, pady=2)

    cadre_arbre = tk.Frame(historique, bg="#f8fafc")
    cadre_arbre.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    arbre_historique = ttk.Treeview(cadre_arbre, columns=("ID", "Client", "Article", "Total TTC", "Date/Heure", "Caissière"), show="headings", height=12)
    arbre_historique.heading("ID", text="N°"); arbre_historique.heading("Client", text="CLIENT"); arbre_historique.heading("Article", text="ARTICLE"); arbre_historique.heading("Total TTC", text="NET TTC"); arbre_historique.heading("Date/Heure", text="TEMPOREL"); arbre_historique.heading("Caissière", text="EMETTEUR")
    arbre_historique.column("ID", width=40, anchor=tk.CENTER); arbre_historique.column("Client", width=120, anchor=tk.W); arbre_historique.column("Article", width=180, anchor=tk.W); arbre_historique.column("Total TTC", width=110, anchor=tk.CENTER); arbre_historique.column("Date/Heure", width=140, anchor=tk.CENTER); arbre_historique.column("Caissière", width=100, anchor=tk.CENTER)
    
    # 🟢 ANCRAGE INDUSTRIALISÉ DE LA SCROLLBAR LONG TERME
    scroll_historique = ttk.Scrollbar(cadre_arbre, orient="vertical", command=arbre_historique.yview)
    arbre_historique.configure(yscrollcommand=scroll_historique.set)
    arbre_historique.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll_historique.pack(side=tk.RIGHT, fill=tk.Y)

    # 🟢 ANCRAGE ÉVÉNEMENT DU DOUBLE-CLIC POUR LE PANNEAU CAISSIÈRE
    arbre_historique.bind("<Double-1>", action_double_clic_detail_caissiere)

    # Allumage automatique immédiat dès l'ouverture du panneau orange
    rafraichir_historique_caissiere_local(filtrer=False)


# --- LOGIQUE SÉCURITÉ COMPTOIR : VERIFICATION DES ACCÈS ET CONTRÔLE DE LICENCE SAAS ---
def verifier_acces():
    """Valide la session employé. 
    Si le compte n'existe pas localement, interroge en direct le Cloud Render PostgreSQL 
    et l'enregistre immédiatement en local en cas de succès pour accélérer le futur.
    """
    global SESSION_UTILISATEUR, NOM_CAISSIERE_ACTIVE
    user = entree_user.get().strip().lower()
    pwd = entree_password.get().strip()

    if not user or not pwd:
        messagebox.showwarning("Champs vides", "Saisissez l'identifiant et le mot de passe.")
        return

    try:
        # Allumage préventif des structures locales SQLite
        data_base.initialisation_systeme()

        # Lecture initiale pour savoir si la boutique est déjà installée
        connexion = sqlite3.connect(data_base.DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("SELECT mot_de_passe FROM employes WHERE identifiant = 'gerant'")
        ligne_pwd = curseur.fetchone()
        
        curseur.execute("SELECT valeur FROM configuration WHERE cle = 'nom_boutique'")
        ligne_boutique = curseur.fetchone()
        connexion.close()

        mot_de_passe_actuel_db = ligne_pwd[0] if ligne_pwd else "serge2026"
        boutique_installee = ligne_boutique is not None

        # =====================================================================
        # 🚨 CAS 1 : CONFIGURATION INITIALE ABSOLUE (PREMIER ALLUMAGE DE L'HISTOIRE)
        # =====================================================================
        if not boutique_installee and mot_de_passe_actuel_db == "serge2026":
            if user == "gerant" and pwd == "serge2026":
                nom_magasin = simpledialog.askstring("Configuration Boutique - Étape 1/2", "Bienvenue chez KashKeeper !\n\nVeuillez entrer le NOM OFFICIEL de votre entreprise :")
                if not nom_magasin or not nom_magasin.strip():
                    messagebox.showwarning("Incomplet", "Un nom est exigé pour l'entreprise ou la boutique")
                    return

                creer_code = simpledialog.askstring("Configuration Boutique - Étape 2/2", "Veuillez définir votre MOT DE PASSE personnalisé définitif :")
                if not creer_code or len(creer_code.strip()) < 6 or creer_code.strip() == "serge2026":
                    messagebox.showerror("Erreur", "Le mot de passe exige un minimum de 6 caractères.")
                    return

                data_base.enregistrer_nom_boutique_sql(nom_magasin.strip())
                data_base.configurer_compte_gerant_sql(creer_code.strip())
                
                messagebox.showinfo("Succès", f"Félicitations !\nL'entreprise '{nom_magasin.strip().upper()}' est activée.\n\nConnectez-vous maintenant.")
                entree_password.delete(0, tk.END)
                entree_password.focus()
                return
            else:
                messagebox.showerror("Accès Refusé", "Code d'initialisation d'usine incorrect.")
                return

        # Sécurité mot de passe d'origine expiré
        if pwd == "serge2026" and mot_de_passe_actuel_db != "serge2026":
            messagebox.showerror("Accès Refusé", "Ce mot de passe d'usine a expiré après la configuration initiale.")
            return

        # =====================================================================
        # 🌐 CAS 2 : DEUXIÈME ALLUMAGE ET UTILISATION QUOTIDIENNE (TA LOGIQUE CLOUD EXCLUSIVEMENT)
        # =====================================================================
        
        # Étape A : Si c'est une caissière (pas le gérant), on va d'abord tenter de rafraîchir en direct depuis Render
        if user != "gerant" and URL_API_KASHFLOW and CLE_API_KASHFLOW:
            try:
                print("⏳ [CLOUD] Interrogation préventive de Render pour authentification caissière...")
                headers = {"X-API-Key": CLE_API_KASHFLOW}
                # On force le téléchargement des fiches employés créées sur la machine gérant
                rep_emp = requests.get(f"{URL_API_KASHFLOW}/boutique/telecharger-employes", headers=headers, timeout=10)
                if rep_emp.status_code == 200:
                    employes = rep_emp.json().get("employes", [])
                    
                    # On ouvre le SQLite local pour inscrire directement le compte trouvé dans le Cloud
                    conn_sync = sqlite3.connect(data_base.DB_NAME)
                    for emp in employes:
                        user_emp = emp[0] if isinstance(emp, list) else emp.get("identifiant")
                        pass_emp = emp[1] if isinstance(emp, list) else emp.get("mot_de_passe")
                        sal_emp = emp[3] if isinstance(emp, list) else emp.get("salaire")
                        
                        # 🟢 GRAVURE EN BASE LOCALE DIRECTE : On écrase ou on insère pour accélérer la prochaine connexion hors-ligne
                        conn_sync.execute("""
                            INSERT INTO employes (identifiant, mot_de_passe, applique_tva, salaire) 
                            VALUES (?, ?, 1, ?)
                            ON CONFLICT(identifiant) DO UPDATE SET mot_de_passe = ?, salaire = ?
                        """, (user_emp, pass_emp, sal_emp, pass_emp, sal_emp))
                    conn_sync.commit()
                    conn_sync.close()
                    print("✅ [CLOUD] Compte caissière synchronisé et gravé localement !")
            except Exception as err_cloud:
                print(f"📡 [CLOUD] Serveur injoignable au clic, authentification basée sur la mémoire locale : {err_cloud}")

        # Étape B : Vérification finale des identifiants (qu'ils viennent d'être synchronisés à l'instant ou lus du disque local)
        if data_base.verifier_identifiants_sql(user, pwd):
            autorisation_ouvrir_comptoir = True
            
            # Contrôle de sécurité de la licence SaaS
            try:
                reponse_licence = requests.get(f"{URL_API_KASHFLOW}/licence/statut", headers={"X-API-Key": CLE_API_KASHFLOW}, timeout=10)
                if reponse_licence.status_code == 200:
                    infos = reponse_licence.json()
                    statut_serveur = infos.get("statut", "actif")
                    jours_restants = infos.get("jours_restants", 0)

                    if statut_serveur == "expire":
                        conn = sqlite3.connect(data_base.DB_NAME)
                        row_secours = conn.execute("SELECT valeur FROM configuration WHERE cle = 'licence_secours_expire'").fetchone()
                        conn.close()
                        
                        autorisation_ouvrir_comptoir = False
                        if row_secours:
                            date_exp_secours = datetime.strptime(row_secours[0], "%d/%m/%Y")
                            if (date_exp_secours - datetime.now()).days >= 0:
                                autorisation_ouvrir_comptoir = True
                        
                        if not autorisation_ouvrir_comptoir:
                            messagebox.showerror("Abonnement Expiré", "🚨 COMPTOIR  VERROUILLÉ !")
                            return 
                    elif statut_serveur == "grace":
                        messagebox.showwarning("Avertissement Grâce", f"⚠️ MODE TOLÉRANCE ACTIF :\nIl vous reste {jours_restants} jour(s) avant blocage.")
            except Exception as e:
                logging.warning("Liaison contrôle licence asynchrone hors-ligne : %s", e)

            if autorisation_ouvrir_comptoir:
                SESSION_UTILISATEUR = str(user).strip().lower()
                NOM_CAISSIERE_ACTIVE = str(user).strip().lower()
                messagebox.showinfo("Accès Autorisé", f"Bienvenue {SESSION_UTILISATEUR.upper()} !")
                FENETRE_PRINCIPALE_LOGIN.withdraw()
                
                # Téléchargement asynchrone du catalogue de stocks une fois connecté pour mettre à jour la grille
                threading.Thread(target=rafraichir_donnees_locales_depuis_cloud, daemon=True).start()
                
                lancer_thread_synchronisation_asynchrone()
                ouvrir_comptoir_facturation()
        else:
            messagebox.showerror("Accès Refusé", "Identifiant ou mot de passe incorrect.")
            
    except Exception as e:
        messagebox.showerror("Erreur", f"Erreur système : {str(e)}")



def recuperer_mot_de_passe_oublie():
    """Permet la récupération par clé master avec une interface de saisie masquée par des étoiles (*)."""
    try:
        connexion = sqlite3.connect(data_base.DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("SELECT mot_de_passe FROM employes WHERE identifiant = 'gerant'")
        res = curseur.fetchone()
        connexion.close()

        # 🛑 BLOCAGE DE LA FAILLE : Interdit si l'utilisateur n'a pas encore fait le premier démarrage
        if res and res[0] == "serge2026":
            messagebox.showwarning("Action Impossible", "Veuillez d'abord vous connecter normalement avec le code d'usine pour configurer la boutique.")
            return

        def valider_cle_secours():
            cle_saisie = entree_cle.get().strip()
            if cle_saisie == CLE_MASTER_SERGE:
                fenetre_cle.destroy()
                # Demande du nouveau mot de passe personnalisé
                nouveau_code = simpledialog.askstring("Réinitialisation", "Clé correcte !\nTapez votre nouveau mot de passe gérant :", show="*")
                if nouveau_code and nouveau_code.strip():
                    data_base.configurer_compte_gerant_sql(nouveau_code.strip())
                    messagebox.showinfo("Succès", "Mot de passe réinitialisé avec succès ! Connectez-vous.")
            else:
                messagebox.showerror("Accès Refusé", "Clé de secours invalide.")
                entree_cle.delete(0, tk.END)

        # 🔑 CREATION D'UNE BOÎTE DE DIALOGUE SÉCURISÉE SUR-MESURE
        fenetre_cle = Toplevel(FENETRE_PRINCIPALE_LOGIN)
        fenetre_cle.title("Sécurité Constructeur")
        fenetre_cle.geometry("320x150")
        fenetre_cle.configure(bg="#1e293b")
        fenetre_cle.resizable(False, False)
        fenetre_cle.grab_set()

        tk.Label(
            fenetre_cle, 
            text="ENTREZ LA CLÉ DE SECOURS INGÉNIEUR :", 
            font=("Helvetica", 9, "bold"), 
            bg="#1e293b", 
            fg="white"
        ).pack(pady=12)

        # 🟢 CORRIGÉ : L'option show="*" masque instantanément la saisie à l'écran
        entree_cle = tk.Entry(fenetre_cle, font=("Helvetica", 11), show="*", bd=2, justify=tk.CENTER)
        entree_cle.pack(fill=tk.X, padx=30, pady=5)
        entree_cle.focus()
        
        entree_cle.bind("<Return>", lambda event: valider_cle_secours())

        tk.Button(
            fenetre_cle, 
            text="🔓 VÉRIFIER LA CLÉ", 
            font=("Helvetica", 9, "bold"), 
            bg="#3b82f6", 
            fg="white", 
            command=valider_cle_secours
        ).pack(fill=tk.X, padx=30, pady=10)

    except Exception as e:
        messagebox.showerror("Erreur", f"Erreur système : {str(e)}")


def action_telecharger_mise_a_jour():
    """Interroge le Cloud Render, télécharge le nouveau code et remplace le fichier actuel à chaud."""
    if not URL_API_KASHFLOW or not CLE_API_KASHFLOW:
        messagebox.showerror("Réseau", "Configuration réseau manquante dans config.txt.")
        return
        
    confirmation = messagebox.askyesno("Mise à jour à distance", "Voulez-vous vérifier si une mise à jour ou une nouvelle fonctionnalité est disponible pour votre boutique ?")
    if not confirmation:
        return

    try:
        reponse = requests.get(
            f"{URL_API_KASHFLOW}/systeme/mise-a-jour",
            headers={"X-API-Key": CLE_API_KASHFLOW},
            timeout=15
        )
        
        if reponse.status_code == 200:
            donnees = reponse.json()
            nouveau_code = donnees.get("code")
            
            if not nouveau_code or "import tkinter" not in nouveau_code:
                messagebox.showerror("Erreur", "Le code reçu du serveur est incomplet ou corrompu.")
                return
                
            chemin_local_actuel = os.path.abspath(__file__)
            
            # Remplacement à chaud du script d'interface sur la machine du client
            with open(chemin_local_actuel, "w", encoding="utf-8") as f:
                f.write(nouveau_code)
                
            messagebox.showinfo("Succès absolu", "🚀 KASHFLOW MANAGER a été mis à jour avec succès à distance !\n\nLe logiciel va redémarrer pour activer les nouvelles fonctionnalités.")
            login.destroy()
        else:
            messagebox.showinfo("Logiciel à jour", "✨ Votre système KashFlow possède déjà la dernière version d'usine disponible.")
    except Exception as e:
        messagebox.showerror("Échec réseau", f"Impossible de joindre le serveur Cloud pour la mise à jour :\n{e}")


def ouvrir_fenetre_paiement():
    """Fenêtre de paiement SaaS CamPay (Momo Cameroun) et PaySika (Carte Internationale Visa/MC)."""
    def action_declencher_prelevement():
        num_momo = entree_numero_momo.get().strip()
        if mode_paiement.get() == "MOMO" and (not num_momo or len(num_momo) < 9):
            messagebox.showwarning("Numéro invalide", "Entrez un numéro valide à 9 chiffres.")
            return
        if mode_paiement.get() != "MOMO":
            num_momo = "CARTE_BANCAIRE"

        btn_payer.config(text="🔄 APPEL RÉSEAU EN COURS...", state=tk.DISABLED, bg="#475569")
        fenetre_paye.update_idletasks()

        try:
            reponse = requests.post(f"{URL_API_KASHFLOW}/licence/collecter-momo", json={"numero": num_momo}, headers={"X-API-Key": CLE_API_KASHFLOW}, timeout=15)
            if reponse.status_code == 200:
                donnees = reponse.json()
                if donnees.get("statut") == "SUCCESS_CARD":
                    webbrowser.open(donnees.get("lien_web"))
                else:
                    messagebox.showinfo("Paiement Initié", f"📱 {donnees.get('message')}\n\nSi vous rencontrez des blocages de documents, contactez l'ingénieur Serges sur WhatsApp.")
                fenetre_paye.destroy()
            else:
                try: error_msg = reponse.json().get("detail", "Refus de la passerelle.")
                except Exception: error_msg = "Erreur de communication."
                messagebox.showerror("Échec", f"🔴 {error_msg}\n\nEn cas de problème réglementaire, contactez le support WhatsApp constructeur.")
                btn_payer.config(text="🚀 DEMANDER LE RETRAIT SÉCURISÉ", state=tk.NORMAL, bg="#10b981")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de joindre Render :\n{e}")
            btn_payer.config(text="🚀 DEMANDER LE RETRAIT SÉCURISÉ", state=tk.NORMAL, bg="#10b981")

    def toggle_champs_paiement():
        if mode_paiement.get() == "MOMO":
            cadre_input.pack(fill=tk.X, pady=10, before=btn_payer)
        else:
            cadre_input.pack_forget()

    fenetre_paye = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    fenetre_paye.title("💳 Renouvellement Abonnement - Caisse Pro")
    fenetre_paye.geometry("440x420")
    fenetre_paye.configure(bg="#1e293b")
    fenetre_paye.resizable(False, False)
    fenetre_paye.grab_set()

    tk.Label(fenetre_paye, text="RENOUVELLEMENT DE L'ABONNEMENT ", font=("Segoe UI", 11, "bold"), bg="#1e293b", fg="#f59e0b").pack(pady=15)
    
    cadre_choix = tk.Frame(fenetre_paye, bg="#1e293b")
    cadre_choix.pack(pady=5)
    mode_paiement = tk.StringVar(value="MOMO")

    tk.Radiobutton(cadre_choix, text="📱 Mobile Money ", variable=mode_paiement, value="MOMO", bg="#1e293b", fg="white", selectcolor="#1e293b", font=("Segoe UI", 9, "bold"), command=toggle_champs_paiement).pack(side=tk.LEFT, padx=15)
    tk.Radiobutton(cadre_choix, text="💳 Carte Bancaire / Cartes Visa / Mastercard", variable=mode_paiement, value="CARD", bg="#1e293b", fg="white", selectcolor="#1e293b", font=("Segoe UI", 9, "bold"), command=toggle_champs_paiement).pack(side=tk.LEFT, padx=15)

    cadre_texte = tk.Frame(fenetre_paye, bg="#1e293b", padx=20)
    cadre_texte.pack(fill=tk.X)
    tk.Label(cadre_texte, text="Tarif mensuel : 14 000 FCFA", font=("Segoe UI", 10, "bold"), bg="#1e293b", fg="#cbd5e1").pack(anchor=tk.W, pady=5)

    cadre_input = tk.Frame(fenetre_paye, bg="#1e293b", padx=20)
    cadre_input.pack(fill=tk.X, pady=5)
    
    entree_numero_momo = tk.Entry(cadre_input, font=("Segoe UI", 13, "bold"), bg="white", fg="#1e293b", justify=tk.CENTER)
    entree_numero_momo.pack(fill=tk.X, ipady=4)
    entree_numero_momo.insert(0, "6")

    # =====================================================================
    # 🔑 ALGORITHME CHIRURGICAL DE SÉCURITÉ : VÉRIFICATION DU CODE WHATSAPP
    # =====================================================================
    def action_activer_par_cle_secours_whatsapp():
        cle_client = str(CLE_API_KASHFLOW).strip()
        code_saisi = simpledialog.askstring("Activation Manuelle", "Saisissez la clé d'activation mensuelle fournie par l'ingénieur :", parent=fenetre_paye)
        if not code_saisi: return
        
        import hashlib
        maintenant = datetime.now()
        # Génération du jeton d'usine basé sur la clé, le mois et l'année en cours (Octobre 2026)
        sel_secret = f"{cle_client}-{maintenant.month}-{maintenant.year}-KASHKEEPER-SERGE"
        signature_attendue = hashlib.md5(sel_secret.encode("utf-8")).hexdigest().upper()[:8]
        
        # Format strict de la clé : KASH-XXXX-XXXX
        code_officiel_attendu = f"KASH-{signature_attendue[:4]}-{signature_attendue[4:]}"
        
        if code_saisi.strip().upper() == code_officiel_attendu:
            try:
                # Écriture immédiate sur le disque local de la caisse pour +30 jours
                conn = sqlite3.connect(data_base.DB_NAME)
                conn.execute("INSERT OR REPLACE INTO configuration (cle, valeur) VALUES ('licence_secours_expire', ?)", 
                             ((maintenant + timedelta(days=30)).strftime("%d/%m/%Y"),))
                conn.commit()
                conn.close()
                messagebox.showinfo("✨ Succès Absolu", "FÉLICITATIONS, COMPTOIR DE VENTE DÉBLOQUÉ !\n\nVotre application a été réactivée localement avec succès pour 30 jours.")
                fenetre_paye.destroy()
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible d'enregistrer la clé de secours : {e}")
        else:
            messagebox.showerror("Accès Refusé", "Clé d'activation mensuelle invalide ou expirée.\n\nVeuillez contacter votre support technique.")

    # 🟢 BOUTON 1 (D'ORIGINE RESTAURÉ) : Option automatique conservée intacte pour plus tard
    btn_payer = tk.Button(fenetre_paye, text="🚀  DEMANDER LE RETRAIT SÉCURISÉ", bg="#10b981", fg="white", font=("Segoe UI", 10, "bold"), bd=0, cursor="hand2", command=action_declencher_prelevement, pady=6)
    btn_payer.pack(fill=tk.X, padx=20, pady=10)
    btn_payer.config(text="🚀 DEMANDER LE RETRAIT SÉCURISÉ", state=tk.NORMAL, bg="#10b981")

    # 🟢 BOUTON 2 (NOUVEAU) : Utiliser la clé d'activation manuelle Orange Money / MTN MoMo
    btn_cle_manuel = tk.Button(fenetre_paye, text="🔑  UTILISER LA CLÉ D'ACTIVATION MANUELLE", bg="#f59e0b", fg="white", font=("Segoe UI", 10, "bold"), bd=0, cursor="hand2", command=action_activer_par_cle_secours_whatsapp, pady=6)
    btn_cle_manuel.pack(fill=tk.X, padx=20, pady=5)
    
    # 🟢 BOUTON 3 (D'ORIGINE CONSERVÉ) : Fermeture de la boîte de dialogue
    tk.Button(fenetre_paye, text="ANNULER", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9, "underline"), bd=0, cursor="hand2", command=fenetre_paye.destroy).pack()


def ouvrir_fenetre_modification_mdp_caissiere():
    """Ouvre une interface sécurisée permettant à la caissière connectée de changer son mot de passe."""
    caissiere_active = str(NOM_CAISSIERE_ACTIVE).strip().lower()

    # Demande de l'ancien mot de passe pour vérification de sécurité
    ancien_pwd = simpledialog.askstring("Sécurité", "Entrez votre mot de passe ACTUEL :", show="*")
    if not ancien_pwd: return

    # Vérification stricte dans la base de données locale
    if not data_base.verifier_identifiants_sql(caissiere_active, ancien_pwd.strip()):
        messagebox.showerror("Authentification échouée", "Mot de passe actuel incorrect. Modification annulée.")
        return

    # Saisie du nouveau mot de passe
    nouveau_pwd = simpledialog.askstring("Nouveau code", "Entrez votre NOUVEAU mot de passe (min 4 caractères) :", show="*")
    if not nouveau_pwd or len(nouveau_pwd.strip()) < 4:
        messagebox.showerror("Erreur", "Le mot de passe doit comporter au moins 4 caractères.")
        return

    confirmation_pwd = simpledialog.askstring("Confirmation", "Confirmez votre nouveau mot de passe :", show="*")
    if nouveau_pwd.strip() != confirmation_pwd.strip():
        messagebox.showerror("Erreur", "Les deux mots de passe ne correspondent pas.")
        return

    # Gravure immédiate du nouveau mot de passe en base de données local
    try:
        connexion = sqlite3.connect(data_base.DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("UPDATE employes SET mot_de_passe = ? WHERE identifiant = ?", (nouveau_pwd.strip(), caissiere_active))
        connexion.commit()
        connexion.close()
        messagebox.showinfo("Succès", "✨ Votre mot de passe secret a été modifié avec succès ! Utilisez-le à votre prochaine connexion.")
    except Exception as e:
        messagebox.showerror("Erreur système", f"Impossible de modifier le mot de passe : {e}")


# --- CONFIGURATION ET ALLUMAGE DE L'ÉCRAN GRAPHIQUE RACINE WINDOWS ---
login = tk.Tk()
FENETRE_PRINCIPALE_LOGIN = login
login.title("Sécurité d'Accès")
login.geometry("350x460")
login.configure(bg="#1e293b")
login.resizable(False, False)

tk.Label(login, text="CONNEXION SÉCURISÉE", font=("Helvetica", 12, "bold"), bg="#1e293b", fg="white").pack(pady=20)
boite = tk.Frame(login, bg="#1e293b", padx=30)
boite.pack(fill=tk.X)

tk.Label(boite, text="Identifiant Employé :", bg="#1e293b", fg="#cbd5e1").pack(anchor=tk.W)
entree_user = tk.Entry(boite, font=("Helvetica", 11), bd=2)
entree_user.pack(fill=tk.X, pady=5)
entree_user.insert(0, "gerant")

tk.Label(boite, text="Mot de passe secret :", bg="#1e293b", fg="#cbd5e1").pack(anchor=tk.W)
entree_password = tk.Entry(boite, font=("Helvetica", 11), show="*", bd=2)
entree_password.pack(fill=tk.X, pady=5)

# 🟢 RESTAURATION DES CHAINES CLAVIER CORRECTES
entree_user.bind("<Return>", lambda event: entree_password.focus())
entree_password.bind("<Return>", lambda event: verifier_acces())

# Boutons d'allumage des interfaces
tk.Button(login, text="🔓 ACCÉDER AU COMPTOIR", font=("Helvetica", 11, "bold"), bg="#3b82f6", fg="white", command=verifier_acces).pack(fill=tk.X, padx=30, pady=12)
tk.Button(login, text="🔄 VÉRIFIER LES MISES À JOUR", font=("Helvetica", 10, "bold"), bg="#475569", fg="white", command=action_telecharger_mise_a_jour).pack(fill=tk.X, padx=30, pady=5)
tk.Button(login, text="❓ Mot de passe oublié / Réinitialiser", font=("Helvetica", 9, "underline"), bg="#1e293b", fg="#94a3b8", bd=0, command=recuperer_mot_de_passe_oublie, cursor="hand2").pack(pady=5)

# --- ENCADREMENT BAS DE LA PAGE DE CONNEXION ---
cadre_bas = tk.Frame(login, bg="#1e293b")
cadre_bas.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=10)

def action_ouvrir_support_manuel():
    """Ouvre une fenêtre pop-up propre affichant les coordonnées de l'ingénieur pour activation manuelle."""
    pop_support = Toplevel(login)
    pop_support.title("📞 Activation Manuelle & Support Technique")
    pop_support.geometry("380x250")
    pop_support.configure(bg="#1e293b")
    pop_support.resizable(False, False)
    pop_support.grab_set()

    tk.Label(pop_support, text="SUPPORT TECHNIQUE KASHKEEPER", font=("Helvetica", 10, "bold"), bg="#1e293b", fg="#cbd5e1").pack(pady=10)
    
    # Message d'explication clair pour le gérant
    texte_rh = "NOTRE passerelle de paiement automatisée est en cours de maintenance réglementaire.\n\nPour renouveller manuellement votre abonnement mensuel (14 000 FCFA), veuillez utiliser l'un des contacts suivant:"
    tk.Label(pop_support, text=texte_rh, font=("Helvetica", 9), bg="#1e293b", fg="#94a3b8", wrap=340, justify=tk.CENTER).pack(padx=15, pady=5)

    # Coordonnées réelles à afficher (À adapter avec tes vrais numéros)
    tk.Label(pop_support, text="📱 Téléphone / WhatsApp : +237 6 86 08 15 12 | 683 10 63 38 ", font=("Helvetica", 10, "bold"), bg="#1e293b", fg="#f59e0b").pack(pady=2)
    tk.Label(pop_support, text="✉️ E-mail d'audit : zidaneserges@gmail.com", font=("Helvetica", 10, "bold"), bg="#1e293b", fg="#3b82f6").pack(pady=2)

    tk.Button(pop_support, text="❌ FERMER", font=("Helvetica", 9, "bold"), bg="#dc2626", fg="white", bd=0, command=pop_support.destroy, padx=10, pady=4).pack(pady=15)

# 🟢 AJOUTÉ : Le petit bouton Contact à l'extrême inférieur GAUCHE
btn_contact = tk.Button(
    cadre_bas, 
    text="📞 CONTACT SUPPORT", 
    font=("Helvetica", 8, "bold", "underline"), 
    bg="#1e293b", 
    fg="#94a3b8", 
    bd=0, 
    cursor="hand2", 
    command=action_ouvrir_support_manuel
)
btn_contact.pack(side=tk.LEFT)

# Le bouton orange de renouvellement de licence reste à l'extrême DROITE (Masqué ou inactif selon tes besoins)
btn_abonnement = tk.Button(
    cadre_bas, 
    text="💳 PAYER ABONNEMENT", 
    font=("Helvetica", 8, "bold", "underline"), 
    bg="#1e293b", 
    fg="#f59e0b", 
    bd=0, 
    cursor="hand2", 
    command=ouvrir_fenetre_paiement
)
btn_abonnement.pack(side=tk.RIGHT)

def lancer_moteur_hybride_synchro_cloud():
    """ thread invisible qui propulse les ventes vers Render PostgreSQL quand Internet est actif. """
    def boucle_traitement():
        while True:
            try:
                # 1. Extraction des lignes locales non encore synchronisées (synchro = 0)
                conn = sqlite3.connect(data_base.DB_NAME)
                ventes_locales = conn.execute("""
                    SELECT id, client, article, description_unique, montant_ht, tva, total_ttc, caissiere, jour || '/' || mois || '/' || annee || ' ' || heure 
                    FROM ventes WHERE synchro = 0 LIMIT 10
                """).fetchall()
                conn.close()
                
                if ventes_locales and URL_API_KASHFLOW and CLE_API_KASHFLOW:
                    paquet_ventes = []
                    for v in ventes_locales:
                        paquet_ventes.append({
                            "id_local": v[0], "client": v[1], "article": v[2], "description_unique": v[3],
                            "montant_ht": v[4], "tva": v[5], "total_ttc": v[6], "caissiere": v[7], "date_vente": v[8]
                        })
                    
                    # 2. Expédition vers ton API d'infrastructure
                    reponse = requests.post(
                        f"{URL_API_KASHFLOW}/sync/ventes_magasin",
                        json={"ventes": paquet_ventes},
                        headers={"X-API-Key": CLE_API_KASHFLOW},
                        timeout=15
                    )
                    
                    # 3. Si Render PostgreSQL valide, on marque synchro = 1 en local pour ne plus les renvoyer
                    if reponse.status_code == 200:
                        ids_a_marquer = reponse.json().get("ids_synchonises", [])
                        conn_up = sqlite3.connect(data_base.DB_NAME)
                        for id_l in ids_a_marquer:
                            conn_up.execute("UPDATE ventes SET synchro = 1 WHERE id = ?", (id_l,))
                        conn_up.commit()
                        conn_up.close()
            except Exception:
                pass # Internet est coupé au marché, le logiciel attend le prochain tour sans bloquer
                
            time.sleep(30) # Tourne en boucle toutes les 30 secondes

    threading.Thread(target=boucle_traitement, daemon=True).start()
# Allumage officiel du logiciel d'usine

def rafraichir_donnees_locales_depuis_cloud():
    """Télécharge les stocks et les employés depuis Render pour écraser le SQLite local."""
    global URL_API_KASHFLOW, CLE_API_KASHFLOW

    if URL_API_KASHFLOW and CLE_API_KASHFLOW:
        try:
            headers = {"X-API-Key": CLE_API_KASHFLOW}
            
            # 1. Téléchargement et synchronisation des stocks (CORRIGÉ AVEC HEADERS)
            rep_stocks = requests.get(f"{URL_API_KASHFLOW}/boutique/telecharger-stocks", headers=headers, timeout=45)
            if rep_stocks.status_code == 200:
                articles = rep_stocks.json().get("articles", [])
                conn = sqlite3.connect(data_base.DB_NAME)
                conn.execute("DELETE FROM stocks") 
                for art in articles:
                    nom_art = art[0] if isinstance(art, list) else art.get("article")
                    prix_art = art[2] if isinstance(art, list) else art.get("prix_ht")
                    qte_art = art[3] if isinstance(art, list) else art.get("quantite")
                    
                    conn.execute("INSERT INTO stocks (modele, quantite_dispo, prix_achat, ventes_cumulees) VALUES (?, ?, ?, 0)", 
                                 (nom_art, qte_art, prix_art))
                conn.commit()
                conn.close()

            # 2. Téléchargement et synchronisation des employés (CORRIGÉ AVEC HEADERS)
            rep_emp = requests.get(f"{URL_API_KASHFLOW}/boutique/telecharger-employes", headers=headers, timeout=45)
            if rep_emp.status_code == 200:
                employes = rep_emp.json().get("employes", [])
                conn = sqlite3.connect(data_base.DB_NAME)
                
                conn.execute("DELETE FROM employes WHERE identifiant != 'gerant'") 
                for emp in employes:
                    user_emp = emp[0] if isinstance(emp, list) else emp.get("identifiant")
                    pass_emp = emp[1] if isinstance(emp, list) else emp.get("mot_de_passe")
                    sal_emp = emp[3] if isinstance(emp, list) else emp.get("salaire")
                    
                    conn.execute("INSERT INTO employes (identifiant, mot_de_passe, applique_tva, salaire) VALUES (?, ?, 1, ?)", 
                                 (user_emp, pass_emp, sal_emp))
                conn.commit()
                conn.close()
                
            print("🔄 Données de la boutique synchronisées avec succès depuis le Cloud !")
        except Exception as e:
            print(f"⚠️ Impossible de rafraîchir les données (Mode hors-ligne) : {e}")

login.mainloop()

