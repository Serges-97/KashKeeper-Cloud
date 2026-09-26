# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 1 SUR 7)
# =====================================================================
import tkinter as tk
from tkinter import messagebox, simpledialog, Toplevel, ttk
import sqlite3
import logging
import os
import threading
import uuid
from datetime import datetime
import requests
import data_base
import operation
import json 
import win32print
import win32ui
# Lancement des configurations SQLite d'usine au démarrage du logiciel
data_base.initialisation_systeme()

# Variables globales de contrôle des privilèges et sécurité constructeur
SESSION_UTILISATEUR = "caissier"
NOM_CAISSIERE_ACTIVE = "Anonyme"
NOM_BOUTIQUE_FIXE = "KASHFLOW_MANAGER"
CLE_MASTER_SERGE = "Je suis simple"

URL_API_KASHFLOW = "https://onrender.com" 
CLE_API_KASHFLOW = "KASHFLOW_KEY_DEFAUT"

def imprimer_ticket_thermique_direct(client, article, total_ttc, caissiere):
    """Envoie un ticket de caisse épuré directement sur le rouleau de l'imprimante thermique."""
    try:
        nom_boutique = data_base.recuperer_nom_boutique_sql() or "KASHKEEPER BOUTIQUE"
        nom_boutique = str(nom_boutique).upper()
        nom_imprimante = win32print.GetDefaultPrinter()
        liste_imprimantes = [imp[2] for imp in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]
        
        for imp in liste_imprimantes:
            if any(mot in imp.lower() for mot in ["thermal", "pos", "58", "80", "xp-"]):
                nom_imprimante = imp
                break

        date_heure = datetime.now().strftime("%d/%m/%Y  %H:%M")
        separateur = "--------------------------------"
        
        ticket_texte = (
            f"{nom_boutique}\n"
            f"{separateur}\n"
            f"Date : {date_heure}\n"
            f"Caissiere : {str(caissiere).upper()}\n"
            f"Client : {str(client).upper()}\n"
            f"{separateur}\n"
            f"ARTICLE : {str(article).upper()}\n"
            f"{separateur}\n"
            f"TOTAL NET : {total_ttc} FCFA\n"
            f"{separateur}\n"
            f"Merci pour votre confiance !\n"
            f"A bientot.\n\n\n\n\n"
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
        logging.warning("Impression thermique ignoree ou non configuree : %s", e)

def charger_configuration_externe():
    """Lit dynamiquement la configuration du client en supportant les espaces, tirets et égaux."""
    global URL_API_KASHFLOW, CLE_API_KASHFLOW
    dossier_prog = os.path.dirname(os.path.abspath(__file__))
    fichier_config = os.path.join(dossier_prog, "config.txt")
    
    # 🟢 SÉCURITÉ CONSTRUCTEUR : Si le fichier n'existe pas, on crée le modèle propre d'usine
    if not os.path.exists(fichier_config):
        with open(fichier_config, "w", encoding="utf-8") as f:
            f.write("# CONFIGURATION RESEAU KASHFLOW MANAGER \n")
            f.write("URL_API - https://onrender.com \n")
            f.write("CLE_API - KASHFLOW_KEY_DEFAUT\n")
        return

    try:
        with open(fichier_config, "r", encoding="utf-8") as f:
            for ligne in f:
                ligne_propre = ligne.strip()
                if ligne_propre.startswith("#") or not ligne_propre:
                    continue
                
                # Détection dynamique du séparateur (soit un tiret, soit un signe égal)
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
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 2 SUR 7)
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
        "applique_tva_vente": donnees.get("applique_tva", 1)
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
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 3 SUR 7)
# =====================================================================

# =====================================================================
# 📦 PANNEAU GESTION DE L'INVENTAIRE / STOCKS (EXCLUSIVITÉ GÉRANT)
# =====================================================================
def ouvrir_panneau_stock():
    """Interface d'inventaire moderne avec barre de défilement et sécurité anti-doublons de casse."""
    if SESSION_UTILISATEUR != "gerant":
        messagebox.showerror("Accès Interdit", "Seul le gérant peut modifier l'inventaire.")
        return

    # Déclaration initiale des variables de saisie pour effacer UnboundLocalError
    global entree_modele, entree_qte_stock

    def pousser_stock_vers_cloud(modele, quantite):
        """Propulse la modification d'inventaire sur le serveur en direct."""
        if not URL_API_KASHFLOW or not CLE_API_KASHFLOW:
            return
        try:
            payload = {"modele": str(modele).strip().lower(), "quantite_dispo": int(quantite)}
            def requete():
                try: requests.post(f"{URL_API_KASHFLOW}/stocks/mettre_a_jour", json=payload, headers={"X-API-Key": CLE_API_KASHFLOW}, timeout=6)
                except Exception: pass
            threading.Thread(target=requete, daemon=True).start()
        except Exception: pass

    def action_ajouter_quantite(id_stock_cible, nom_article_cible):
        """Ajoute du stock de manière chirurgicale sur l'ID de la ligne sélectionnée."""
        qte = simpledialog.askinteger("Réapprovisionnement", f"Quantité à ajouter pour « {str(nom_article_cible).upper()} » :", parent=admin_stock, minvalue=1)
        if qte is None: return

        connexion = sqlite3.connect(data_base.DB_NAME)
        connexion.execute("UPDATE stocks SET quantite_dispo = quantite_dispo + ? WHERE id = ?", (qte, id_stock_cible))
        qte_totale = connexion.execute("SELECT quantite_dispo FROM stocks WHERE id = ?", (id_stock_cible,)).fetchone()[0]
        connexion.commit()
        connexion.close()
        
        pousser_stock_vers_cloud(nom_article_cible.strip().lower(), qte_totale)
        rafraichir_tableau()
        messagebox.showinfo("Inventaire mis à jour", "Stock augmenté avec succès.")

    def rafraichir_tableau():
        """Recharge les stocks et remplit le tableau défilant."""
        for i in tableau_stocks.get_children():
            tableau_stocks.delete(i)
        
        lignes = data_base.obtenir_tous_les_stocks_locaux()
        for id_db, modele, quantite, _ in lignes:
            tableau_stocks.insert("", tk.END, iid=str(id_db), values=(str(modele).strip().upper(), f"{quantite} pcs"))
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 4 SUR 7)
# =====================================================================

    def action_ajouter_modele():
        """Crée un nouvel article ou fusionne la quantité si le nom existe déjà (Anti-doublon)."""
        global entree_modele, entree_qte_stock
        modele = entree_modele.get().strip().lower()
        qte_texte = entree_qte_stock.get().strip()
            
        if not modele or not qte_texte:
            messagebox.showwarning("Champs vides", "Veuillez remplir le modèle et la quantité.")
            return
                
        try:
            qte = int(qte_texte)
            if qte <= 0: raise ValueError
                
            connexion = sqlite3.connect(data_base.DB_NAME)
            curseur = connexion.cursor()
            
            curseur.execute("""
            INSERT INTO stocks (modele, quantite_dispo) VALUES (?, ?)
            ON CONFLICT(modele) DO UPDATE SET quantite_dispo = quantite_dispo + ?
            """, (modele, qte, qte))
            
            curseur.execute("SELECT quantite_dispo FROM stocks WHERE lower(modele) = ?", (modele,))
            qte_totale = curseur.fetchone()
            connexion.commit()
            connexion.close()
            
            pousser_stock_vers_cloud(modele, qte_totale)
            
            messagebox.showinfo("Inventaire Mis à jour", f"L'article '{modele.upper()}' a été enregistré !")
            entree_modele.delete(0, tk.END)
            entree_qte_stock.delete(0, tk.END)
            rafraichir_tableau()
            entree_modele.focus()
        except ValueError:
            messagebox.showerror("Erreur", "La quantité doit être un entier supérieur à 0.")

    def action_supprimer_modele():
        """Supprime l'article sélectionné de façon chirurgicale par son ID unique."""
        selection = tableau_stocks.selection()
        if not selection:
            messagebox.showwarning("Sélection manquante", "Sélectionnez une ligne dans le tableau à supprimer.")
            return
            
        # 🟢 REPARÉ : Extraction de l'ID de la ligne cliquée
        id_unique_ligne = selection[0]
        item = tableau_stocks.item(id_unique_ligne)
        # 🟢 REPARÉ : On extrait le texte pur de la première colonne pour l'API
        nom_article = item["values"][0]

        if not messagebox.askyesno("Confirmation", f"Voulez-vous retirer uniquement cette ligne « {nom_article} » de l'inventaire ?"): 
            return

        connexion = sqlite3.connect(data_base.DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("DELETE FROM stocks WHERE id = ?", (id_unique_ligne,))
        article_supprime = curseur.rowcount > 0
        connexion.commit()
        connexion.close()

        if article_supprime:
            pousser_stock_vers_cloud(str(nom_article).lower(), 0)
            messagebox.showinfo("Succès", "Ligne d'article retirée avec succès.")
            rafraichir_tableau()
        else:
            messagebox.showwarning("Erreur", "Ligne introuvable.")

    def action_clic_bouton_quantite():
        """Déclenche l'ajout de quantité sur l'article sélectionné."""
        selection = tableau_stocks.selection()
        if not selection:
            messagebox.showwarning("Sélection manquante", "Veuillez cliquer sur une ligne du tableau d'abord.")
            return
        # 🟢 REPARÉ : Extraction propre des indices du tuple Tkinter
        id_cible = selection[0]
        nom_article = tableau_stocks.item(id_cible)["values"][0]
        action_ajouter_quantite(id_cible, nom_article)

    # Dessin de la fenêtre des stocks
    admin_stock = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    admin_stock.title("📦 Gestion des Stocks - Sécurisée par ID")
    admin_stock.geometry("520x540")
    admin_stock.configure(bg="#f8fafc")
    admin_stock.resizable(False, False)
    admin_stock.grab_set()

    tk.Label(admin_stock, text="INVENTAIRE DES PRODUITS EN STOCK", font=("Helvetica", 11, "bold"), bg="#0f766e", fg="white", pady=8).pack(fill=tk.X)

    cadre_conteneur = tk.Frame(admin_stock, bg="#f8fafc")
    cadre_conteneur.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    tableau_stocks = ttk.Treeview(cadre_conteneur, columns=("Article", "Quantite"), show="headings", height=10)
    tableau_stocks.heading("Article", text="DÉSIGNATION DE L'ARTICLE")
    tableau_stocks.heading("Quantite", text="STOCK DISPONIBLE")
    tableau_stocks.column("Article", width=330, anchor=tk.W)
    tableau_stocks.column("Quantite", width=130, anchor=tk.CENTER)

    defilement = ttk.Scrollbar(cadre_conteneur, orient="vertical", command=tableau_stocks.yview)
    tableau_stocks.configure(yscrollcommand=defilement.set)
    
    tableau_stocks.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    defilement.pack(side=tk.RIGHT, fill=tk.Y)

    tk.Button(admin_stock, text="➕ AJOUTER QUANTITÉ AU PRODUIT SÉLECTIONNÉ", font=("Helvetica", 9, "bold"), bg="#0f766e", fg="white", command=action_clic_bouton_quantite).pack(fill=tk.X, padx=15, pady=2)

    # Formulaire d'ajouts fixe en bas
    cadre_ajout = tk.LabelFrame(admin_stock, text="Créer ou Approvisionner un Article", font=("Helvetica", 9, "bold"), bg="#f8fafc", padx=10, pady=6)
    cadre_ajout.pack(fill=tk.X, padx=15, pady=10)

    tk.Label(cadre_ajout, text="Nom de l'article :", bg="#f8fafc").pack(anchor=tk.W)
    entree_modele = tk.Entry(cadre_ajout, font=("Helvetica", 10))
    entree_modele.pack(fill=tk.X, pady=2)

    tk.Label(cadre_ajout, text="Quantité reçue :", bg="#f8fafc").pack(anchor=tk.W)
    entree_qte_stock = tk.Entry(cadre_ajout, font=("Helvetica", 10))
    entree_qte_stock.pack(fill=tk.X, pady=2)

    entree_modele.bind("<Return>", lambda event: entree_qte_stock.focus())
    entree_qte_stock.bind("<Return>", lambda event: action_ajouter_modele())

    cadre_actions = tk.Frame(cadre_ajout, bg="#f8fafc")
    cadre_actions.pack(fill=tk.X, pady=6)
    tk.Button(cadre_actions, text="📥 ENREGISTRER / FUSIONNER", bg="#10b981", fg="white", font=("Helvetica", 9, "bold"), command=action_ajouter_modele).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    tk.Button(cadre_actions, text="🗑 SUPPRIMER LIGNE SÉLECTIONNÉE", bg="#dc2626", fg="white", font=("Helvetica", 9, "bold"), command=action_supprimer_modele).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

    rafraichir_tableau()
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 5 SUR 7)
# =====================================================================

# --- 3. PANNEAU D'AUDIT COMPTABLE TEMPOREL ET FILTRAGE VISIBLE ---
def ouvrir_panneau_historique():
    """Ouvre l'espace analytique et force l'affichage complet de la grille des ventes."""
    if SESSION_UTILISATEUR != "gerant":
        messagebox.showerror("Accès Interdit", "Seul le gérant a accès aux rapports financiers.")
        return

    def action_exporter_registre_excel():
        """Génère un fichier CSV (Excel) haute clarté directement sur le bureau du gérant."""
        import csv
        import sys
        
        # Détermination de l'emplacement dynamique du bureau de l'utilisateur
        bureau_pc = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.exists(bureau_pc):
            bureau_pc = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            
        horodatage = datetime.now().strftime("%d_%m_%Y_%H%M")
        nom_fichier_csv = os.path.join(bureau_pc, f"KashKeeper_Rapport_Ventes_{horodatage}.csv")
        
        try:
            ventes_brutes = data_base.obtenir_registre_ventes_brutes()
            if not ventes_brutes:
                messagebox.showwarning("Registre vide", "Aucune transaction enregistrée en base pour le moment.")
                return
                
            # Écriture industrielle du fichier Excel avec encodage universel anti-bug d'accents
            with open(nom_fichier_csv, mode="w", newline="", encoding="utf-8-sig") as f:
                ecrivain = csv.writer(f, delimiter=";") # Point-virgule pour l'alignement Excel automatique
                
                # Écriture de la ligne d'en-tête officielle du tableur
                ecrivain.writerow([
                    "N° FACTURE", "CLIENT", "ARTICLE / MODELE", "IMEI / SERIE / SAV", 
                    "MONTANT HT (FCFA)", "VALEUR TVA (FCFA)", "TOTAL NET TTC (FCFA)", 
                    "CAISSIERE EMETTEUR", "DATE FACTURATION", "HEURE", "SYNCHRONISÉ CLOUD"
                ])
                
                # Injection de toutes les lignes comptables
                for ligne in ventes_brutes:
                    ecrivain.writerow(ligne)
                    
            messagebox.showinfo("Exportation Réussie", f"📊 RAPPORT COMPTABLE GÉNÉRÉ !\n\nLe fichier Excel a été créé avec succès sur votre bureau sous le nom :\n« KashKeeper_Rapport_Ventes_{horodatage}.csv »")
        except Exception as e:
            messagebox.showerror("Erreur d'écriture", f"Impossible d'exportateur le fichier Excel :\n{e}")

    def action_charger_statistiques():
        tempo = select_tempo.get()
        cible = entree_cible.get().strip()
        
        if not cible:
            messagebox.showwarning("Critère manquant", "Veuillez entrer une valeur cible (ex: 31/08/2026, 08, 2026).")
            return
            
        statistiques = data_base.extraire_statistiques_avancees(tempo, cible)
        label_ca.config(text=f"CHIFFRE D'AFFAIRES TTC : {statistiques['ca_total']} FCFA", bg="#10b981", fg="white")
        label_top.config(text=f"🔥 Produit Phare sur la période : {statistiques['produit_phare']}")
        label_perf.config(text=statistiques['message_performance'])

    def action_filtrer_par_vendeuse():
        nom_vendeuse = normaliser_nom_caissiere(select_vendeuse.get())
        if not nom_vendeuse or nom_vendeuse == "anonyme":
            messagebox.showwarning("Champ vide", "Veuillez sélectionner une caissière.")
            return
            
        for i in grille_audit.get_children():
            grille_audit.delete(i)
            
        ventes_filtrees = data_base.recuperer_ventes_par_caissiere(nom_vendeuse)
        if not ventes_filtrees:
            messagebox.showinfo("Rapport", f"Aucune vente pour : {nom_vendeuse}")
            return
            
        for v in ventes_filtrees:
            facture_no = v[0]
            client = v[1]
            art_propre = str(v[2]).strip()
            montant_ttc = f"{v[3]} FCFA" if "FCFA" not in str(v[3]) else v[3]
            date_formatee = v[4]
            heure = v[5]
            grille_audit.insert("", tk.END, values=(facture_no, client, art_propre, montant_ttc, f"{date_formatee} à {heure}", nom_vendeuse.upper()))

    def action_afficher_tout_historique():
        for i in grille_audit.get_children():
            grille_audit.delete(i)
        toutes_les_ventes = data_base.recuper_tout_les_ventes()
        
        for v in toutes_les_ventes:
            facture_no = v[0]
            client = v[1]
            art_propre = str(v[2]).strip()
            montant_ttc = f"{v[3]} FCFA" if "FCFA" not in str(v[3]) else v[3]
            date_formatee = v[4]
            caissiere_nom = str(v[5]).upper()
            grille_audit.insert("", tk.END, values=(facture_no, client, art_propre, montant_ttc, date_formatee, caissiere_nom))

    audit = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    audit.title("📊 Tableau de Bord Économique")
    audit.geometry("750x650")
    audit.configure(bg="#f8fafc")
    audit.grab_set()

    tk.Label(audit, text="RAPPORT D'AUDIT COMPTABLE ANALYTIQUE", font=("Helvetica", 11, "bold"), bg="#1e293b", fg="white", pady=8).pack(fill=tk.X)

    # Zone du haut : Comparatifs et CA
    cadre_stat = tk.LabelFrame(audit, text="Analyse Temporelle Comparative (N vs N-1)", bg="#f8fafc", padx=10, pady=8)
    cadre_stat.pack(fill=tk.X, padx=15, pady=10)

    tk.Label(cadre_stat, text="Période :", bg="#f8fafc").grid(row=0, column=0, padx=5, sticky=tk.W)
    select_tempo = ttk.Combobox(cadre_stat, values=["JOUR", "MOIS", "ANNEE"], width=10, state="readonly")
    select_tempo.grid(row=0, column=1, padx=5)
    select_tempo.current(0)

    tk.Label(cadre_stat, text="Cible :", bg="#f8fafc").grid(row=0, column=2, padx=5, sticky=tk.W)
    entree_cible = tk.Entry(cadre_stat, width=12, font=("Helvetica", 10), bd=2)
    entree_cible.grid(row=0, column=3, padx=5)

    tk.Button(cadre_stat, text="🔍 ANALYSER", font=("Helvetica", 9, "bold"), bg="#1e293b", fg="white", command=action_charger_statistiques).grid(row=0, column=4, padx=10)

    label_ca = tk.Label(cadre_stat, text="CHIFFRE D'AFFAIRES TTC : 0.00 FCFA", font=("Helvetica", 11, "bold"), bg="#e2e8f0", fg="#1e293b", pady=6)
    label_ca.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=6)
    
    label_top = tk.Label(cadre_stat, text="🔥 Produit Phare : Aucun", font=("Helvetica", 10), bg="#f8fafc", fg="#0f766e", anchor=tk.W)
    label_top.grid(row=2, column=0, columnspan=5, sticky=tk.EW, pady=2)
    
    label_perf = tk.Label(cadre_stat, text="📈 En attente d'analyse...", font=("Helvetica", 10, "italic"), bg="#f8fafc", fg="#475569", anchor=tk.W)
    label_perf.grid(row=3, column=0, columnspan=5, sticky=tk.EW, pady=2)

    # Zone du bas : Le registre de la grille visible
    cadre_grille = tk.LabelFrame(audit, text="Registre des transactions et ventes", bg="#f8fafc", padx=10, pady=8)
    cadre_grille.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

    cadre_filtre_nom = tk.Frame(cadre_grille, bg="#f8fafc")
    cadre_filtre_nom.pack(fill=tk.X, pady=4)
    
    tk.Label(cadre_filtre_nom, text="Caissière :", bg="#f8fafc").pack(side=tk.LEFT, padx=2)
    
    liste_caissieres = data_base.recuperer_liste_tous_employes()
    select_vendeuse = ttk.Combobox(cadre_filtre_nom, values=liste_caissieres, width=18, state="readonly")
    if liste_caissieres:
        select_vendeuse.current(0)
    select_vendeuse.pack(side=tk.LEFT, padx=4)
    
    tk.Button(cadre_filtre_nom, text="🎯 Filtrer", bg="#475569", fg="white", font=("Helvetica", 8, "bold"), command=action_filtrer_par_vendeuse).pack(side=tk.LEFT, padx=4)
    tk.Button(cadre_filtre_nom, text="📋 Afficher Tout", bg="#0284c7", fg="white", font=("Helvetica", 8, "bold"), command=action_afficher_tout_historique).pack(side=tk.RIGHT, padx=4)

    # 🟢 INTEGRATION DU BOUTON PHYSIQUE EXCEL (A gauche de Afficher Tout pour un rendu Pro)
    tk.Button(
        cadre_filtre_nom, 
        text="📥 EXPORTER SUR EXCEL", 
        bg="#10b981", 
        fg="white", 
        font=("Helvetica", 8, "bold"), 
        command=action_exporter_registre_excel
    ).pack(side=tk.RIGHT, padx=8)

    grille_audit = ttk.Treeview(cadre_grille, columns=("ID", "Client", "Article", "Total TTC", "Date/Heure", "Émetteur"), show="headings", height=8)
    grille_audit.heading("ID", text="N°"); grille_audit.heading("Client", text="CLIENT"); grille_audit.heading("Article", text="ARTICLE"); grille_audit.heading("Total TTC", text="NET TTC"); grille_audit.heading("Date/Heure", text="TEMPOREL"); grille_audit.heading("Émetteur", text="CAISSIÈRE")
    
    grille_audit.column("ID", width=40, anchor=tk.CENTER); grille_audit.column("Client", width=110, anchor=tk.W); grille_audit.column("Article", width=140, anchor=tk.W); grille_audit.column("Total TTC", width=110, anchor=tk.CENTER); grille_audit.column("Date/Heure", width=120, anchor=tk.CENTER); grille_audit.column("Émetteur", width=80, anchor=tk.CENTER)
    grille_audit.pack(fill=tk.BOTH, expand=True, pady=5)

    action_afficher_tout_historique()

# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 6 SUR 7)
# =====================================================================

# --- 4. CONFIGURATION ET RAJOUT DU PERSONNEL (EXCLUSIVITÉ GÉRANT) ---
def ouvrir_panneau_administration():
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
        if data_base.ajouter_nouvel_employe_sql(nom, code, applique_tva):
            messagebox.showinfo("Succès", f"Compte de la caissière '{nom.upper()}' créé !")
            entree_nouveau_nom.delete(0, tk.END)
            entree_nouveau_code.delete(0, tk.END)
        else:
            messagebox.showerror("Erreur", "Identifiant déjà pris.")

    admin = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    admin.title("⚙️ Gestion Personnel")
    admin.geometry("400x380")
    admin.configure(bg="#f8fafc")
    admin.grab_set()

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
    select_tva_personnel.pack(fill=tk.X, pady=4)
    select_tva_personnel.current(0)

    tk.Button(cadre, text="➕ CRÉER LE COMPTE SÉCURISÉ", bg="#3b82f6", fg="white", font=("Helvetica", 9, "bold"), command=action_ajouter_caissier, pady=6).pack(fill=tk.X, pady=15)


# =====================================================================
# INTERFACE PRINCIPALE : COMPTOIR DE FACTURATION ET LOGIQUE DE FLUX
# =====================================================================
def ouvrir_comptoir_facturation():
    """Interface de vente principale pour les caissières et le gérant avec mise à jour des stocks."""
    global SESSION_UTILISATEUR, NOM_CAISSIERE_ACTIVE, NOM_BOUTIQUE_FIXE

    nom_boutique_fixe = (data_base.recuperer_nom_boutique_sql() or NOM_BOUTIQUE_FIXE).upper()
    NOM_BOUTIQUE_FIXE = nom_boutique_fixe

    comptoir = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    comptoir.title(f"💳 KASHFLOW Comptoir - Session {NOM_CAISSIERE_ACTIVE.upper()}")
    comptoir.geometry("480x720")
    comptoir.configure(bg="#f8fafc")

    def rafraichir_stocks_depuis_cloud():
        """Interroge l'API Cloud pour mettre à jour les stocks locaux (Mise à jour descendante)."""
        if not URL_API_KASHFLOW or not CLE_API_KASHFLOW:
            return
        try:
            reponse = requests.get(
                f"{URL_API_KASHFLOW}/stocks/etat",
                headers={"X-API-Key": CLE_API_KASHFLOW},
                timeout=5
            )
            if reponse.status_code == 200:
                donnees_serveur = reponse.json()
                for item in donnees_serveur.get("inventaire_magasin", []):
                    art = item.get("article_modele", "")
                    qte = item.get("quantite_restante", 0)
                    if art:
                        data_base.forcer_mise_a_jour_stock_local(art, qte)
                
                actualiser_liste_deroulante_smartphones()
        except Exception as e:
            logging.warning("Erreur rafraîchissement descendant des stocks : %s", e)

    def actualiser_liste_deroulante_smartphones():
        """Recharge les produits disponibles dans la liste déroulante Tkinter en lettres majuscules."""
        try:
            connexion = sqlite3.connect(data_base.DB_NAME)
            curseur = connexion.cursor()
            curseur.execute("SELECT modele FROM stocks WHERE quantite_dispo > 0")
            modeles = [str(row[0]).strip().upper() for row in curseur.fetchall()]
            connexion.close()
            
            liste_smartphones["values"] = modeles
            if modeles and not liste_smartphones.get():
                liste_smartphones.current(0)
        except Exception:
            pass

    def planifier_synchronisation_et_ecoute():
        """Planifie l'envoi et la réception asynchrone toutes les 30 secondes."""
        if comptoir.winfo_exists():
            threading.Thread(target=synchroniser_file_cloud, daemon=True).start()
            threading.Thread(target=rafraichir_stocks_depuis_cloud, daemon=True).start()
            comptoir.after(30000, planifier_synchronisation_et_ecoute)

    # Allumage immédiat des threads réseau en arrière-plan
    threading.Thread(target=synchroniser_file_cloud, daemon=True).start()
    threading.Thread(target=rafraichir_stocks_depuis_cloud, daemon=True).start()
    comptoir.after(30000, planifier_synchronisation_et_ecoute)

    tk.Label(comptoir, text=f"{nom_boutique_fixe} - COMPTOIR DE FACTURATION", font=("Helvetica", 12, "bold"), bg="#0f766e", fg="white", pady=8).pack(fill=tk.X)

    def verifier_connexion_cloud():
        """Effectue une vérification discrète de la liaison avec Render au démarrage."""
        try:
            reponse = requests.get(URL_API_KASHFLOW, timeout=4)
            if reponse.status_code == 200:
                label_statut_cloud.config(text="CONNECTÉ 🟢", fg="#10b981")
            else:
                label_statut_cloud.config(text="📡 SERVEUR EN LIGNE (RÉPONSE INCONNUE) 🟡", fg="#f59e0b")
        except Exception:
            label_statut_cloud.config(text=" déconnecté 🔴", fg="#dc2626")

    def forcer_test_reseau():
        """Bouton manuel pour forcer le diagnostic réseau et rafraîchir l'inventaire."""
        label_statut_cloud.config(text="🔄 Connexion en cours...", fg="#94a3b8")
        comptoir.update_idletasks()
        try:
            reponse = requests.get(URL_API_KASHFLOW, timeout=4)
            if reponse.status_code == 200:
                label_statut_cloud.config(text="📡 CLOUD CONNECTÉ : EN DIRECT 🟢", fg="#10b981")
                threading.Thread(target=rafraichir_stocks_depuis_cloud, daemon=True).start()
                messagebox.showinfo("Réseau OK", "Connexion et mise à jour des stocks réussies !")
            else:
                label_statut_cloud.config(text="📡 SERVEUR EN LIGNE (RÉPONSE INCONNUE) 🟡", fg="#f59e0b")
        except Exception:
            label_statut_cloud.config(text="📡 CLOUD DÉCONNECTÉ (PAS D'INTERNET) 🔴", fg="#dc2626")
            messagebox.showwarning("Réseau Coupé", "Impossible de joindre le serveur. Fonctionnement local activé.")

    # Zone d'affichage du statut Cloud sous le titre
    label_statut_cloud = tk.Label(comptoir, text="📡 VÉRIFICATION DU STATUT RÉSEAU...", font=("Helvetica", 10, "bold"), bg="#1e3a8a", fg="white")
    label_statut_cloud.pack(pady=2)
    
    btn_test_reseau = tk.Button(comptoir, text="🔄 Tester la liaison Cloud", font=("Helvetica", 8, "bold"), bg="#1e293b", fg="white", command=forcer_test_reseau)
    btn_test_reseau.pack(pady=2)
    
    comptoir.after(1000, verifier_connexion_cloud)
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 7A SUR 7)
# =====================================================================

    def action_bouton_enregistrer():
        """Valide la saisie, applique la déduction fiscale et enregistre la vente."""
        caissiere_nom = str(NOM_CAISSIERE_ACTIVE).strip().lower()
        nom_client = entree_client.get().strip()
        smartphone = liste_smartphones.get().strip().lower()
        desc = entree_desc.get().strip()
        prix_txt = entree_prix.get().strip()
        qte_txt = entree_quantite.get().strip()

        if not all([nom_client, smartphone, desc, prix_txt, qte_txt]):
            messagebox.showwarning("Champs incomplets", "Remplissez tous les champs obligatoires.")
            return

        try:
            prix = float(prix_txt)
            qte = int(qte_txt)
            if prix <= 0 or qte <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Erreur", "Prix et quantité invalides.")
            return

        try:
            verif_stock = data_base.verifier_et_reduire_stock(smartphone, qte)
            if not verif_stock["autorise"]:
                messagebox.showerror("Stock Insuffisant", verif_stock["reason"])
                return

            if SESSION_UTILISATEUR == "gerant":
                applique_tva = 1 if var_tva_directe.get() else 0
            else:
                applique_tva = data_base.obtenir_regime_tva_employe(caissiere_nom)
                
            calcul = operation.calculer_facture_dynamique(prix, qte, applique_tva)
            nom_boutique = data_base.recuperer_nom_boutique_sql() or "KASHFLOW_MANAGER"
            reference_locale = str(uuid.uuid4())
            
            num_facture = data_base.enregistrer_vente_sql(
                nom_client, smartphone, desc,
                calcul["montant_ht"], calcul["valeur_tva"], calcul["total_ttc"],
                caissiere_nom, reference_locale
            )

            if num_facture:
                donnees_cloud = {
                    "reference_locale": reference_locale,
                    "client": str(nom_client).strip(),
                    "article": str(smartphone).strip(),
                    "description_unique": str(desc).strip(),
                    "prix_ht": float(prix),
                    "quantite": int(qte),
                    "caissiere": str(caissiere_nom).strip().lower(),
                    "applique_tva_vente": int(applique_tva)
                }

                threading.Thread(target=synchroniser_vente_cloud, args=(reference_locale, donnees_cloud), daemon=True).start()
                operation.generer_recu_pdf_industriel(
                    nom_boutique, num_facture, nom_client, smartphone, desc, qte,
                    calcul["montant_ht"], calcul["valeur_tva"], calcul["total_ttc"], caissiere_nom
                )
                                # 🟢 DÉCLENCHEMENT DU ROULEAU THERMIQUE AUTOMATIQUE
                imprimer_ticket_thermique_direct(nom_client, smartphone, calcul["total_ttc"], caissiere_nom)


                if verif_stock["alerte_patron"]:
                    messagebox.showwarning("Alerte Stock", f"⚠️ {verif_stock['restant']} pcs")
                    
                messagebox.showinfo("Succès", f"✅ Vente #{num_facture} émise avec succès !")
                
                entree_client.delete(0, tk.END)
                entree_desc.delete(0, tk.END)
                entree_prix.delete(0, tk.END)
                entree_quantite.delete(0, tk.END)
                actualiser_liste_deroulante_smartphones()
                entree_client.focus()
        except Exception as e:
            messagebox.showerror("Erreur Système", f"Une erreur s'est produite : {str(e)}")

    # Construction du cadre de saisie principal du comptoir
    cadre = tk.Frame(comptoir, bg="#f8fafc", padx=15, pady=10)
    cadre.pack(fill=tk.BOTH, expand=True)

    tk.Label(cadre, text="Client :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    entree_client = tk.Entry(cadre, font=("Helvetica", 11), bd=2)
    entree_client.pack(fill=tk.X, pady=4)

    tk.Label(cadre, text="Sélectionner l'Article :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    liste_smartphones = ttk.Combobox(cadre, state="readonly", font=("Helvetica", 10))
    actualiser_liste_deroulante_smartphones()
    liste_smartphones.pack(fill=tk.X, pady=4)

    tk.Label(cadre, text="Description unique (N° IMEI, Série, SAV) :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    entree_desc = tk.Entry(cadre, font=("Helvetica", 11), bd=2)
    entree_desc.pack(fill=tk.X, pady=4)

    tk.Label(cadre, text="Prix Unitaire HT (FCFA) :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
    entree_prix = tk.Entry(cadre, font=("Helvetica", 11), bd=2)
    entree_prix.pack(fill=tk.X, pady=4)

    tk.Label(cadre, text="Quantité :", bg="#f8fafc", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 7B-1 SUR 7)
# =====================================================================

    entree_quantite = tk.Entry(cadre, font=("Helvetica", 11), bd=2)
    entree_quantite.pack(fill=tk.X, pady=4)

    var_tva_directe = tk.BooleanVar(value=True)
    if SESSION_UTILISATEUR == "gerant":
        case_tva = tk.Checkbutton(cadre, text="Facturer la TVA (19.25%) sur cette vente", variable=var_tva_directe, bg="#f8fafc", font=("Helvetica", 10, "bold"), fg="#1e3a8a")
        case_tva.pack(anchor=tk.W, pady=6)

    entree_client.bind("<Return>", lambda event: liste_smartphones.focus())
    liste_smartphones.bind("<Return>", lambda event: entree_desc.focus())
    entree_desc.bind("<Return>", lambda event: entree_prix.focus())
    entree_prix.bind("<Return>", lambda event: entree_quantite.focus())
    entree_quantite.bind("<Return>", lambda event: action_bouton_enregistrer())

    tk.Button(cadre, text="🛒 VALIDER LA VENTE & ÉMETTRE LE PDF", font=("Helvetica", 11, "bold"), bg="#10b981", fg="white", command=action_bouton_enregistrer, pady=10).pack(fill=tk.X, pady=15)

    tk.Label(comptoir, text="PANNEAU DE CONTROLE SÉCURISÉ", font=("Helvetica", 10, "bold"), bg="#e2e8f0", fg="#1e293b", pady=4).pack(fill=tk.X)
    cadre_menu = tk.Frame(comptoir, bg="#e2e8f0", padx=10, pady=8)
    cadre_menu.pack(fill=tk.X)

    if SESSION_UTILISATEUR == "gerant":
        tk.Button(cadre_menu, text="📦 Stocks", bg="#0284c7", fg="white", font=("Helvetica", 9, "bold"), command=ouvrir_panneau_stock).pack(side=tk.LEFT, padx=3)
        tk.Button(cadre_menu, text="📊 Analyse", bg="#7c3aed", fg="white", font=("Helvetica", 9, "bold"), command=ouvrir_panneau_historique).pack(side=tk.LEFT, padx=3)
        tk.Button(cadre_menu, text="⚙️ Employés", bg="#ea580c", fg="white", font=("Helvetica", 9, "bold"), command=ouvrir_panneau_administration).pack(side=tk.LEFT, padx=3)
    else:
        tk.Button(cadre_menu, text="📊 HISTORIQUE DE VENTES", bg="#f59e0b", fg="white", font=("Helvetica", 9, "bold"), command=ouvrir_historique_caissiere).pack(side=tk.LEFT, padx=5)
    
    def deconnecter():
        comptoir.destroy()
        FENETRE_PRINCIPALE_LOGIN.deiconify()
        entree_user.delete(0, tk.END)
        entree_password.delete(0, tk.END)
        entree_user.insert(0, "gerant")
        entree_user.focus()
    
    tk.Button(cadre_menu, text="🚪 Quitter", bg="#64748b", fg="white", font=("Helvetica", 9, "bold"), command=deconnecter).pack(side=tk.RIGHT, padx=3)


def ouvrir_historique_caissiere():
    """Fenêtre d'historique personnelle des ventes de la caissière active avec filtrage temporel complet."""
    caissiere_nom = str(NOM_CAISSIERE_ACTIVE).strip().lower()

    historique = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    historique.title(f"📊 Historique de {caissiere_nom.upper()}")
    historique.geometry("750x620")
    historique.configure(bg="#f8fafc")
    historique.grab_set()

    tk.Label(historique, text=f"HISTORIQUE DES VENTES PERSONNEL - {caissiere_nom.upper()}", font=("Helvetica", 11, "bold"), bg="#1e293b", fg="white", pady=8).pack(fill=tk.X)

    cadre_stat = tk.LabelFrame(historique, text="Suivi Temporel de mon Tiroir-Caisse", bg="#f8fafc", padx=10, pady=8)
    cadre_stat.pack(fill=tk.X, padx=15, pady=10)

    tk.Label(cadre_stat, text="Période :", bg="#f8fafc").grid(row=0, column=0, padx=5, sticky=tk.W)
    select_tempo = ttk.Combobox(cadre_stat, values=["JOUR", "MOIS", "ANNEE"], width=10, state="readonly")
    select_tempo.grid(row=0, column=1, padx=5); select_tempo.current(0)

    tk.Label(cadre_stat, text="Cible (ex: 31/08/2026) :", bg="#f8fafc").grid(row=0, column=2, padx=5, sticky=tk.W)
    entree_cible_historique = tk.Entry(cadre_stat, width=15, font=("Helvetica", 10), bd=2)
    entree_cible_historique.grid(row=0, column=3, padx=5)

    def rafraichir_historique_caissiere():
        valeur = entree_cible_historique.get().strip()
        if not valeur:
            messagebox.showwarning("Critère manquant", "Saisissez un critère cible.")
            return

        for item in arbre_historique.get_children(): arbre_historique.delete(item)
        ventes = data_base.recuperer_ventes_par_caissiere(caissiere_nom)
        total_ttc = 0.0

        for v in ventes:
            date_brute = str(v[4]).strip()
            garder = False
            
            if select_tempo.get() == "JOUR":
                if date_brute == valeur: garder = True
            elif select_tempo.get() == "MOIS":
                try:
                    m_db = date_brute.split("/")
                    if int(m_db[1]) == int(valeur): garder = True
                except Exception: pass
            elif select_tempo.get() == "ANNEE":
                if date_brute.endswith(valeur): garder = True

            if garder:
                total_ttc += float(v[3])
                arbre_historique.insert("", tk.END, values=(v[0], v[1], str(v[2]).strip(), f"{v[3]} FCFA", f"{v[4]} à {v[5]}", caissiere_nom.upper()))

        label_total.config(text=f"MON TOTAL COMPTABLE CUMULÉ : {round(total_ttc, 2)} FCFA")

    tk.Button(cadre_stat, text="🔍 FILTRER", bg="#1e293b", fg="white", font=("Helvetica", 9, "bold"), command=rafraichir_historique_caissiere).grid(row=0, column=4, padx=10)

    label_total = tk.Label(cadre_stat, text="MON TOTAL COMPTABLE CUMULÉ : 0.00 FCFA", font=("Helvetica", 11, "bold"), bg="#d1fae5", fg="#065f46", pady=6)
    label_total.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=6)

    arbre_historique = ttk.Treeview(historique, columns=("ID", "Client", "Article", "Total TTC", "Date/Heure", "Caissière"), show="headings", height=12)
    arbre_historique.heading("ID", text="N°"); arbre_historique.heading("Client", text="CLIENT"); arbre_historique.heading("Article", text="ARTICLE"); arbre_historique.heading("Total TTC", text="NET TTC"); arbre_historique.heading("Date/Heure", text="TEMPOREL"); arbre_historique.heading("Caissière", text="EMETTEUR")
    arbre_historique.column("ID", width=40, anchor=tk.CENTER); arbre_historique.column("Client", width=120, anchor=tk.W); arbre_historique.column("Article", width=180, anchor=tk.W); arbre_historique.column("Total TTC", width=110, anchor=tk.CENTER); arbre_historique.column("Date/Heure", width=140, anchor=tk.CENTER); arbre_historique.column("Caissière", width=100, anchor=tk.CENTER)
    arbre_historique.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

# =====================================================================
# MODULE 4 : app_visuel.py (Version Multi-Postes Pro - PARTIE 7B-2 SUR 7)
# =====================================================================

def verifier_acces():
    """Valide la session employé et applique le contrôle de licence Cloud bloquant et inviolable."""
    global SESSION_UTILISATEUR, NOM_CAISSIERE_ACTIVE
    user = entree_user.get().strip().lower()
    pwd = entree_password.get().strip()

    if not user or not pwd:
        messagebox.showwarning("Champs vides", "Saisissez l'identifiant et le mot de passe.")
        return

    try:
        # Allumage préventif des structures locales SQLite
        data_base.initialisation_systeme()

        # Lecture immédiate en base de données locale pour vérifier l'état
        connexion = sqlite3.connect(data_base.DB_NAME)
        curseur = connexion.cursor()
        curseur.execute("SELECT mot_de_passe FROM employes WHERE identifiant = 'gerant'")
        ligne_pwd = curseur.fetchone()
        
        curseur.execute("SELECT valeur FROM configuration WHERE cle = 'nom_boutique'")
        ligne_boutique = curseur.fetchone()
        connexion.close()

        mot_de_passe_actuel_db = ligne_pwd[0] if ligne_pwd else "serge2026"
        boutique_installee = ligne_boutique is not None

        # 🟢 CORRECTION CONSTRUCTEUR : Si le nom de la boutique n'est pas dans la base locale, 
        # on force l'ouverture de l'assistant, même si le Cloud est actif !
        if not boutique_installee:
            if user == "gerant" and pwd == "serge2026":
                nom_magasin = simpledialog.askstring("Configuration Boutique - Étape 1/2", "Bienvenue chez KashKeeper !\n\nVeuillez entrer le NOM OFFICIEL de votre entreprise :")
                if not nom_magasin or not nom_magasin.strip():
                    messagebox.showwarning("Incomplet", "Le nom de l'entreprise est exigé.")
                    return

                creer_code = simpledialog.askstring("Configuration Boutique - Étape 2/2", "Veuillez définir votre MOT DE PASSE personnalisé définitif :")
                if not creer_code or len(creer_code.strip()) < 6 or creer_code.strip() == "serge2026":
                    messagebox.showerror("Erreur", "Le mot de passe exige un minimum de 6 caractères et doit être différent de 'serge2026'.")
                    return

                data_base.enregistrer_nom_boutique_sql(nom_magasin.strip())
                data_base.configurer_compte_gerant_sql(creer_code.strip())
                
                messagebox.showinfo("Succès", f"Félicitations !\nL'entreprise '{nom_magasin.strip().upper()}' est activée.\n\nConnectez-vous maintenant avec votre nouveau mot de passe.")
                entree_password.delete(0, tk.END)
                entree_password.focus()
                return
            else:
                # 🛑 SÉCURITÉ : Si la base locale vient d'être supprimée, on explique au gérant d'utiliser le code d'usine pour réinitialiser
                if pwd != "serge2026":
                    messagebox.showerror("Nouvelle Installation", "Base de données locale introuvable.\n\nConnectez-vous avec  le mot de passe d'usine pour reconfigurer votre espace.")
                    return

        # 🛑 PROTECTION : Ce bloc ne s'active désormais QUE si la boutique est déjà configurée localement
        if boutique_installee and pwd == "serge2026" and mot_de_passe_actuel_db != "serge2026":
            messagebox.showerror("Accès Refusé", "Ce mot de passe d'usine a expiré après la configuration initiale.")
            return

        # 🟢 CONTRÔLE INTERCONNEXION SAAS (Vérification de la licence sur Render)
        if data_base.verifier_identifiants_sql(user, pwd):
            try:
                reponse_licence = requests.get(
                    f"{URL_API_KASHFLOW}/licence/statut", 
                    headers={"X-API-Key": CLE_API_KASHFLOW}, 
                    timeout=5
                )
                
                if reponse_licence.status_code == 200:
                    infos = reponse_licence.json()
                    statut_serveur = infos.get("statut", "actif")
                    jours_restants = infos.get("jours_restants", 0)

                    # 🛑 CAS 1 : BLOCAGE DE SÉCURITÉ STRICT
                    if statut_serveur == "expire":
                        messagebox.showerror("Abonnement Expiré", "🚨 COMPTOIR VERROUILLÉ !\n\nVotre période d'abonnement et de tolérance est terminée.\nVeuillez régulariser en cliquant sur 'PAYER ABONNEMENT' en bas à droite.")
                        return # On arrête TOUT ici, le code ne descend pas !
                    
                    # 🔶 CAS 2 : PÉRIODE DE GRÂCE (Tolérance de 3 jours)
                    elif statut_serveur == "grace":
                        messagebox.showwarning("Avertissement de Tolérance", f"⚠️ ALERTE FINANCIÈRE :\n\nVotre abonnement est expiré. Mode tolérance activé pour {jours_restants} jour(s).\nVeuillez recharger pour éviter la coupure automatique.")

            except Exception as e:
                # Tolérance hors-ligne si panne de réseau internet temporaire
                logging.warning("Vérification licence différée (mode hors-ligne) : %s", e)

            # 🟢 SEULEMENT SI TOUT EST OK : On autorise enfin l'accès au comptoir
            SESSION_UTILISATEUR = str(user).strip().lower()
            NOM_CAISSIERE_ACTIVE = str(user).strip().lower()
            messagebox.showinfo("Accès Autorisé", f"Bienvenue {SESSION_UTILISATEUR.upper()} !")
            FENETRE_PRINCIPALE_LOGIN.withdraw()
            ouvrir_comptoir_facturation()
        else:
            messagebox.showerror("Accès Refusé", "Identifiant ou mot de passe incorrect.")
            
    except Exception as e:
        messagebox.showerror("Erreur", f"Erreur système : {str(e)}")



def recuperer_mot_de_passe_oublie():
    """Permet la récupération par clé master uniquement si le profil de base a été configuré."""
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

        cle_saisie = simpledialog.askstring("Sécurité Constructeur", "Veuillez entrer la clé de secours fournie par l'ingénieur Serge :")
        if cle_saisie == CLE_MASTER_SERGE:
            nouveau_code = simpledialog.askstring("Réinitialisation", "Clé correcte !\nTapez votre nouveau mot de passe gérant :")
            if nouveau_code and nouveau_code.strip():
                data_base.configurer_compte_gerant_sql(nouveau_code.strip())
                messagebox.showinfo("Succès", "Mot de passe réinitialisé ! Connectez-vous.")
        elif cle_saisie is not None:
            messagebox.showerror("Accès Refusé", "Clé de secours invalide.")
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
            timeout=10
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
    """Fenêtre de renouvellement de l'abonnement par Mobile Money ou Carte Bancaire Internationale."""
    def action_declencher_prelevement():
        num_momo = entree_numero_momo.get().strip()
        
        if mode_paiement.get() == "MOMO":
            if not num_momo or len(num_momo) < 9:
                messagebox.showwarning("Numéro invalide", "Veuillez entrer un numéro de téléphone valide à 9 chiffres.")
                return
        else:
            num_momo = "CARTE_BANCAIRE"

        btn_payer.config(text="🔄 APPEL RÉSEAU EN COURS...", state=tk.DISABLED, bg="#475569")
        fenetre_paye.update_idletasks()

        try:
            reponse = requests.post(
                f"{URL_API_KASHFLOW}/licence/collecter-momo",
                json={"numero": num_momo},
                headers={"X-API-Key": CLE_API_KASHFLOW},
                timeout=12
            )
            
            if reponse.status_code == 200:
                donnees = reponse.json()
                if num_momo == "CARTE_BANCAIRE":
                    messagebox.showinfo(
                        "Paiement par Carte", 
                        "💳 INTERCONNEXION BANCAIRE VISA/MC REUSSIE !\n\nUn lien de facturation international a été raccordé à votre boutique.\n"
                        "Consultez vos reçus pour finaliser le paiement."
                    )
                else:
                    messagebox.showinfo("Paiement Initié", f"📱 {donnees.get('message')}")
                fenetre_paye.destroy()
            else:
                try: erreur_msg = reponse.json().get("detail", "Refus de la passerelle.")
                except Exception: erreur_msg = "Erreur de communication avec le serveur."
                messagebox.showerror("Échec", f"🔴 {erreur_msg}")
                btn_payer.config(text="📲 DEMANDER LE RETRAIT", state=tk.NORMAL, bg="#10b981")
        except Exception as e:
            messagebox.showerror("Erreur Système", f"Impossible de joindre le serveur Cloud Render :\n{e}")
            btn_payer.config(text="📲 DEMANDER LE RETRAIT", state=tk.NORMAL, bg="#10b981")

    def toggle_champs_paiement():
        if mode_paiement.get() == "MOMO":
            cadre_input.pack(fill=tk.X, pady=(10, 10), before=btn_payer)
        else:
            cadre_input.pack_forget()

    fenetre_paye = Toplevel(FENETRE_PRINCIPALE_LOGIN)
    fenetre_paye.title("💳 Renouvellement de l'Abonnement")
    fenetre_paye.geometry("440x420")
    fenetre_paye.configure(bg="#1e293b")
    fenetre_paye.resizable(False, False)
    fenetre_paye.grab_set()

    tk.Label(fenetre_paye, text="RENOUVELLEMENT DE L'ABONNEMENT", font=("Segoe UI", 11, "bold"), bg="#1e293b", fg="#f59e0b").pack(pady=(18, 5))
    
    cadre_choix = tk.Frame(fenetre_paye, bg="#1e293b")
    cadre_choix.pack(pady=10)
    mode_paiement = tk.StringVar(value="MOMO")
    
    tk.Radiobutton(cadre_choix, text="📱 Mobile Money", variable=mode_paiement, value="MOMO", bg="#1e293b", fg="white", selectcolor="#1e293b", font=("Segoe UI", 9, "bold"), command=toggle_champs_paiement).pack(side=tk.LEFT, padx=15)
    tk.Radiobutton(cadre_choix, text="💳 Carte Bancaire (Visa/Mc)", variable=mode_paiement, value="CARD", bg="#1e293b", fg="white", selectcolor="#1e293b", font=("Segoe UI", 9, "bold"), command=toggle_champs_paiement).pack(side=tk.LEFT, padx=15)

    cadre_texte = tk.Frame(fenetre_paye, bg="#1e293b", padx=20)
    cadre_texte.pack(fill=tk.X)

    texte_instructions = (
        "Sélectionnez votre mode de règlement préféré.\n"
        "Pour le Mobile Money, un pop-up USSD surgira sur votre écran.\n"
        "Pour la Carte Bancaire, une facturation sécurisée Visa/Mastercard sera initiée.\n\n"
        "Tarif mensuel : 14 000 FCFA"
    )
    tk.Label(cadre_texte, text=texte_instructions, font=("Segoe UI", 10), bg="#1e293b", fg="#cbd5e1", justify=tk.LEFT, wraplength=390).pack(anchor=tk.W, pady=5)
    
    cadre_input = tk.Frame(fenetre_paye, bg="#1e293b", padx=20)
    cadre_input.pack(fill=tk.X, pady=(10, 10))
    tk.Label(cadre_input, text="Numéro Mobile Money (Cameroun) :", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#94a3b8").pack(anchor=tk.W, pady=(0, 4))
    
    entree_numero_momo = tk.Entry(cadre_input, font=("Segoe UI", 13, "bold"), bd=0, bg="white", fg="#1e293b", justify=tk.CENTER, relief=tk.FLAT)
    entree_numero_momo.pack(fill=tk.X, ipady=6)
    entree_numero_momo.insert(0, "6")

    btn_payer = tk.Button(fenetre_paye, text="🚀  DEMANDER LE RETRAIT SÉCURISÉ", bg="#10b981", fg="white", font=("Segoe UI", 10, "bold"), bd=0, cursor="hand2", command=action_declencher_prelevement, pady=8)
    btn_payer.pack(fill=tk.X, padx=20, pady=(15, 5))
    
    tk.Button(fenetre_paye, text="ANNULER", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9, "bold", "underline"), bd=0, cursor="hand2", command=fenetre_paye.destroy).pack(pady=5)




# --- POINT DE DÉMARRAGE DE LA RACINE UNIQUE ---
login = tk.Tk()
FENETRE_PRINCIPALE_LOGIN = login

login.title("Sécurité d'Accès")
login.geometry("350x460") 
login.configure(bg="#1e293b")

tk.Label(login, text="CONNEXION SÉCURISÉE", font=("Helvetica", 12, "bold"), bg="#1e293b", fg="white").pack(pady=20)
boite = tk.Frame(login, bg="#1e293b", padx=30)
boite.pack(fill=tk.X)

tk.Label(boite, text="Identifiant Employé :", bg="#1e293b", fg="#cbd5e1").pack(anchor=tk.W)
entree_user = tk.Entry(boite, font=("Helvetica", 11), bd=2)
entree_user.pack(fill=tk.X, pady=5)
entree_user.insert(0, "gerant")

tk.Label(boite, text="Mot de passe secret :", bg="#1e293b", fg="#cbd5e1").pack(anchor=tk.W)

# =====================================================================
# ÉCRAN DE VERROUILLAGE SÉCURISÉ ET CONFIGURATION DU POINT DE DÉMARRAGE
# =====================================================================

entree_password = tk.Entry(boite, font=("Helvetica", 11), show="*", bd=2)
entree_password.pack(fill=tk.X, pady=5)

entree_user.bind("<Return>", lambda event: entree_password.focus())
entree_password.bind("<Return>", lambda event: verifier_acces())

# 1. Bouton d'accès principal
tk.Button(login, text="🔓 ACCÉDER AU COMPTOIR", font=("Helvetica", 11, "bold"), bg="#3b82f6", fg="white", command=verifier_acces).pack(fill=tk.X, padx=30, pady=12)

# 2. Bouton de mise à jour
tk.Button(login, text="🔄 VÉRIFIER LES MISES À JOUR", font=("Helvetica", 10, "bold"), bg="#475569", fg="white", command=action_telecharger_mise_a_jour).pack(fill=tk.X, padx=30, pady=5)

# 3. Bouton mot de passe oublié
tk.Button(login, text="❓ Mot de passe oublié / Réinitialiser", font=("Helvetica", 9, "underline"), bg="#1e293b", fg="#94a3b8", bd=0, command=recuperer_mot_de_passe_oublie, cursor="hand2").pack(pady=5)

# 🚀 ANCRAGE EXTRÊME INFERIEUR DROIT DU BOUTON ABONNEMENT MENSUEL
cadre_bas = tk.Frame(login, bg="#1e293b")
cadre_bas.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=10)

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

login.mainloop()
