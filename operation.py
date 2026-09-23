# =====================================================================
# ENGINE FINANCIER KASHFLOW - MODULE 2 : operation.py (Édition Demi-Format A5 Haute Clarté)
# =====================================================================
import os
import sys
from fpdf import FPDF
from datetime import datetime

# Taux officiel de la TVA en vigueur au Cameroun (19.25%)
TAUX_TVA_CAMEROUN = 19.25 / 100

def calculer_facture_dynamique(prix_unitaire_ht, quantite, applique_tva):
    """
    Calcule le montant Hors Taxes, la valeur exacte de la TVA (0% ou 19.25%)
    et le montant toutes taxes comprises (TTC) pour la facture.
    """
    try:
        prix = float(prix_unitaire_ht)
        qt = int(quantite)
        
        # Validation rigoureuse d'ingénierie
        if prix <= 0 or qt <= 0:
            return None
            
        montant_ht = prix * qt
        
        # RÈGLE DU CAHIER DES CHARGES : Gestion des grands et petits commerces
        if int(applique_tva) == 1:
            # Grande entreprise : application stricte de la taxe nationale
            valeur_tva = montant_ht * TAUX_TVA_CAMEROUN
        else:
            # Petite boutique de quartier : vente directe sans facturation fiscale
            valeur_tva = 0.0
            
        montant_ttc = montant_ht + valeur_tva
        
        return {
            "montant_ht": round(montant_ht, 2),
            "valeur_tva": round(valeur_tva, 2),
            "total_ttc": round(montant_ttc, 2)
        }
    except Exception:
        return None


def generer_recu_pdf_industriel(nom_boutique, num_facture, nom_client, nom_article, desc_unique, quantite, mnt_ht, valeur_tva, total_ttc, nom_caissiere):
    """
    📄 INNOVATION DEMI-FORMAT A5 HAUTE CLARTÉ :
    Génère un reçu au format compact A5 avec un contraste renforcé pour éviter la fatigue visuelle.
    """
    try:
        maintenant = datetime.now()
        date_facture = maintenant.strftime("%d/%m/%Y")
        heure_facture = maintenant.strftime("%H:%M")
        
        # Initialisation en format A5 (Demi-page)
        pdf = FPDF(orientation="P", unit="mm", format="A5")
        pdf.add_page()
        pdf.set_margins(10, 10, 10)
        
        # =====================================================================
        # 🛡️ 1. FILIGRANE DE SÉCURITÉ (RESTER LÉGER MAIS NET EN ARRIÈRE-PLAN)
        # =====================================================================
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(242, 242, 242) # Légèrement accentué pour la lisibilité de l'encre
        pdf.text(x=12, y=95, txt=f"{nom_boutique.upper()} - DOCUMENT AUTHENTIQUE")
        pdf.text(x=12, y=105, txt=f"GARANTIE CONSTRUCTEUR CERTIFIEE")
        pdf.set_text_color(0, 0, 0)
        
        # =====================================================================
        # 🏢 2. EN-TÊTE OFFICIEL DE L'ENTREPRISE (CONTRASTE MAXIMAL)
        # =====================================================================
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(11, 92, 86) # Vert teal plus sombre pour un meilleur contraste
        pdf.cell(128, 6, f"{nom_boutique.upper()}", ln=1, align="C")
        
        pdf.set_font("Helvetica", "B", 10) # Augmenté de 9 à 10
        pdf.set_text_color(15, 23, 42) # Noir profond au lieu de gris sombre
        pdf.cell(128, 5, f"FACTURE COMMERCIALE N°{str(num_facture).zfill(4)}", ln=1, align="C")
        
        pdf.set_font("Helvetica", "B", 8.5) # Passage en gras pour éviter le flou d'encre
        pdf.set_text_color(51, 65, 85) # Gris ardoise soutenu
        pdf.cell(128, 4, f"Émise le {date_facture} à {heure_facture}", ln=1, align="C")
        pdf.ln(2)
        
        # Ligne de séparation renforcée
        pdf.set_draw_color(148, 163, 184) # Bordure plus sombre pour une coupure nette
        pdf.set_line_width(0.5)
        pdf.line(10, pdf.get_y(), 138, pdf.get_y())
        pdf.ln(3)
        
        # =====================================================================
        # 🧑‍💼 3. TRAÇABILITÉ DES ACTEURS (TEXTES EN GRAS ACCENTUÉS)
        # =====================================================================
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(64, 5, f"Client : {nom_client.upper()}", ln=0)
        pdf.cell(64, 5, f"Émis par : {nom_caissiere.upper()}", ln=1, align="R")
        pdf.ln(3)
        
        # =====================================================================
        # 📦 4. TABLEAU DES ARTICLES (POLICES ÉPAISSIES ANTI-FATIGUE)
        # =====================================================================
        pdf.set_fill_color(226, 232, 240) # Fond d'en-tête légèrement plus prononcé
        pdf.set_draw_color(148, 163, 184)
        pdf.set_font("Helvetica", "B", 8.5)
        
        pdf.cell(53, 6, " DÉSIGNATION DE L'ARTICLE", border=1, ln=False, fill=True)
        pdf.cell(15, 6, "QTÉ", border=1, ln=False, align="C", fill=True)
        pdf.cell(30, 6, "P.U HT", border=1, ln=False, align="R", fill=True)
        pdf.cell(30, 6, "TOTAL HT ", border=1, ln=True, align="R", fill=True)
        
        # Lignes de données de l'article (Épaissies en noir uni)
        pdf.set_text_color(15, 23, 42)
        
        y_actuel = pdf.get_y()
        pdf.rect(10, y_actuel, 53, 11) # Hauteur ajustée de 10 à 11 pour aérer le texte
        pdf.set_xy(11, y_actuel + 1)
        pdf.set_font("Helvetica", "B", 9) # Taille augmentée pour la netteté
        pdf.cell(52, 4, str(nom_article).upper(), ln=True)
        
        pdf.set_xy(11, pdf.get_y() + 0.5)
        pdf.set_font("Helvetica", "B", 7.5) # Passage de l'italique fin (I) au gras (B) anti-flou
        pdf.cell(52, 4, f"ID/IMEI/Série: {desc_unique}", ln=False)
        
        # Cellules financières de la ligne
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_xy(63, y_actuel)
        pdf.cell(15, 11, f"{quantite}", border=1, align="C")
        
        pu_ht = mnt_ht / quantite if quantite > 0 else 0
        pdf.cell(30, 11, f"{pu_ht:,.0f} FCFA", border=1, align="R")
        pdf.cell(30, 11, f"{mnt_ht:,.0f} FCFA ", border=1, align="R", ln=True)
        pdf.ln(3)
        
        # =====================================================================
        # 📊 5. BLOC DES TOTAUX HAUTE DENSITÉ
        # =====================================================================
        pdf.set_x(65)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(38, 4, "Montant Total HT :", ln=False, align="R")
        pdf.cell(25, 4, f"{mnt_ht:,.2f} FCFA", ln=True, align="R")
        
        pdf.set_x(65)
        pdf.cell(38, 4, "Valeur de la TVA :", ln=False, align="R")
        pdf.cell(25, 4, f"{valeur_tva:,.2f} FCFA", ln=True, align="R")
        
        pdf.ln(1)
        pdf.set_x(55)
        pdf.set_fill_color(220, 252, 231) # Vert plus contrasté pour l'encadré Net à Payer
        pdf.set_draw_color(34, 197, 94)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(21, 128, 61) # Vert foncé haute clarté
        pdf.cell(73, 8, f" NET À PAYER : {total_ttc:,.2f} FCFA ", border=1, ln=True, align="C", fill=True)
        
        # =====================================================================
        # 📜 6. PIED DE PAGE (ÉVITÉ LE GRIS TROP CLAIR POUR LES PETITS CARACTÈRES)
        # =====================================================================
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 7.5) # Suppression du style italique fin fatiguant pour l'œil
        pdf.set_text_color(71, 85, 105) # Assombri pour une lecture sans effort
        pdf.cell(128, 4, "Merci pour votre confiance et a tres bientot ! ", ln=1, align="C")
        
        # =====================================================================
        # 📂 COMPILATION ET ENREGISTREMENT PHYSIQUE D'USINE
        # =====================================================================
              # =====================================================================
        # 📂 COORDONNÉES COMPTABLES DU SOUS-DOSSIER FACTURES_EMISES (FIXÉ .EXE)
        # =====================================================================
        if getattr(sys, 'frozen', False):
            dossier_reel_app = os.path.dirname(sys.executable)
        else:
            dossier_reel_app = os.path.dirname(os.path.abspath(__file__))

        # L'utilisation de dossier_reel_app (avec deux "e") est maintenant unifiée
        dossier_factures = os.path.join(dossier_reel_app, "Factures_Emises")
        if not os.path.exists(dossier_factures):
            os.makedirs(dossier_factures)

        nom_magasin_propre = nom_boutique.replace(' ', '_').replace('/', '_').replace('\\', '_')
        nom_fichier = os.path.join(dossier_factures, f"recu_{nom_magasin_propre}_F{num_facture}.pdf")
    
        pdf.output(nom_fichier)
        
        # Exécution instantanée du gestionnaire d'impression Windows/Linux
        try:
            os.startfile(nom_fichier, "print")
        except Exception as e:
            print(f"[INFO IMPRIMANTE] : Aucune imprimante détectée ou configurée par défaut. {e}")
            
        return True
  
    except Exception as e:
        print(f"[ERREUR DESSINATEUR PDF V5.5 DEMI-FORMAT A5] : {e}")
        return False
